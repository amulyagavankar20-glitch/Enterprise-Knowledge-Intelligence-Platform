"""JSON request logs and non-sensitive default response hardening."""

import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        item = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "error_type", "scope", "action"):
            value = getattr(record, key, None)
            if value is not None:
                item[key] = value
        return json.dumps(item, separators=(",", ":"), ensure_ascii=False)


def _request_logger() -> logging.Logger:
    logger = logging.getLogger("eki.request")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def install_observability(app: FastAPI) -> None:
    logger = _request_logger()

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            if request.url.path in {"/", "/index.html", "/app.css", "/app.js"}:
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                    "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
                    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
                )
            return response
        finally:
            logger.info(
                "http_request_complete",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    # Deliberately omit query strings and request/response bodies.
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )

    @app.exception_handler(Exception)
    async def safe_unhandled_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled_request_exception",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred.",
                "request_id": request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def safe_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic's default error may include the raw submitted value. Return
        # locations and validation types only, never passwords or form content.
        errors = [
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", "Invalid value."),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": errors, "request_id": getattr(request.state, "request_id", "unknown")},
        )
