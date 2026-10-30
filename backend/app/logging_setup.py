"""Structured JSON logging with a per-request correlation ID.

Every record is written as one JSON object per line to stdout and to LOG_FILE_PATH.
Callers pass structured fields through `extra={...}`; never log secrets or full meeting notes.
"""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}
_REDACT_KEYS = {"api_key", "gemini_api_key", "password", "secret", "authorization", "raw_notes", "content_text"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = "[redacted]" if key.lower() in _REDACT_KEYS else value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def configure_logging(log_file_path: str, level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    formatter = JsonFormatter()
    root = logging.getLogger("relay")
    root.setLevel(level.upper())
    root.propagate = False

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    root.addHandler(stdout)

    try:
        path = Path(log_file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:  # unwritable path must not stop the app
        root.warning("log_file_unavailable", extra={"path": log_file_path, "error_type": type(exc).__name__})
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"relay.{name}")
