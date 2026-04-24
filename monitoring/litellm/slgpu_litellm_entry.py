#!/usr/bin/env python3
"""
Обёртка вокруг LiteLLM proxy: до импорта сервера патчим Langfuse OTEL config.
Langfuse 3 ожидает x-langfuse-ingestion-version=4; в litellm передаётся только Authorization.
См. https://langfuse.com/integrations/native/opentelemetry
"""
from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any, Optional


def _fix_open_telemetry_config_headers(c: Any) -> Any:
    if c is None:
        return None
    h = getattr(c, "headers", None) or ""
    if "x-langfuse-ingestion-version" in h:
        return c
    new_h = h + ("," if h else "") + "x-langfuse-ingestion-version=4"
    return replace(c, headers=new_h)


def _apply_langfuse_otel_ingestion_header_patch() -> None:
    try:
        from litellm.integrations.langfuse import langfuse_otel as m
    except Exception:
        return

    cls = m.LangfuseOtelLogger

    _orig_create = cls._create_open_telemetry_config_from_langfuse_env

    def _patched_create(self: Any) -> Any:
        return _fix_open_telemetry_config_headers(_orig_create(self))

    cls._create_open_telemetry_config_from_langfuse_env = _patched_create

    if hasattr(cls, "get_langfuse_otel_config"):
        gf = cls.get_langfuse_otel_config
        if isinstance(gf, staticmethod):
            _orig_get = gf.__func__

            @staticmethod
            def _patched_get() -> Any:
                return _fix_open_telemetry_config_headers(_orig_get())

            cls.get_langfuse_otel_config = _patched_get  # type: ignore[method-assign]


def main(argv: Optional[list[str]] = None) -> None:
    if argv is not None:
        sys.argv = argv
    _apply_langfuse_otel_ingestion_header_patch()
    from litellm.proxy.proxy_cli import run_server

    sys.argv[0] = "litellm"
    run_server()


if __name__ == "__main__":
    main()
