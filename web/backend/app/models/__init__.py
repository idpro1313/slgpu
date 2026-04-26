"""ORM models for slgpu-web."""

from app.models.audit import AuditEvent
from app.models.job import Job, JobStatus
from app.models.model import HFModel, ModelDownloadStatus
from app.models.preset import Preset
from app.models.service import ServiceState, ServiceStatus
from app.models.setting import Setting
from app.models.stack_param import StackParam
from app.models.slot import EngineSlot, RunStatus

__all__ = [
    "AuditEvent",
    "EngineSlot",
    "HFModel",
    "Job",
    "JobStatus",
    "ModelDownloadStatus",
    "Preset",
    "RunStatus",
    "ServiceState",
    "ServiceStatus",
    "Setting",
    "StackParam",
]
