# -*- coding: utf-8 -*-
"""Google Gemini API (Google AI Studio) — модель gemini-3.5-flash-lite.

Все данные запроса читаются из файла api_gem.txt (лежит рядом с main.py / рядом с exe):
    api_key=...      — обязательный ключ Google AI Studio
    model=...        — имя модели (по умолчанию gemini-3.5-flash-lite)
    max_output_tokens, timeout, context_window — опционально.

Без ключа ничего не работает: см. api_gem.txt, там подробно описано, что заполнять.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Iterator

import requests

from paths import resource_path

logger = logging.getLogger(__name__)

API_FILE_NAME = "api_gem.txt"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_TIMEOUT = 60
DEFAULT_CONTEXT_WINDOW = 1_000_000
MIN_CONTEXT_WINDOW = 2048
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Значения-заглушки: ключ ещё не вставлен — работать нельзя.
_PLACEHOLDER_KEYS = {
    "",
    "вставь_сюда_свой_api_key",
    "ваш_ключ",
    "api_key",
    "todo",
    "changeme",
}

_cache_lock = threading.Lock()
_cache: dict | None = None
_cache_sig: tuple | None = None


def _user_path() -> str:
    """Путь к api_gem.txt, который пользователь редактирует: рядом с exe или с проектом."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), API_FILE_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), API_FILE_NAME)


def api_gem_path() -> str:
    """Путь к api_gem.txt. Если рядом с exe его нет — распаковываем шаблон из сборки."""
    user = _user_path()
    if os.path.exists(user):
        return user
    bundled = resource_path(API_FILE_NAME)
    if os.path.abspath(bundled) != os.path.abspath(user) and os.path.exists(bundled):
        try:
            import shutil

            shutil.copyfile(bundled, user)
            logger.info("Создан шаблон %s из сборки", user)
            return user
        except OSError as e:
            logger.warning("Не удалось создать %s: %s", user, e)
            return bundled
    return user


def _read_file() -> str:
    path = api_gem_path()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except OSError as e:
        logger.warning("Не удалось прочитать %s: %s", path, e)
        return ""


def _parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip().lower()] = value.strip().strip('"').strip("'")
    return out


def _settings() -> dict[str, str]:
    """Кэш содержимого api_gem.txt (инвалидируется по mtime/размеру)."""
    global _cache, _cache_sig
    path = api_gem_path()
    try:
        st = os.stat(path)
        sig = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        sig = (path, 0, 0)
    with _cache_lock:
        if _cache is None or _cache_sig != sig:
            parsed = _parse(_read_file())
            _cache = parsed
            _cache_sig = sig
        return dict(_cache)


def api_key() -> str:
    return _settings().get("api_key", "").strip()


def has_key() -> bool:
    return api_key().lower() not in _PLACEHOLDER_KEYS


def model() -> str:
    return (_settings().get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _max_output_tokens() -> int:
    raw = _settings().get("max_output_tokens")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_MAX_OUTPUT_TOKENS
    return max(64, min(65536, n))


def request_timeout() -> int:
    raw = _settings().get("timeout")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_TIMEOUT
    return max(5, min(600, n))


def context_limit() -> int:
    """Окно контекста модели (токены) — по нему main.py обрезает историю."""
    raw = _settings().get("context_window")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_CONTEXT_WINDOW
    return max(MIN_CONTEXT_WINDOW, min(4_000_000, n))


def _require_key() -> str:
    if not has_key():
        raise RuntimeError(
            f"API-ключ Gemini не задан. Открой файл {api_gem_path()} и заполни строку api_key=..."
        )
    return api_key()


def _clamp_temperature(value) -> float:
    try:
        t = float(value)
    except (TypeError, ValueError):
        t = 0.75
    return max(0.0, min(2.0, t))


def _to_body(messages: list[dict], *, temperature: float, max_tokens: int) -> dict:
    system_parts: list[str] = []
    contents: list[dict] = []
    for m in messages:
        role = (m.get("role") or "").lower()
        text = (m.get("content") or "").strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
        else:
            contents.append({"role": "user", "parts": [{"text": text}]})
    if not contents:
        raise RuntimeError("Gemini API: пустой запрос (нет сообщений).")
    body: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": _clamp_temperature(temperature),
            "maxOutputTokens": max_tokens,
        },
    }
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return body


