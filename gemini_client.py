# -*- coding: utf-8 -*-
"""OpenRouter (основной) / Groq (запасной) через OpenAI SDK."""
from __future__ import annotations

import logging

from openai import OpenAI
from openai import (
    AuthenticationError as OpenAIAuthError,
    RateLimitError as OpenAIRateLimitError,
    APIStatusError as OpenAIAPIError,
)

from paths import read_config_json

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "thedrummer/unslopnemo-12b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class GeminiRateLimitError(Exception):
    """429 Too Many Requests."""


class GeminiQuotaError(Exception):
    """Дневной лимит токенов исчерпан."""


def _load_openrouter_key() -> str:
    return (read_config_json().get("openrouter_api_key") or "").strip()


def _load_groq_key() -> str:
    return (read_config_json().get("gemini_api_key") or "").strip()


def _resolve_model() -> str:
    return (read_config_json().get("gemini_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def has_openrouter_key() -> bool:
    return bool(_load_openrouter_key())


def chat_completion(
    messages: list[dict],
    *,
    timeout: int = 60,
    temperature: float | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    model_override: str | None = None,
    api_base: str | None = None,
) -> str:
    if model_override:
        model_name = model_override
    else:
        model_name = _resolve_model()
    if not messages:
        raise ValueError("Нет сообщений для отправки.")

    is_openrouter = api_base is None or "openrouter" in api_base

    if is_openrouter:
        api_key = _load_openrouter_key()
        base_url = api_base or OPENROUTER_BASE_URL
        provider_label = "OpenRouter"
        if not api_key:
            raise ValueError(
                "Ключ OpenRouter не задан. Укажите его в config.json "
                "(поле «openrouter_api_key»)."
            )
    else:
        api_key = _load_groq_key()
        base_url = api_base or GROQ_BASE_URL
        provider_label = "Groq"
        if not api_key:
            raise ValueError(
                "Ключ Groq API не задан. Укажите его в config.json "
                "(поле «gemini_api_key»)."
            )

    kwargs: dict = {
        "model": model_name,
        "messages": messages,
        "timeout": timeout,
    }
    if temperature is not None:
        kwargs["temperature"] = max(0.0, min(2.0, float(temperature)))
    if frequency_penalty is not None:
        kwargs["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        kwargs["presence_penalty"] = presence_penalty

    client_kwargs = {"api_key": api_key, "base_url": base_url}
    if is_openrouter:
        client_kwargs["default_headers"] = {
            "HTTP-Referer": "https://github.com/anomalyco/opencode",
            "X-Title": "MikuGPT",
        }
    client = OpenAI(**client_kwargs)

    try:
        response = client.chat.completions.create(**kwargs)
        result = response.choices[0].message.content or ""
        logger.info("%s API сырой ответ: %s", provider_label, result)
        return result
    except OpenAIRateLimitError as e:
        body = e.response.text
        logger.warning("%s RateLimit (429): %s", provider_label, body)
        if "tokens per day" in body.lower() or "tpd" in body.lower():
            raise GeminiQuotaError()
        raise GeminiRateLimitError()
    except OpenAIAuthError as e:
        logger.warning("%s auth ошибка: %s", provider_label, e.response.text)
        raise ValueError(
            f"Неверный или просроченный ключ {provider_label}. "
            f"{'Создайте ключ на openrouter.ai/keys.' if is_openrouter else 'Создайте ключ на console.groq.com/keys.'}"
        )
    except OpenAIAPIError as e:
        logger.warning("%s ошибка %s: %s", provider_label, e.status_code, e.response.text)
        raise RuntimeError(
            f"Ошибка {provider_label} ({e.status_code}): {e.response.text}"
        )
    except Exception as e:
        logger.warning("%s неожиданная ошибка: %s", provider_label, e)
        raise RuntimeError(f"Ошибка при обращении к {provider_label}: {e}")
