# -*- coding: utf-8 -*-
"""Озвучка Мику через Fish Audio.

Синтез идёт на стороне Fish Audio (https://docs.fish.audio/), локальные
RVC-модели и Hugging Face Space больше не используются. Ключ, голос и модель
задаются в .env:

    FISH_API_KEY=...
    FISH_REFERENCE_ID=...   — голос для русского
    FISH_REFERENCE_ID_KK/UK/EN=... — голоса для остальных языков
    FISH_TTS_MODEL=s2.1-pro-free
"""
from __future__ import annotations

import logging
import os
import queue
import struct
import tempfile
import threading
import time
import wave

import requests

from paths import load_env_file
from tts_text import clean_text_for_tts, split_for_tts

logger = logging.getLogger(__name__)

load_env_file()

DEFAULT_API_URL = "https://api.fish.audio/v1/tts"
DEFAULT_TTS_MODEL = "s2.1-pro-free"
DEFAULT_TIMEOUT = 120
DEFAULT_LANGUAGE_VOICE_IDS = {
    "kk": "6717a74323274cb296ea9a0da654c977",
    "uk": "6717a74323274cb296ea9a0da654c977",
    "en": "6717a74323274cb296ea9a0da654c977",
}
_MAX_INPUT_CHARS = 2000
_MAX_ATTEMPTS = 3
_RETRY_SLEEP_SEC = 1.2
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_PLACEHOLDER_KEYS = {
    "",
    "your_api_key_here",
    "your_fish_api_key_here",
    "replace_me",
    "вставь_ключ",
    "api_key",
}

_tts_chain_lock = threading.Lock()
_synth_lock = threading.Lock()


