# -*- coding: utf-8 -*-
"""Локальная LLM через llama-cpp-python (GGUF D:\model\llm_model.gguf).

Без ключей и без сети. Те же промпты/настройки, что и у онлайн-провайдеров,
просто запрос выполняется на своей машине через локальную модель.
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
    """Размер контекстного окна модели (настраивается через config.json «local_llm_ctx»)."""
    v = read_config_json().get("local_llm_ctx")
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = DEFAULT_N_CTX
    return max(2048, min(65536, n))


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
            logger.info("Локальная LLM: загрузка модели %s (gpu_layers=%s, ctx=%s) ...", path, n_gpu, n_ctx)
            _llm = Llama(
                model_path=path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu,
                verbose=False,
            )
            logger.info("Локальная LLM: модель готова (ctx=%s, gpu=%s)", n_ctx, n_gpu)
    return _llm


def chat_completion(
    messages: list[dict],
    *,
    timeout: int = 60,
    temperature: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Полный диалог (не потоковый) через локальную GGUF-модель."""
    temp = 0.75 if temperature is None else temperature
    try:
        llm = _get_llm()
        resp = llm.create_chat_completion(
            messages=messages,
            temperature=max(0.0, min(2.0, float(temp))),
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.warning("Локальная LLM: ошибка запроса: %s", e)
        raise RuntimeError(f"Локальная LLM: {e}") from e

    try:
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        logger.warning("Локальная LLM: неожиданная структура ответа: %s", str(resp)[:500])
        raise RuntimeError("Локальная LLM вернула неожиданную структуру ответа.")

    if not text:
        raise RuntimeError("Локальная LLM вернула пустой ответ.")

    logger.info("Локальная LLM ответ: %s", text)
    return text


def chat_completion_stream(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
):
    """Генератор кусков текста по мере генерации (локальная GGUF)."""
    temp = 0.75 if temperature is None else temperature
    llm = _get_llm()
    logger.info("Локальная LLM stream: начало ответа...")
    try:
        for chunk in llm.create_chat_completion(
            messages=messages,
            temperature=max(0.0, min(2.0, float(temp))),
            max_tokens=max_tokens,
            stream=True,
        ):
            delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
    except Exception as e:
        logger.warning("Локальная LLM stream: ошибка: %s", e)
        raise RuntimeError(f"Локальная LLM: {e}") from e


def warmup(delay_sec: float = 2.5) -> None:
    """Фоновый прогрев: загрузить модель заранее, чтобы первая озвучка была быстрее."""
    import time

    time.sleep(delay_sec)
    try:
        _get_llm()
        logger.info("Локальная LLM: прогрев завершён")
    except Exception as e:
        logger.debug("Локальная LLM warmup пропущено: %s", e)