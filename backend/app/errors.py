from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from .ai.client import AIError, AIInvalidOutput, AINotConfigured, AIRateLimited, AITimeout
from .logging_setup import get_logger, request_id_var

log = get_logger("errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | list | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(entity: str, entity_id) -> AppError:
    return AppError(404, "not_found", f"{entity} {entity_id} was not found in this project.")


def conflict(code: str, message: str, details=None) -> AppError:
    return AppError(409, code, message, details)


def bad_request(code: str, message: str, details=None) -> AppError:
    return AppError(422, code, message, details)


def _body(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details, "request_id": request_id_var.get()}},
    )


def ai_error_response(exc: AIError) -> JSONResponse:
    if isinstance(exc, AINotConfigured):
        return _body(503, "ai_not_configured", str(exc))
    if isinstance(exc, AITimeout):
        return _body(504, "ai_timeout", str(exc))
    if isinstance(exc, AIRateLimited):
        return _body(503, "ai_rate_limited", str(exc))
    if isinstance(exc, AIInvalidOutput):
        return _body(502, "ai_invalid_output", str(exc))
    return _body(502, "ai_provider_error", str(exc))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return _body(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(AIError)
    async def _ai_error(_: Request, exc: AIError):
        return ai_error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return _body(422, "validation_error", "The request was invalid.", details)

    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, exc: StaleDataError):
        log.warning("stale_update_rejected")
        return _body(409, "version_conflict", "This record was changed by someone else. Reload and try again.")

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        log.warning("db_integrity_error", extra={"error_type": type(exc.orig).__name__ if exc.orig else None})
        return _body(409, "integrity_conflict", "The operation conflicts with existing records (duplicate or invalid state).")

    @app.exception_handler(SQLAlchemyError)
    async def _db(_: Request, exc: SQLAlchemyError):
        log.error("db_error", extra={"error_type": type(exc).__name__})
        return _body(500, "database_error", "A database error occurred. No partial changes were saved.")
