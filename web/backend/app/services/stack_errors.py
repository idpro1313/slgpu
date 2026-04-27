"""Errors for strict stack validation (no silent defaults from code)."""

from __future__ import annotations


class MissingStackParams(Exception):
    """One or more required stack_params keys are missing or empty for this scope."""

    def __init__(self, keys: list[str], scope: str) -> None:
        self.keys = list(keys)
        self.scope = scope
        super().__init__(f"missing stack params for {scope}: {keys}")
