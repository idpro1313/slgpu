"""Version 1 of the slgpu-web API."""

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    app_config,
    bench,
    dashboard,
    docker_logs,
    gpu,
    jobs,
    litellm,
    models,
    monitoring,
    presets,
    runtime,
    settings,
)

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(presets.router, prefix="/presets", tags=["presets"])
api_router.include_router(gpu.router, prefix="/gpu", tags=["gpu"])
api_router.include_router(runtime.router, prefix="/runtime", tags=["runtime"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(litellm.router, prefix="/litellm", tags=["litellm"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(app_config.router, prefix="/app-config", tags=["app-config"])
api_router.include_router(bench.router, prefix="/bench", tags=["bench"])
api_router.include_router(
    docker_logs.router, prefix="/docker", tags=["docker-logs"]
)
