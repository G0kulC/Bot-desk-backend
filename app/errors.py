from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    502: "provider_error",
    503: "unavailable",
}


class AppError(Exception):
    """Raise anywhere in request handling to return {"error": {"code", "message"}}."""

    def __init__(self, status_code: int, code: str, message: str, details: object | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def not_found(entity: str) -> AppError:
    return AppError(404, "not_found", f"{entity} not found")


def _body(code: str, message: str, details: object | None = None) -> dict:
    err: dict = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(
            _body(code, message), status_code=exc.status_code, headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(_body("validation_error", "Invalid request", details), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", exc_info=exc)
        return JSONResponse(_body("internal_error", "Something went wrong"), status_code=500)


__all__ = ["AppError", "HTTPException", "install_error_handlers", "not_found"]
