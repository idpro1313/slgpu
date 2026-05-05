"""Реестр стека: необязательные SGLang-флаги MiMo DP / multi-layer EAGLE (8.2.16)."""

from app.services.stack_registry import STACK_KEY_REGISTRY

_SGL_OPTIONAL = (
    "SGLANG_ENABLE_DP_ATTENTION",
    "SGLANG_ENABLE_DP_LM_HEAD",
    "SGLANG_MM_ENABLE_DP_ENCODER",
    "SGLANG_ENABLE_MULTI_LAYER_EAGLE",
)


def test_sgl_mi_mo_dp_flags_are_allow_empty_for_stack_registry() -> None:
    for k in _SGL_OPTIONAL:
        meta = STACK_KEY_REGISTRY[k]
        assert meta.allow_empty is True, k
        assert "llm_slot" in meta.required_for, k
