"""Синхронное чтение пресета из SQLite (без async session) для merge_llm_stack_env / slot_runtime."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.core.config import get_settings
from app.services.stack_config import sqlite_path_from_database_url


def load_preset_flat_from_db_sync(preset_name: str) -> dict[str, str] | None:
    """Вернуть плоский dict для слияния со стеком либо ``None``, если пресета нет в БД."""
    p = sqlite_path_from_database_url(get_settings().database_url)
    if p is None or not p.is_file():
        return None
    conn = sqlite3.connect(str(p))
    try:
        row = conn.execute(
            "SELECT hf_id, tp, served_model_name, parameters FROM presets WHERE name = ?",
            (preset_name,),
        ).fetchone()
        if not row:
            return None
        hf_id, tp, served, parameters_raw = row
        out: dict[str, str] = {}
        params: dict[str, Any] = {}
        if parameters_raw:
            if isinstance(parameters_raw, str):
                try:
                    params = json.loads(parameters_raw)
                except json.JSONDecodeError:
                    params = {}
            elif isinstance(parameters_raw, dict):
                params = parameters_raw
        # Сначала импортированные ключи (.env → parameters), затем столбцы пресета в БД:
        # иначе устаревший ``TP`` из файла-примера перезаписывал TP/tp/gpu_mask из UI
        # (слот с TP=2 и двумя GPU получал tensor_parallel_size=8).
        for k, v in params.items():
            if v is None or str(v).strip() == "":
                continue
            out[str(k)] = str(v)
        if hf_id:
            out["MODEL_ID"] = str(hf_id)
        if tp is not None:
            out["TP"] = str(int(tp))
        if served:
            out["SERVED_MODEL_NAME"] = str(served)
        return out
    finally:
        conn.close()
