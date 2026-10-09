# -*- coding: utf-8 -*-
"""Р›РѕРєР°Р»СЊРЅР°СЏ LLM С‡РµСЂРµР· llama-cpp-python (GGUF D:\model\llm_model.gguf).

Р‘РµР· РєР»СЋС‡РµР№ Рё Р±РµР· СЃРµС‚Рё. РўРµ Р¶Рµ РїСЂРѕРјРїС‚С‹/РЅР°СЃС‚СЂРѕР№РєРё, С‡С‚Рѕ Рё Сѓ РѕРЅР»Р°Р№РЅ-РїСЂРѕРІР°Р№РґРµСЂРѕРІ,
РїСЂРѕСЃС‚Рѕ Р·Р°РїСЂРѕСЃ РІС‹РїРѕР»РЅСЏРµС‚СЃСЏ РЅР° СЃРІРѕРµР№ РјР°С€РёРЅРµ С‡РµСЂРµР· Р»РѕРєР°Р»СЊРЅСѓСЋ РјРѕРґРµР»СЊ.
"""
from __future__ import annotations

import logging
import threading

from paths import read_config_json

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = r"D:\model\llm_model.gguf"
DEFAULT_MODEL_NAME = "llm_local"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_N_CTX = 8192
DEFAULT_REPETITION_PENALTY = 1.15
REPETITION_PENALTY_MIN = 1.0
REPETITION_PENALTY_MAX = 2.0

_llm = None
_llm_lock = threading.Lock()


def _model_path() -> str:
    p = (read_config_json().get("local_llm_path") or "").strip()
    return p or DEFAULT_MODEL_PATH


def has_model() -> bool:
    return bool(_model_path().strip())


def _gpu_layers() -> int:
    v = read_config_json().get("local_llm_gpu_layers")
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = -1
    return n if n >= -1 else -1


def _ctx_limit() -> int:
    """Р Р°Р·РјРµСЂ РєРѕРЅС‚РµРєСЃС‚РЅРѕРіРѕ РѕРєРЅР° РјРѕРґРµР»Рё (РЅР°СЃС‚СЂР°РёРІР°РµС‚СЃСЏ С‡РµСЂРµР· config.json В«local_llm_ctxВ»)."""
    v = read_config_json().get("local_llm_ctx")
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = DEFAULT_N_CTX
    return max(2048, min(65536, n))


def _repetition_penalty() -> float:
    v = read_config_json().get("local_llm_repetition_penalty")
    try:
        n = float(v)
    except (TypeError, ValueError):
        n = DEFAULT_REPETITION_PENALTY
    return max(REPETITION_PENALTY_MIN, min(REPETITION_PENALTY_MAX, n))


def context_limit() -> int:
    return _ctx_limit()


def _get_llm():
    global _llm
    with _llm_lock:
        if _llm is None:
            from llama_cpp import Llama

            path = _model_path()
            n_gpu = _gpu_layers()
            n_ctx = _ctx_limit()
            logger.info("Р›РѕРєР°Р»СЊРЅР°СЏ LLM: Р·Р°РіСЂСѓР·РєР° РјРѕРґРµР»Рё %s (gpu_layers=%s, ctx=%s) ...", path, n_gpu, n_ctx)
            _llm = Llama(
                model_path=path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu,
                verbose=False,
            )
            logger.info("Р›РѕРєР°Р»СЊРЅР°СЏ LLM: РјРѕРґРµР»СЊ РіРѕС‚РѕРІР° (ctx=%s, gpu=%s)", n_ctx, n_gpu)
    return _llm


