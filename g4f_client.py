# -*- coding: utf-8 -*-
"""Free LLM провайдеры без API-ключа.

Основной: открытый OpenAI-совместимый API Pollinations (text.pollinations.ai/openai),
без ключа и без «cake credits». Резерв: g4f (только проверенно рабочее без ключа).
"""
from __future__ import annotations

import json
import logging

import httpx

from g4f.client import Client as G4FClient

logger = logging.getLogger(__name__)

POLLINATIONS_URL = "https://text.pollinations.ai/openai"
POLLINATIONS_MODELS = ["openai", "mistral"]

# g4f-резерв: только те, что реально отдают текст без ключа сейчас.
G4F_FALLBACK_PROVIDERS = ["Yqcloud"]

_g4f_client = G4FClient()


def _pollinations_post(payload: dict, *, timeout: int) -> str | None:
    """Один POST на Pollinations; при TLS-ошибке повторим с verify=False."""
    attempts = [
        {"verify": True},
        {"verify": False},
    ]
    for attempt in attempts:
        try:
            resp = httpx.post(
                POLLINATIONS_URL,
                json=payload,
                timeout=httpx.Timeout(connect=15.0, read=float(timeout), write=30.0, pool=30.0),
                verify=attempt["verify"],
            )
            if resp.status_code != 200:
                logger.warning("Pollinations статус %s: %s", resp.status_code, resp.text[:120])
                return None
            data = resp.json()
            if isinstance(data, dict):
                choices = data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    msg = choices[0].get("message") or {}
                    text = (msg.get("content") or "").strip()
                    if text:
                        return text
            logger.warning("Pollinations: пустой/неожиданный ответ")
            return None
        except Exception as e:
            logger.warning("Pollinations ошибка (verify=%s): %s: %s",
                           attempt["verify"], type(e).__name__, e)
    return None


def _pollinations_chat(model: str, messages: list[dict], *, timeout: int, temperature: float | None) -> str | None:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = max(0.0, min(2.0, float(temperature)))
    text = _pollinations_post(payload, timeout=timeout)
    return text if text else None


def _pollinations_stream(messages: list[dict], payload: dict, *, timeout: int):
    """SSE-стрим Pollinations: генератор текстовых кусков."""
    for verify in (True, False):
        emitted_any = False
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=15.0, read=float(timeout), write=30.0, pool=30.0),
                verify=verify,
            ) as client:
                with client.stream("POST", POLLINATIONS_URL, json=payload) as resp:
                    if resp.status_code != 200:
                        logger.warning("Pollinations stream статус %s", resp.status_code)
                        return
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            return
                        try:
                            obj = json.loads(data)
                        except Exception:
                            continue
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}) if isinstance(choices[0], dict) else {}
                        content = delta.get("content")
                        if content:
                            emitted_any = True
                            yield content
            return
        except Exception as e:
            logger.warning("Pollinations stream ошибка (verify=%s): %s", verify, e)
            if emitted_any:
                return
    return


def chat_completion(
    messages: list[dict],
    *,
    timeout: int = 120,
    temperature: float | None = None,
) -> str:
    last_error: Exception | None = None

    for model in POLLINATIONS_MODELS:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = max(0.0, min(2.0, float(temperature)))
        text = _pollinations_post(payload, timeout=timeout)
        if text:
            logger.info("g4f: ответ через Pollinations (%s)", model)
            return text

    for provider in G4F_FALLBACK_PROVIDERS:
        try:
            response = _g4f_client.chat.completions.create(
                model="",
                messages=messages,
                max_tokens=512,
                timeout=timeout,
                provider=provider,
            )
            if response.choices and (text := response.choices[0].message.content):
                logger.info("g4f fallback через %s OK", provider)
                return text
        except Exception as e:
            last_error = e
            logger.warning("g4f fallback %s ошибка: %s", provider, e)
            continue

    raise RuntimeError(
        f"g4f: все провайдеры недоступны. {last_error or 'нет ответа от Pollinations'}"
    )


def chat_completion_stream(
    messages: list[dict],
    *,
    timeout: int = 120,
    temperature: float | None = None,
):
    """Генератор кусков текста по мере генерации (Pollinations SSE, резерв g4f)."""
    for model in POLLINATIONS_MODELS:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = max(0.0, min(2.0, float(temperature)))
        count = 0
        ok = False
        for token in _pollinations_stream(messages, payload, timeout=timeout):
            if token:
                ok = True
                count += 1
                yield token
        if ok:
            logger.info("g4f stream: через Pollinations (%s), кусков: %s", model, count)
            return
        logger.warning("g4f stream: Pollinations (%s) не дал текста, пробуем другого", model)

    for provider in G4F_FALLBACK_PROVIDERS:
        try:
            stream = _g4f_client.chat.completions.create(
                model="",
                messages=messages,
                max_tokens=512,
                timeout=timeout,
                provider=provider,
                stream=True,
            )
            count = 0
            ok = False
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = getattr(delta, "content", None) if delta else None
                if token:
                    ok = True
                    count += 1
                    yield token
            if ok:
                logger.info("g4f stream: через %s (кусков: %s)", provider, count)
                return
            logger.warning("g4f stream: %s не дал текста", provider)
        except Exception as e:
            logger.warning("g4f stream: %s ошибка: %s", provider, e)
            continue

    raise RuntimeError("g4f: все стриминг-провайдеры недоступны")