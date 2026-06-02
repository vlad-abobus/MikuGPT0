from __future__ import annotations

import logging

from paths import read_config_json

logger = logging.getLogger(__name__)

PROVIDER_OPENROUTER = "openrouter"

OPENROUTER_AUTH_MSG = (
    "Ключ OpenRouter заблокирован или неверный. Создайте новый на openrouter.ai/keys."
)
NO_KEY_OPENROUTER_MSG = (
    "Укажите ключ OpenRouter в config.json (поле «openrouter_api_key»)."
)

CHAT_RATE_LIMIT_MSG = (
    "OpenRouter временно ограничил запросы. Подождите минуту."
)
CHAT_QUOTA_MSG = (
    "Лимит OpenRouter исчерпан. Переключаю на g4f..."
)

DEFAULT_TEMPERATURE = 0.75
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0

_g4f_active = False


def get_temperature() -> float:
    raw = read_config_json().get("ai_temperature", DEFAULT_TEMPERATURE)
    try:
        t = float(raw)
    except (TypeError, ValueError):
        t = DEFAULT_TEMPERATURE
    return max(TEMPERATURE_MIN, min(TEMPERATURE_MAX, t))


class ChatAuthError(Exception):
    """Неверный или заблокированный API-ключ."""


class ChatRateLimitError(Exception):
    """Лимит запросов (429) на всех доступных моделях."""


class ChatProviderError(Exception):
    """Прочая ошибка провайдера."""


def get_provider() -> str:
    return PROVIDER_OPENROUTER


def has_openrouter_key() -> bool:
    return bool((read_config_json().get("openrouter_api_key") or "").strip())


def has_active_key() -> bool:
    return has_openrouter_key()


def reset_quota_flag() -> None:
    global _g4f_active
    _g4f_active = False


def is_g4f_session() -> bool:
    return _g4f_active


def _map_openrouter_error(exc: BaseException) -> BaseException:
    from gemini_client import GeminiRateLimitError

    if isinstance(exc, GeminiRateLimitError):
        return ChatRateLimitError(CHAT_RATE_LIMIT_MSG)
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "ключ" in msg.lower():
            return ChatAuthError(OPENROUTER_AUTH_MSG)
        if "не задан" in msg.lower():
            return ChatAuthError(NO_KEY_OPENROUTER_MSG)
    if isinstance(exc, RuntimeError):
        return ChatProviderError(str(exc))
    return ChatProviderError(str(exc))


def _g4f_chat(messages: list[dict], *, timeout: int) -> str:
    from g4f_client import chat_completion as g4f_chat

    try:
        logger.info("g4f: отправка запроса...")
        return g4f_chat(messages, timeout=timeout, temperature=get_temperature())
    except Exception as e:
        raise ChatProviderError(f"Ошибка g4f: {e}") from e


def force_g4f_for_session() -> None:
    global _g4f_active
    _g4f_active = True


def _openrouter_chat(
    messages: list[dict],
    *,
    timeout: int,
    model_override: str | None = None,
) -> str:
    global _g4f_active

    if _g4f_active:
        return _g4f_chat(messages, timeout=timeout)

    from gemini_client import chat_completion as or_chat
    from gemini_client import (
        GeminiQuotaError,
        OPENROUTER_BASE_URL,
    )

    if not has_openrouter_key():
        raise ChatAuthError(NO_KEY_OPENROUTER_MSG)

    model = model_override or None

    try:
        return or_chat(
            messages,
            timeout=timeout,
            temperature=get_temperature(),
            model_override=model,
            api_base=OPENROUTER_BASE_URL,
        )
    except GeminiQuotaError:
        logger.info("OpenRouter quota исчерпан")
        raise ChatRateLimitError(CHAT_QUOTA_MSG)
    except Exception as e:
        raise _map_openrouter_error(e) from e


def chat(
    messages: list[dict],
    *,
    model_hint: str | None = None,
    timeout: int = 60,
    nsfw: bool = False,
    model_override: str | None = None,
) -> str:
    return _openrouter_chat(messages, timeout=timeout, model_override=model_override)


def chat_short(
    messages: list[dict],
    *,
    model_hint: str | None = None,
    timeout: int = 30,
    nsfw: bool = False,
    model_override: str | None = None,
) -> str:
    return _openrouter_chat(messages, timeout=timeout, model_override=model_override)