def chat_completion(
    messages: list[dict],
    *,
    timeout: int = 60,
    temperature: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """РџРѕР»РЅС‹Р№ РґРёР°Р»РѕРі (РЅРµ РїРѕС‚РѕРєРѕРІС‹Р№) С‡РµСЂРµР· Р»РѕРєР°Р»СЊРЅСѓСЋ GGUF-РјРѕРґРµР»СЊ."""
    temp = 0.75 if temperature is None else temperature
    try:
        llm = _get_llm()
        resp = llm.create_chat_completion(
            messages=messages,
            temperature=max(0.0, min(2.0, float(temp))),
            repeat_penalty=_repetition_penalty(),
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.warning("Р›РѕРєР°Р»СЊРЅР°СЏ LLM: РѕС€РёР±РєР° Р·Р°РїСЂРѕСЃР°: %s", e)
        raise RuntimeError(f"Р›РѕРєР°Р»СЊРЅР°СЏ LLM: {e}") from e

    try:
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        logger.warning("Р›РѕРєР°Р»СЊРЅР°СЏ LLM: РЅРµРѕР¶РёРґР°РЅРЅР°СЏ СЃС‚СЂСѓРєС‚СѓСЂР° РѕС‚РІРµС‚Р°: %s", str(resp)[:500])
        raise RuntimeError("Р›РѕРєР°Р»СЊРЅР°СЏ LLM РІРµСЂРЅСѓР»Р° РЅРµРѕР¶РёРґР°РЅРЅСѓСЋ СЃС‚СЂСѓРєС‚СѓСЂСѓ РѕС‚РІРµС‚Р°.")

    if not text:
        raise RuntimeError("Р›РѕРєР°Р»СЊРЅР°СЏ LLM РІРµСЂРЅСѓР»Р° РїСѓСЃС‚РѕР№ РѕС‚РІРµС‚.")

    logger.info("Р›РѕРєР°Р»СЊРЅР°СЏ LLM РѕС‚РІРµС‚ (rep_pen=%.2f): %s", _repetition_penalty(), text)
    return text


def chat_completion_stream(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
):
    """Р“РµРЅРµСЂР°С‚РѕСЂ РєСѓСЃРєРѕРІ С‚РµРєСЃС‚Р° РїРѕ РјРµСЂРµ РіРµРЅРµСЂР°С†РёРё (Р»РѕРєР°Р»СЊРЅР°СЏ GGUF)."""
    temp = 0.75 if temperature is None else temperature
    llm = _get_llm()
    logger.info("Р›РѕРєР°Р»СЊРЅР°СЏ LLM stream: РЅР°С‡Р°Р»Рѕ РѕС‚РІРµС‚Р°...")
    try:
        for chunk in llm.create_chat_completion(
            messages=messages,
            temperature=max(0.0, min(2.0, float(temp))),
            repeat_penalty=_repetition_penalty(),
            max_tokens=max_tokens,
            stream=True,
        ):
            delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
    except Exception as e:
        logger.warning("Р›РѕРєР°Р»СЊРЅР°СЏ LLM stream: РѕС€РёР±РєР°: %s", e)
        raise RuntimeError(f"Р›РѕРєР°Р»СЊРЅР°СЏ LLM: {e}") from e


def warmup(delay_sec: float = 2.5) -> None:
    """Р¤РѕРЅРѕРІС‹Р№ РїСЂРѕРіСЂРµРІ: Р·Р°РіСЂСѓР·РёС‚СЊ РјРѕРґРµР»СЊ Р·Р°СЂР°РЅРµРµ, С‡С‚РѕР±С‹ РїРµСЂРІР°СЏ РѕР·РІСѓС‡РєР° Р±С‹Р»Р° Р±С‹СЃС‚СЂРµРµ."""
    import time

    time.sleep(delay_sec)
    try:
        _get_llm()
        logger.info("Р›РѕРєР°Р»СЊРЅР°СЏ LLM: РїСЂРѕРіСЂРµРІ Р·Р°РІРµСЂС€С‘РЅ")
    except Exception as e:
        logger.debug("Р›РѕРєР°Р»СЊРЅР°СЏ LLM warmup РїСЂРѕРїСѓС‰РµРЅРѕ: %s", e)