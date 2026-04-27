"""Классификация log records для таблицы ``app_log_event``."""

from __future__ import annotations

import logging
import sys

from app.services.app_log_sink import classify_record_to_dto


def _make_record(
    name: str, level: int, msg: str, **extras: object
) -> logging.LogRecord:
    r = logging.LogRecord(
        name=name,
        level=level,
        pathname="x.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extras.items():
        setattr(r, k, v)
    return r


def test_classify_app_http_request() -> None:
    r = _make_record(
        "app.http",
        logging.INFO,
        "[app][http][BLOCK_API_REQUEST] m",
        method="GET",
        path="/api/v1/jobs",
        status=200,
        duration_ms=1.0,
        request_id="a" * 32,
    )
    d = classify_record_to_dto(r)
    assert d.event_kind == "http_request"
    assert d.http_method == "GET"
    assert d.http_path == "/api/v1/jobs"
    assert d.status_code == 200
    assert d.request_id == "a" * 32


def test_classify_app_http_error() -> None:
    r = _make_record(
        "app.http",
        logging.ERROR,
        "[app][http][BLOCK_API_ERROR] m",
        method="GET",
        path="/api/v1/x",
    )
    d = classify_record_to_dto(r)
    assert d.event_kind == "http_error"


def test_classify_app_warning() -> None:
    r = _make_record("app.services.stack_config", logging.WARNING, "w", exc_info=None)
    d = classify_record_to_dto(r)
    assert d.event_kind == "app_warning"


def test_classify_main_lifecycle() -> None:
    r = _make_record("app.main", logging.INFO, "[main][create_app] x")
    d = classify_record_to_dto(r)
    assert d.event_kind == "app_lifecycle"


def test_classify_with_exc() -> None:
    try:
        1 / 0
    except ZeroDivisionError:
        r = _make_record("app", logging.ERROR, "e")
        r.exc_info = sys.exc_info()
    d = classify_record_to_dto(r)
    assert d.event_kind == "app_error"
    assert d.exc_summary
    assert "ZeroDivision" in d.exc_summary
