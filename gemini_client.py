# -*- coding: utf-8 -*-
"""OpenRouter (основной) / Groq (запасной) через httpx."""
from __future__ import annotations

import json
import logging

import httpx

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

    body: dict = {
        "model": model_name,
        "messages": messages,
    }
    if temperature is not None:
        body["temperature"] = max(0.0, min(2.0, float(temperature)))
    if frequency_penalty is not None:
        body["frequency_penalty"] = frequency_penalty
    if presence_penalty is not None:
        body["presence_penalty"] = presence_penalty

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if is_openrouter:
        headers["HTTP-Referer"] = "https://github.com/anomalyco/opencode"
        headers["X-Title"] = "MikuGPT"

    # Явно сериализуем в UTF-8, чтобы httpx не спотыкался на кириллице
    encoded_body = json.dumps(body, ensure_ascii=False).encode("utf-8")

    try:
        with httpx.Client(verify=True) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                content=encoded_body,
                timeout=timeout,
            )
    except Exception as e:
        logger.warning("%s транспортная ошибка: %s", provider_label, e)
        raise RuntimeError(f"Ошибка при обращении к {provider_label}: {e}")

    try:
        data = response.json()
    except Exception:
        logger.warning("%s невалидный JSON в ответе: %s", provider_label, response.text[:500])
        raise RuntimeError(f"{provider_label} вернул невалидный JSON: {response.text[:200]}")

    if response.status_code == 429:
        body_text = response.text
        logger.warning("%s RateLimit (429): %s", provider_label, body_text)
        if "tokens per day" in body_text.lower() or "tpd" in body_text.lower():
            raise GeminiQuotaError()
        raise GeminiRateLimitError()

    if response.status_code == 401:
        logger.warning("%s auth ошибка: %s", provider_label, response.text)
        raise ValueError(
            f"Неверный или просроченный ключ {provider_label}. "
            f"{'Создайте ключ на openrouter.ai/keys.' if is_openrouter else 'Создайте ключ на console.groq.com/keys.'}"
        )

    if response.status_code != 200:
        logger.warning("%s ошибка %s: %s", provider_label, response.status_code, response.text[:500])
        raise RuntimeError(
            f"Ошибка {provider_label} ({response.status_code}): {response.text[:200]}"
        )

    try:
        result = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        logger.warning("%s неожиданная структура ответа: %s", provider_label, str(data)[:500])
        raise RuntimeError(f"{provider_label} вернул неожиданную структуру ответа.")

    logger.info("%s API сырой ответ: %s", provider_label, result)
    return result
