"""Gemini client wrapper: JSON-only responses, Pydantic validation, structured latency logging.

The model never receives database credentials or tool access; it only returns JSON which is
validated server-side before anything is persisted.
"""
import json
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import get_settings
from ..logging_setup import get_logger

log = get_logger("ai")
T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    error_type = "ai_error"


class AINotConfigured(AIError):
    error_type = "not_configured"


class AITimeout(AIError):
    error_type = "timeout"


class AIInvalidOutput(AIError):
    error_type = "invalid_output"


class AIProviderError(AIError):
    error_type = "provider_error"


class AIRateLimited(AIProviderError):
    error_type = "rate_limited"


class AIClient(Protocol):
    model: str

    def generate_json(self, *, task: str, system: str, prompt: str, schema: type[T]) -> T: ...


def _schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "Respond with a single JSON object only (no markdown fences) that validates against this JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), separators=(",", ":"))
    )


def parse_model_output(text: str | None, schema: type[T]) -> T:
    if not text or not text.strip():
        raise AIInvalidOutput("The AI provider returned an empty response.")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{"):] if "{" in cleaned else cleaned
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIInvalidOutput("The AI response was not valid JSON.") from exc
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise AIInvalidOutput(f"The AI response did not match the expected structure ({exc.error_count()} errors).") from exc


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: float):
        from google import genai
        from google.genai import types

        self.model = model
        self._types = types
        self._client = genai.Client(
            # Gemini rejects deadlines under 10 s (400 INVALID_ARGUMENT), which would fail every call.
            api_key=api_key, http_options=types.HttpOptions(timeout=int(max(timeout_seconds, 10) * 1000))
        )

    def _generate(self, system: str, prompt: str, schema: type[BaseModel]):
        config = self._types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", temperature=0.1)
        contents = prompt + "\n\n" + _schema_instruction(schema)
        try:
            return self._client.models.generate_content(model=self.model, contents=contents, config=config)
        except Exception as exc:
            if getattr(exc, "code", None) != 503:  # only transient "model overloaded" responses are retried, once
                raise
            log.warning("ai_retry", extra={"model": self.model, "error_type": "unavailable"})
            time.sleep(1.5)
            return self._client.models.generate_content(model=self.model, contents=contents, config=config)

    def generate_json(self, *, task: str, system: str, prompt: str, schema: type[T]) -> T:
        start = time.perf_counter()
        outcome, error_type = "success", None
        try:
            try:
                response = self._generate(system, prompt, schema)
            except Exception as exc:  # provider SDK raises many types; normalise them
                name, msg = type(exc).__name__.lower(), str(exc).lower()
                # Client-side (httpx) timeouts and server-side deadlines (HTTP 504 DEADLINE_EXCEEDED) both count.
                if "timeout" in name or "timed out" in msg or "deadline_exceeded" in msg or getattr(exc, "code", None) == 504:
                    raise AITimeout("The AI provider timed out. Your data was preserved; please retry.") from exc
                if getattr(exc, "code", None) == 429:
                    when = "tomorrow (daily quota)" if "perday" in msg else "in a minute"
                    raise AIRateLimited(f"The AI provider's rate limit or quota was reached. Your data was preserved; "
                                        f"please retry {when}.") from exc
                raise AIProviderError(f"The AI provider returned an error ({type(exc).__name__}).") from exc
            return parse_model_output(getattr(response, "text", None), schema)
        except AIError as exc:
            outcome, error_type = "failure", exc.error_type
            raise
        finally:
            log.info(
                "ai_call",
                extra={
                    "ai_task": task,
                    "model": self.model,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                    "outcome": outcome,
                    "error_type": error_type,
                },
            )


class UnconfiguredClient:
    model = "unconfigured"

    def generate_json(self, *, task: str, system: str, prompt: str, schema: type[T]) -> T:
        log.warning("ai_call", extra={"ai_task": task, "model": None, "outcome": "failure", "error_type": "not_configured"})
        raise AINotConfigured(
            "AI is not configured. Set GEMINI_API_KEY (and optionally GEMINI_MODEL) on the server to enable this feature."
        )


_client: AIClient | None = None


def get_ai_client() -> AIClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = (
            GeminiClient(s.gemini_api_key, s.gemini_model, s.gemini_timeout_seconds)
            if s.ai_configured
            else UnconfiguredClient()
        )
    return _client
