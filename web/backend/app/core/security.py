"""Validation helpers for arguments forwarded to the slgpu CLI.

Anything that ends up on a command line MUST pass through one of these
validators. Failing fast here is the primary defence against shell
injection and accidental destructive commands.
"""

from __future__ import annotations

import re

_HF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*\/[A-Za-z0-9._\-]+$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._\-]{0,63}$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9._\-/]{1,128}$")
_ENGINE_VALUES = frozenset({"vllm", "sglang"})


class ValidationError(ValueError):
    """Raised when an argument fails the strict allowlist."""


def validate_engine(value: str) -> str:
    if value not in _ENGINE_VALUES:
        raise ValidationError(f"engine must be one of {sorted(_ENGINE_VALUES)}, got {value!r}")
    return value


def validate_slug(value: str) -> str:
    if not _SLUG_RE.match(value):
        raise ValidationError(f"slug {value!r} is not a valid preset name")
    return value


def validate_slot_key(value: str) -> str:
    """Slot id for inference instances (same rules as preset slug)."""
    return validate_slug(value)


def validate_hf_id(value: str) -> str:
    if not _HF_ID_RE.match(value):
        raise ValidationError(f"hf id {value!r} must look like 'org/repo'")
    return value


def validate_slug_or_hf_id(value: str) -> str:
    if "/" in value:
        return validate_hf_id(value)
    return validate_slug(value)


def validate_port(value: int) -> int:
    if not isinstance(value, int) or value < 1 or value > 65535:
        raise ValidationError(f"port {value!r} must be 1..65535")
    return value


def validate_tp(value: int) -> int:
    if not isinstance(value, int) or value < 1 or value > 128:
        raise ValidationError(f"tp {value!r} must be 1..128")
    return value


def validate_revision(value: str) -> str:
    if not _REVISION_RE.match(value):
        raise ValidationError(f"revision {value!r} contains forbidden characters")
    return value
