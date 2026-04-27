"""Smoke tests: configs/main.env covers all canonical stack registry keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.stack_config import parse_dotenv_text
from app.services.stack_registry import STACK_KEY_REGISTRY


REPO_ROOT = Path(__file__).resolve().parents[3]
MAIN_ENV = REPO_ROOT / "configs" / "main.env"


@pytest.mark.skipif(not MAIN_ENV.is_file(), reason="configs/main.env missing")
def test_main_env_covers_registry_keys() -> None:
    """Every canonical key (incl. allow_empty) must be present in main.env."""
    flat = parse_dotenv_text(MAIN_ENV.read_text(encoding="utf-8"))
    missing = [k for k in STACK_KEY_REGISTRY if k not in flat]
    assert not missing, (
        "configs/main.env is the canonical UI import template — "
        f"missing registry keys: {sorted(missing)}"
    )


@pytest.mark.skipif(not MAIN_ENV.is_file(), reason="configs/main.env missing")
def test_main_env_required_keys_have_values() -> None:
    """Required (non allow_empty) registry keys must have non-empty values in main.env."""
    flat = parse_dotenv_text(MAIN_ENV.read_text(encoding="utf-8"))
    blank: list[str] = []
    for key, meta in STACK_KEY_REGISTRY.items():
        if meta.allow_empty:
            continue
        v = flat.get(key, "").strip()
        if not v:
            blank.append(key)
    assert not blank, (
        "configs/main.env: required registry keys are blank: "
        f"{sorted(blank)}"
    )
