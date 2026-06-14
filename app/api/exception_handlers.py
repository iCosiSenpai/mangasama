"""Domain exception → HTTP JSON mapping.

The boundary catches our typed exceptions and our non-`MangaSamaError`
sentinels (`ValueError`) and turns them into structured JSON. Anything
else falls through to FastAPI's default 500 handler.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    BlockedByCloudflare,
    ChapterNotFound,
    ChapterNotFoundDB,
    ConfigError,
    LibraryNotFound,
    MangaSamaError,
    RateLimited,
    SeriesNotFound,
    SeriesNotFoundDB,
    SourceUnavailable,
)


def _payload(detail: str, type_: str, **extra) -> dict:
    body = {"detail": detail, "type": type_}
    body.update(extra)
    return body


async def domain_exception_handler(
    request: Request, exc: Exception,
) -> JSONResponse:
    """Single handler that covers every MangaSama-specific exception."""
    if isinstance(exc, LibraryNotFound):
        return JSONResponse(
            status_code=404,
            content=_payload(str(exc), "library_not_found"),
        )
    if isinstance(exc, (SeriesNotFoundDB, SeriesNotFound)):
        return JSONResponse(
            status_code=404,
            content=_payload(str(exc), "series_not_found"),
        )
    if isinstance(exc, (ChapterNotFoundDB, ChapterNotFound)):
        return JSONResponse(
            status_code=404,
            content=_payload(str(exc), "chapter_not_found"),
        )
    if isinstance(exc, RateLimited):
        retry_after = getattr(exc, "retry_after", None)
        headers = {"Retry-After": str(int(retry_after))} if retry_after else None
        return JSONResponse(
            status_code=429,
            content=_payload(str(exc), "rate_limited", retry_after=retry_after),
            headers=headers,
        )
    if isinstance(exc, BlockedByCloudflare):
        return JSONResponse(
            status_code=502,
            content=_payload(
                str(exc), "blocked_by_cloudflare",
                source=getattr(exc, "source", None),
            ),
        )
    if isinstance(exc, SourceUnavailable):
        return JSONResponse(
            status_code=502,
            content=_payload(
                str(exc), "source_unavailable",
                source=getattr(exc, "source", None),
                status_code=getattr(exc, "status_code", None),
            ),
        )
    if isinstance(exc, ConfigError):
        return JSONResponse(
            status_code=400,
            content=_payload(str(exc), "config_error"),
        )
    if isinstance(exc, ValueError):
        return JSONResponse(
            status_code=400,
            content=_payload(str(exc), "invalid_value"),
        )
    if isinstance(exc, MangaSamaError):
        return JSONResponse(
            status_code=500,
            content=_payload(str(exc), "internal_error"),
        )
    # Last resort: let FastAPI's default handle it (will 500).
    return JSONResponse(
        status_code=500,
        content=_payload(str(exc) or exc.__class__.__name__, "unhandled"),
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Register handlers for our typed exceptions + `ValueError`."""
    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(MangaSamaError, domain_exception_handler)
    app.add_exception_handler(ValueError, domain_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface Pydantic / FastAPI validation errors as 400."""
    from fastapi.exceptions import RequestValidationError

    assert isinstance(exc, RequestValidationError)
    # `exc.errors()` is a list of {loc, msg, type, ...}; flatten to a
    # human-friendly message but keep the structured `errors` for clients.
    return JSONResponse(
        status_code=400,
        content={
            "detail": "request validation failed",
            "type": "validation_error",
            "errors": exc.errors(),
        },
    )
