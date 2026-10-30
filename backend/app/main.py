import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .errors import register_error_handlers
from .logging_setup import configure_logging, get_logger, request_id_var
from .routers.api import router

settings = get_settings()
configure_logging(settings.log_file_path, settings.log_level)
log = get_logger("http")

@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("app_starting", extra={"ai_configured": settings.ai_configured, "model": settings.gemini_model,
                                    "log_file": settings.log_file_path})
    if settings.seed_demo_data:
        from .db import SessionLocal
        from .seed import seed_if_empty

        with SessionLocal() as db:
            log.info("demo_seed_checked", extra={"seeded": seed_if_empty(db)})
    yield


app = FastAPI(
    lifespan=lifespan,
    title="RELAY API",
    version="1.0.0",
    description="AI-Powered Knowledge Integrity & Work Continuity Platform. "
    "All AI output is a draft until a human approves it.",
)
register_error_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    is_api = request.url.path.startswith("/api")
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request_failed", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse(status_code=500, content={"error": {
            "code": "internal_error", "message": "Unexpected server error.", "details": None, "request_id": rid}})
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    if is_api:
        log.info("request_completed", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                                             "status_code": response.status_code,
                                             "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


app.include_router(router)

# Serve the built React app from the same origin so the browser only talks to /api.
dist = Path(settings.frontend_dist)
if (dist / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Unknown API route.",
                                                                    "details": None, "request_id": request_id_var.get()}})
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_frontend():
        return {"message": "RELAY API is running. Frontend build not found; run `npm run build` in frontend/.",
                "docs": "/docs"}
