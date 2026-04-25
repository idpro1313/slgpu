"""Version 1 of the slgpu-web API."""

from fastapi import APIRouter

from app.api.v1 import dashboard, jobs, litellm, models, monitoring, presets, runtime

api_router = APIRouter()
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(presets.router, prefix="/presets", tags=["presets"])
api_router.include_router(runtime.router, prefix="/runtime", tags=["runtime"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(litellm.router, prefix="/litellm", tags=["litellm"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
