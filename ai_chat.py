# -*- coding: utf-8 -*-
"""Единая точка вызова LLM: локальная модель (llama-cpp-python, GGUF D:\model\llm_model.gguf).

Провайдер один — локальная LLM. Без ключей, без сети, без fallback-провайдеров.
"""
from __future__ import annotations

import logging

from paths import read_config_json

logger = logging.getLogger(__name__)

PROVIDER_LOCAL = "local"

DEFAULT_TEMPERATURE = 0.75
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0


class ChatProviderError(Exception):
    """Ошибка локальной LLM."""


def get_temperature() -> float:
    raw = read_config_json().get("ai_temperature", DEFAULT_TEMPERATURE)
    try:
        t = float(raw)
    except (TypeError, ValueError):
        t = DEFAULT_TEMPERATURE
    return max(TEMPERATURE_MIN, min(TEMPERATURE_MAX, t))


def get_provider() -> str:
    return PROVIDER_LOCAL


def has_active_key() -> bool:
    return True


def _local_chat(messages: list[dict], *, timeout: int) -> str:
    from local_llm import chat_completion as local_chat

    try:
        logger.info("Локальная LLM: отправка запроса...")
        return local_chat(messages, timeout=timeout, temperature=get_temperature())
    except Exception as e:
        raise ChatProviderError(f"Ошибка локальной LLM: {e}") from e


def chat_stream(
    messages: list[dict],
    *,
    timeout: int = 120,
    temperature: float | None = None,
):
    """Стриминг ответа локальной модели по кусочкам."""
    from local_llm import chat_completion_stream as local_stream

    temp = get_temperature() if temperature is None else temperature
    try:
        got_any = False
        for token in local_stream(messages, temperature=temp):
            if token:
                got_any = True
                yield token
        if not got_any:
            raise ChatProviderError("Ошибка локальной LLM: модель не вернула ни одного токена")
    except ChatProviderError:
        raise
    except Exception as e:
        raise ChatProviderError(f"Ошибка локальной LLM: {e}") from e


def chat(
    messages: list[dict],
    *,
    model_hint: str | None = None,
    timeout: int = 60,
    nsfw: bool = False,
    model_override: str | None = None,
) -> str:
    return _local_chat(messages, timeout=timeout)


def chat_short(
    messages: list[dict],
    *,
    model_hint: str | None = None,
    timeout: int = 30,
    nsfw: bool = False,
    model_override: str | None = None,
) -> str:
    return _local_chat(messages, timeout=timeout)