def _error_text(resp: requests.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error") or {}
        msg = err.get("message") or ""
        code = err.get("status") or ""
        return f"{msg} {code}".strip() or resp.text[:300]
    except Exception:
        return (resp.text or "")[:300]


def _extract_text(data: dict) -> str:
    chunks: list[str] = []
    for cand in data.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        for part in ((cand.get("content") or {}).get("parts") or []):
            if isinstance(part, dict) and part.get("text"):
                chunks.append(part["text"])
    return "".join(chunks)


def _block_reason(data: dict) -> str:
    fb = data.get("promptFeedback") or {}
    reason = fb.get("blockReason")
    if reason:
        return str(reason)
    for cand in data.get("candidates") or []:
        if isinstance(cand, dict) and cand.get("finishReason") == "SAFETY":
            return "SAFETY"
    return ""


def chat_completion(
    messages: list[dict],
    *,
    timeout: int | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Полный ответ (не потоковый) от Gemini."""
    key = _require_key()
    body = _to_body(
        messages,
        temperature=_clamp_temperature(temperature),
        max_tokens=max_tokens or _max_output_tokens(),
    )
    url = f"{BASE_URL}/{model()}:generateContent"
    try:
        resp = requests.post(
            url,
            params={"key": key},
            json=body,
            timeout=timeout or request_timeout(),
        )
    except requests.Timeout as e:
        raise RuntimeError(f"Gemini API: таймаут запроса ({timeout or request_timeout()} c)") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini API: нет сети — {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API HTTP {resp.status_code}: {_error_text(resp)}")

    try:
        data = resp.json()
    except ValueError as e:
        raise RuntimeError("Gemini API: не удалось разобрать ответ (не JSON).") from e

    text = _extract_text(data).strip()
    if not text:
        reason = _block_reason(data)
        raise RuntimeError(
            f"Gemini API вернул пустой ответ{f' (заблокировано: {reason})' if reason else ''}."
        )
    logger.info("Gemini %s ответ: %s", model(), text[:300])
    return text


def chat_completion_stream(
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Генерация текста кусками по мере ответа (SSE-стриминг Gemini)."""
    key = _require_key()
    body = _to_body(
        messages,
        temperature=_clamp_temperature(temperature),
        max_tokens=max_tokens or _max_output_tokens(),
    )
    url = f"{BASE_URL}/{model()}:streamGenerateContent"
    try:
        resp = requests.post(
            url,
            params={"key": key, "alt": "sse"},
            json=body,
            timeout=request_timeout(),
            stream=True,
        )
    except requests.Timeout as e:
        raise RuntimeError(f"Gemini API: таймаут запроса ({request_timeout()} c)") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini API: нет сети — {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API HTTP {resp.status_code}: {_error_text(resp)}")

    logger.info("Gemini %s stream: начало ответа...", model())
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
            except ValueError:
                continue
            piece = _extract_text(data)
            if piece:
                yield piece
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini API: обрыв соединения — {e}") from e
    finally:
        resp.close()


def warmup(delay_sec: float = 2.5) -> None:
    """Фоновый прогрев: один лёгкий запрос, чтобы ключ/сеть проверились заранее."""
    import time

    time.sleep(delay_sec)
    if not has_key():
        logger.warning("Gemini API: ключ не задан — заполни %s", api_gem_path())
        return
    try:
        resp = requests.get(
            f"{BASE_URL}/{model()}",
            params={"key": api_key()},
            timeout=request_timeout(),
        )
        if resp.status_code == 200:
            logger.info("Gemini API: ключ принят, модель %s доступна", model())
        else:
            logger.warning("Gemini API: проверка ключа — HTTP %s: %s", resp.status_code, _error_text(resp))
    except requests.RequestException as e:
        logger.debug("Gemini API warmup пропущено: %s", e)
