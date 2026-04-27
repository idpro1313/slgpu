"""Логирование исхода HTTP-запросов: метод, путь, статус, длительность, ошибки."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# GRACE [M-WEB][request_log][BLOCK_API_ACCESS]

log = logging.getLogger("app.http")

# Не пишем пачку access при опросе версии/health (фоновый refetch)
_SKIP_PREFIXES: tuple[str, ...] = ("/assets/",)
_SKIP_PATHS: frozenset[str] = frozenset({"/favicon.ico", "/favicon.svg", "/healthz"})


def _path_for_log(request: Request) -> str:
    p = request.url.path
    q = str(request.url.query)
    if not q:
        return p
    s = f"{p}?{q}"
    if len(s) > 500:
        return s[:497] + "…"
    return s


class AppHttpRequestLogMiddleware(BaseHTTPMiddleware):
    """JSON-лог [app][http][BLOCK_API_REQUEST] / BLOCK_API_ERROR для каждого запроса (кроме static/healthz)."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        p = request.url.path
        if p in _SKIP_PATHS or p.startswith(_SKIP_PREFIXES):
            return await call_next(request)
        if p == "/api/v1/app-logs/tail" or p.startswith("/api/v1/app-logs/tail"):
            return await call_next(request)

        t0 = time.perf_counter()
        method = request.method
        sp = _path_for_log(request)

        try:
            response = await call_next(request)
        except Exception as exc:
            # Полный traceback пишет uvicorn/starlette; здесь — кратко, без дубля «ExceptionGroup».
            log.error(
                "[app][http][BLOCK_API_ERROR] method=%s path=%s err=%s",
                method,
                sp,
                exc,
            )
            raise
        else:
            status = int(response.status_code)
            ms = (time.perf_counter() - t0) * 1000.0
            if status >= 500:
                log.error(
                    "[app][http][BLOCK_API_REQUEST] method=%s path=%s status=%s duration_ms=%.1f",
                    method,
                    sp,
                    status,
                    ms,
                )
            else:
                log.info(
                    "[app][http][BLOCK_API_REQUEST] method=%s path=%s status=%s duration_ms=%.1f",
                    method,
                    sp,
                    status,
                    ms,
                )
            return response
