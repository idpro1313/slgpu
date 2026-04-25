"""FastAPI application entry point.

The single container ships both the HTTP API and the React frontend.
- `/api/v1/*` is served by the routers below.
- Anything else is served from `WEB_STATIC_DIR` if it points to the
  built React assets, otherwise we return a 404.
"""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db
from app.schemas.common import HealthResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging("INFO")

    app = FastAPI(title=settings.app_name, version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/healthz", response_model=HealthResponse, tags=["health"])
    async def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            slgpu_root=str(settings.slgpu_root),
            database_url_masked=_mask_db_url(settings.database_url),
        )

    @app.on_event("startup")
    async def _startup() -> None:
        try:
            await init_db()
            logger.info("[main][startup] db initialised")
        except Exception:
            logger.exception("[main][startup] db init failed; continuing")

    if settings.static_dir and settings.static_dir.exists():
        _mount_spa(app, settings.static_dir)

    return app


def _mask_db_url(url: str) -> str:
    return re.sub(r"://[^@]+@", "://***@", url)


def _mount_spa(app: FastAPI, static_dir) -> None:
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get(
        "/{full_path:path}",
        include_in_schema=False,
        response_model=None,
    )
    async def spa_fallback(full_path: str, request: Request) -> FileResponse | JSONResponse:
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "not found"}, status_code=404)
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"detail": "frontend not built"}, status_code=404)


app = create_app()
