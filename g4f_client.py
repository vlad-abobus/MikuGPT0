# -*- coding: utf-8 -*-
"""Fallback через g4f (бесплатные провайдеры без API-ключа)."""
from __future__ import annotations

import logging

from g4f.client import Client

logger = logging.getLogger(__name__)

# Провайдеры без API-ключа: рабочие впереди,
# PollinationsAI последней (требует «cake credits» на g4f.dev → 402).
FALLBACK_PROVIDERS = [
    "Perplexity",
    "DeepInfra",
    "PollinationsAI",
]

_client = Client()


def chat_completion(
    messages: list[dict],
    *,
    timeout: int = 120,
    temperature: float | None = None,
) -> str:
    params: dict = {
        "model": "",
        "messages": messages,
        "max_tokens": 512,
        "timeout": timeout,
    }
    if temperature is not None:
        params["temperature"] = max(0.0, min(2.0, float(temperature)))

    last_error: Exception | None = None
    for provider in FALLBACK_PROVIDERS:
        try:
            params["provider"] = provider
            response = _client.chat.completions.create(**params)
            if response.choices and (text := response.choices[0].message.content):
                logger.info("g4f fallback через %s OK", provider)
                return text
        except Exception as e:
            last_error = e
            logger.warning("g4f fallback %s ошибка: %s", provider, e)
            continue

    raise RuntimeError(
        f"g4f: все провайдеры недоступны. {last_error or ''}"
    )