class _AudioFormatError(RuntimeError):
    """Fish прислал пустой или битый WAV — имеет смысл повторить запрос."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip() or default


def api_key() -> str:
    return _env("FISH_API_KEY")


def reference_id(language: str = "ru") -> str:
    language = (language or "ru").strip().lower()
    if language in DEFAULT_LANGUAGE_VOICE_IDS:
        return _env(
            f"FISH_REFERENCE_ID_{language.upper()}",
            DEFAULT_LANGUAGE_VOICE_IDS[language],
        )
    return _env("FISH_REFERENCE_ID") or _env("FISH_VOICE_ID")


def tts_model() -> str:
    return _env("FISH_TTS_MODEL", DEFAULT_TTS_MODEL)


def api_url() -> str:
    return _env("FISH_API_URL", DEFAULT_API_URL)


def _timeout() -> int:
    try:
        n = int(_env("FISH_TIMEOUT", str(DEFAULT_TIMEOUT)))
    except ValueError:
        n = DEFAULT_TIMEOUT
    return max(10, min(600, n))


def is_configured(language: str = "ru") -> bool:
    key = api_key()
    return bool(
        key and key.lower() not in _PLACEHOLDER_KEYS and reference_id(language)
    )


def configuration_error(language: str = "ru") -> str:
    if not api_key() or api_key().lower() in _PLACEHOLDER_KEYS:
        return (
            "Fish Audio: не задан FISH_API_KEY. Добавь ключ в .env рядом "
            "с приложением (https://fish.audio/app/developers)."
        )
    if not reference_id(language):
        return f"Fish Audio: не задан голос для языка {language!r} в .env."
    return ""


def _prepare_tts_text(text: str | None) -> str:
    speech = clean_text_for_tts(text)
    if len(speech) > _MAX_INPUT_CHARS:
        speech = speech[:_MAX_INPUT_CHARS].rstrip()
    return speech


def _new_wav_path() -> str:
    fd, path = tempfile.mkstemp(prefix="miku_fish_", suffix=".wav")
    os.close(fd)
    return path


def _error_message(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            msg = str(data.get("message") or data.get("error") or "").strip()
            reason = str(data.get("reason") or "").strip()
            if msg:
                return f"{msg}{f' ({reason})' if reason else ''}"
    except Exception:
        pass
    return (resp.text or "").strip()[:400]


def _raise_for_status(status: int, message: str, model: str) -> None:
    if status == 401:
        raise RuntimeError("Fish Audio: неверный FISH_API_KEY (HTTP 401).")
    if status == 402:
        raise RuntimeError(
            f"Fish Audio: нет кредита для модели {model} (HTTP 402). "
            "Используй FISH_TTS_MODEL=s2.1-pro-free или пополни баланс."
        )
    raise RuntimeError(f"Fish Audio HTTP {status}: {message or 'неизвестная ошибка'}")


def _repair_wav_file(path: str) -> None:
    """Проверить WAV и записать реальные размеры RIFF/data.

    Fish отдаёт потоковый WAV с размерами-заглушками ``0xFFFFFFxx``. Не все
    проигрыватели (и ``wave``) понимают такие заголовки, поэтому заменяем их
    фактическими. Заодно отсекаем пустой файл из одного заголовка: Fish так
    отвечает, например, на строку без букв.
    """
    size = os.path.getsize(path)
    if size < 44:
        raise _AudioFormatError("Fish Audio вернул неполный WAV.")

    data_offset = -1
    data_declared = 0
    with open(path, "rb") as f:
        header = f.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise _AudioFormatError("Fish Audio вернул файл не в формате WAV.")

        pos = 12
        while pos + 8 <= size:
            f.seek(pos)
            chunk = f.read(8)
            if len(chunk) < 8:
                break
            chunk_id = chunk[:4]
            chunk_size = struct.unpack("<I", chunk[4:])[0]
            if chunk_id == b"data":
                data_offset = pos + 8
                data_declared = chunk_size
                break
            if chunk_size == 0xFFFFFFFF:
                break
            next_pos = pos + 8 + chunk_size + (chunk_size & 1)
            if next_pos <= pos:
                break
            pos = next_pos

    if data_offset < 0:
        raise _AudioFormatError("Fish Audio вернул WAV без data-чанка.")
    actual_data = size - data_offset
    if actual_data <= 0:
        raise _AudioFormatError("Fish Audio вернул WAV без аудиоданных.")

    # Если размер в заголовке корректный — оставляем его (в файле могут быть
    # чанки после data). Если это заглушка — пишем реальный остаток файла.
    data_size = data_declared if 0 < data_declared <= actual_data else actual_data
    with open(path, "r+b") as f:
        f.seek(4)
        f.write(struct.pack("<I", min(size - 8, 0xFFFFFFFF)))
        f.seek(data_offset - 4)
        f.write(struct.pack("<I", min(data_size, 0xFFFFFFFF)))

    try:
        with wave.open(path, "rb") as w:
            frames = w.getnframes()
    except (wave.Error, EOFError, OSError) as exc:
        raise _AudioFormatError(f"Fish Audio вернул повреждённый WAV: {exc}") from exc
    if frames <= 0:
        raise _AudioFormatError("Fish Audio вернул WAV без аудиоданных.")


def _download_to_file(resp: requests.Response) -> str:
    path = _new_wav_path()
    try:
        size = 0
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                size += len(chunk)
        if size <= 0:
            raise _AudioFormatError("Fish Audio вернул пустой аудиофайл.")
        _repair_wav_file(path)
        return path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


def _generate_miku_voice_unlocked(text: str, language: str = "ru") -> str:
    speech = _prepare_tts_text(text)
    if not speech:
        raise ValueError("Пустой текст для озвучки")

    key = api_key()
    voice_id = reference_id(language)
    if not key or key.lower() in _PLACEHOLDER_KEYS:
        raise RuntimeError(configuration_error(language))
    if not voice_id:
        raise RuntimeError(configuration_error(language))

    model = tts_model()
    payload = {
        "text": speech,
        "reference_id": voice_id,
        "format": "wav",
        "sample_rate": 44100,
        "normalize": True,
        "latency": "balanced",
        "chunk_length": 200,
        "prosody": {"speed": 1.0, "volume": 0, "normalize_loudness": True},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "audio/wav",
        "model": model,
    }

    last_error = ""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with requests.post(
                api_url(),
                json=payload,
                headers=headers,
                timeout=(15, _timeout()),
                stream=True,
            ) as resp:
                if resp.status_code == 200:
                    try:
                        return _download_to_file(resp)
                    except _AudioFormatError as exc:
                        last_error = str(exc)
                        if attempt + 1 < _MAX_ATTEMPTS:
                            logger.warning(
                                "Fish Audio: %s, попытка %s/%s",
                                exc,
                                attempt + 1,
                                _MAX_ATTEMPTS,
                            )
                            time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
                            continue
                        raise RuntimeError(f"Fish Audio: {last_error}.") from exc

                message = _error_message(resp)
                if resp.status_code in _RETRY_STATUSES and attempt + 1 < _MAX_ATTEMPTS:
                    last_error = f"HTTP {resp.status_code}: {message}"
                    logger.warning(
                        "Fish Audio: временная ошибка %s, попытка %s/%s",
                        resp.status_code,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
                    continue
                _raise_for_status(resp.status_code, message, model)
        except requests.Timeout as exc:
            last_error = f"таймаут ({_timeout()} c)"
            if attempt + 1 < _MAX_ATTEMPTS:
                logger.warning("Fish Audio: таймаут, попытка %s/%s", attempt + 1, _MAX_ATTEMPTS)
                time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
                continue
            raise RuntimeError(f"Fish Audio: {last_error}.") from exc
        except requests.RequestException as exc:
            last_error = f"нет сети — {exc}"
            if attempt + 1 < _MAX_ATTEMPTS:
                logger.warning("Fish Audio: ошибка сети, попытка %s/%s", attempt + 1, _MAX_ATTEMPTS)
                time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
                continue
            raise RuntimeError(f"Fish Audio: {last_error}.") from exc

    raise RuntimeError(f"Fish Audio: не удалось получить аудио ({last_error}).")


def generate_miku_voice(
    text: str, voice: str | None = None, *, language: str = "ru"
) -> str:
    """Синтезировать текст через Fish Audio и вернуть путь к временному .wav.

    ``voice`` оставлен для совместимости со старым API; голос задаётся
    через FISH_REFERENCE_ID.
    """
    del voice
    with _synth_lock:
        return _generate_miku_voice_unlocked(text, language)


def play_wav_file(path: str) -> None:
    """Воспроизвести готовый файл (общая очередь с синхронной озвучкой)."""
    from audio_player import play_wav_file as _play

    _play(path)


def speak_text_as_miku(
    text: str, voice: str | None = None, *, language: str = "ru"
) -> None:
    """Синтез + последовательное воспроизведение текста (кнопка 🔊)."""
    del voice
    chunks = [c for c in split_for_tts(text) if clean_text_for_tts(c).strip()]
    if not chunks:
        return

    with _tts_chain_lock:
        if len(chunks) == 1:
            wav = generate_miku_voice(chunks[0], language=language)
            try:
                play_wav_file(wav)
            finally:
                try:
                    os.remove(wav)
                except OSError:
                    pass
            return

        audio_q: "queue.Queue[str | None]" = queue.Queue()
        errors: list[BaseException] = []

        def synth_worker() -> None:
            try:
                for chunk in chunks:
                    try:
                        audio_q.put(generate_miku_voice(chunk, language=language))
                    except Exception as exc:
                        errors.append(exc)
                        logger.warning("Fish Audio: фраза не синтезирована: %s", exc)
            finally:
                audio_q.put(None)

        threading.Thread(
            target=synth_worker, name="miku-fish-synth", daemon=True
        ).start()

        played = False
        while True:
            item = audio_q.get()
            if item is None:
                break
            try:
                play_wav_file(item)
                played = True
            finally:
                try:
                    os.remove(item)
                except OSError:
                    pass

        if not played and errors:
            raise RuntimeError(str(errors[0]))


def warmup(delay_sec: float = 2.5, voice: str | None = None) -> None:
    """Проверить наличие настроек без сетевого запроса и прогрева модели."""
    del voice
    time.sleep(max(0.0, delay_sec))
    if is_configured():
        logger.info("Fish Audio: ключ и голос настроены, модель %s", tts_model())
    else:
        logger.warning(configuration_error())
