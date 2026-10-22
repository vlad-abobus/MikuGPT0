# -*- coding: utf-8 -*-
"""Единая точка вызова LLM: Google Gemini API (gemini-3.5-flash-lite).

Провайдер один — Gemini. Ключ и все настройки запроса берутся из api_gem.txt.
"""
from __future__ import annotations

import logging

from paths import read_config_json

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"

DEFAULT_TEMPERATURE = 0.75
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0


class ChatProviderError(Exception):
    """Ошибка Gemini API."""


def get_temperature() -> float:
    raw = read_config_json().get("ai_temperature", DEFAULT_TEMPERATURE)
    try:
        t = float(raw)
    except (TypeError, ValueError):
        t = DEFAULT_TEMPERATURE
    return max(TEMPERATURE_MIN, min(TEMPERATURE_MAX, t))


def get_provider() -> str:
    return PROVIDER_GEMINI


def has_active_key() -> bool:
    from gemini_client import has_key

    return has_key()


def _gemini_chat(messages: list[dict], *, timeout: int) -> str:
    from gemini_client import chat_completion as gemini_chat

    try:
        logger.info("Gemini: отправка запроса...")
        return gemini_chat(messages, timeout=timeout, temperature=get_temperature())
    except Exception as e:
        raise ChatProviderError(f"Ошибка Gemini API: {e}") from e


def chat_stream(
    messages: list[dict],
    *,
    timeout: int = 120,
    temperature: float | None = None,
):
    """Стриминг ответа Gemini по кусочкам."""
    from gemini_client import chat_completion_stream as gemini_stream

    temp = get_temperature() if temperature is None else temperature
    try:
        got_any = False
        for token in gemini_stream(messages, temperature=temp):
            if token:
                got_any = True
                yield token
        if not got_any:
            raise ChatProviderError("Ошибка Gemini API: модель не вернула ни одного токена")
    except ChatProviderError:
        raise
    except Exception as e:
        raise ChatProviderError(f"Ошибка Gemini API: {e}") from e


def chat(
    messages: list[dict],
    *,
    model_hint: str | None = None,
    timeout: int = 60,
    nsfw: bool = False,
    model_override: str | None = None,
) -> str:
    return _gemini_chat(messages, timeout=timeout)


def chat_short(
    messages: list[dict],
    *,
    model_hint: str | None = None,
    timeout: int = 30,
    nsfw: bool = False,
    model_override: str | None = None,
) -> str:
    return _gemini_chat(messages, timeout=timeout)
