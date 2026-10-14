# -*- coding: utf-8 -*-
"""Озвучка через Hugging Face Space John6666/mikuTTS (gradio_client), без нагрузки на локальный GPU."""
from __future__ import annotations

import concurrent.futures
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Спейс дублирован с NoCrypt/mikuTTS; API — эндпоинт /tts (не legacy /predict).
SPACE_ID = "John6666/mikuTTS"
API_NAME = "/tts"
DEFAULT_MODEL = "1a_miku_default_rvc_(aple)"
# Русский женский голос Edge-TTS (озвучка на русском, без перевода в японский).
TTS_VOICE_RU = "ru-RU-SvetlanaNeural-Female"
_MAX_INPUT_CHARS = 900
# Ключ у config.json: True → rmvpe + index 1.0 (якість), False → pm + 0.75 (швидкість).
_CONFIG_KEY_TTS_QUALITY = "miku_tts_high_quality"

# TTS на HF часто >60 с; дефолтный predict() без таймаута на Future всё равно может получить CancelledError при обрыве SSE.
_GRADIO_JOB_TIMEOUT_SEC = 600.0
_HTTP_TIMEOUT = httpx.Timeout(
    720.0,
    connect=120.0,
    read=720.0,
    write=120.0,
)
_MAX_SUBMIT_RETRIES = 3
_RETRY_SLEEP_SEC = 1.5

_client: Any = None
_client_lock = threading.Lock()
_tts_chain_lock = threading.Lock()
# Один активний predict на клієнт (warmup + 🔊 не змішуються).
_gradio_predict_lock = threading.Lock()
# Сериализация pygame-воспроизведения между всеми потоками озвучки.
_play_lock = threading.Lock()

# --- События воспроизведения для синхронизации анимации (3D-панда) ---
# Слушатель получает ("start", duration_ms) когда реально начинается звук и
# ("end", 0) когда звук закончился (после небольшой паузы без новых фраз).
_playback_listener: Any = None
_speech_active = False
_speech_end_timer: "threading.Timer | None" = None
_speech_state_lock = threading.Lock()
_SPEECH_GAP_SEC = 0.4


def set_playback_listener(listener: Any) -> None:
    """Зарегистрировать колбэк ``listener(event: str, duration_ms: int)``."""
    global _playback_listener
    _playback_listener = listener


def _notify_playback(event: str, duration_ms: int = 0) -> None:
    listener = _playback_listener
    if listener is None:
        return
    try:
        listener(event, int(duration_ms))
    except Exception:
        logger.debug("Ошибка слушателя воспроизведения", exc_info=True)


def _fire_speech_end() -> None:
    global _speech_active
    with _speech_state_lock:
        if not _speech_active:
            return
        _speech_active = False
    _notify_playback("end", 0)


def _arm_speech(duration_ms: int) -> None:
    """Отметить старт звука и перезапустить таймер окончания озвучки."""
    global _speech_active, _speech_end_timer
    just_started = False
    with _speech_state_lock:
        if not _speech_active:
            _speech_active = True
            just_started = True
        if _speech_end_timer is not None:
            _speech_end_timer.cancel()
        delay = max(0, int(duration_ms)) / 1000.0 + _SPEECH_GAP_SEC
        timer = threading.Timer(delay, _fire_speech_end)
        timer.daemon = True
        _speech_end_timer = timer
        timer.start()
    if just_started:
        _notify_playback("start", duration_ms)

# --- Инкрементальная (потоковая) озвучка: текст приходит кусками во время LLM-стрима. ---
_STREAM_LOCK = threading.Lock()
_stream_tx: "queue.Queue[str | None]" | None = None
_stream_audio: "queue.Queue[str | None]" | None = None
_stream_started = False
_stream_done_cb: Any = None


def _stream_synth_worker(tx: "queue.Queue", audio_q: "queue.Queue") -> None:
    """Синтез кусков по очереди; результат (путь к wav) кладёт в audio_q."""
    sent = False
    try:
        while True:
            item = tx.get()
            if item is None:
                audio_q.put(None)
                sent = True
                return
            text = (item or "").strip()
            if not text:
                continue
            try:
                wav = generate_miku_voice(text)
                audio_q.put(wav)
            except Exception:
                logger.warning("Потоковая озвучка: кусок не синтезирован", exc_info=True)
    finally:
        if not sent:
            try:
                audio_q.put_nowait(None)
            except Exception:
                pass


def _stream_play_worker(audio_q: "queue.Queue", done_cb: Any) -> None:
    """Воспроизведение готовых wav по очереди; после завершения — done_cb."""
    try:
        while True:
            path = audio_q.get()
            if path is None:
                return
            try:
                with _play_lock:
                    play_wav_file(path)
            except Exception:
                logger.warning("Потоковая озвучка: воспроизведение куска не удалось", exc_info=True)
    finally:
        if done_cb:
            try:
                done_cb()
            except Exception:
                pass


def start_chunked_speech(done_callback: Any = None) -> None:
    """Начать потоковую озвучку: включаются потоки синтеза и воспроизведения."""
    global _stream_tx, _stream_audio, _stream_started, _stream_done_cb
    with _STREAM_LOCK:
        if _stream_started:
            _stream_done_cb = done_callback or _stream_done_cb
            return
        tx: "queue.Queue[str | None]" = queue.Queue()
        audio_q: "queue.Queue[str | None]" = queue.Queue()
        _stream_tx, _stream_audio = tx, audio_q
        _stream_done_cb = done_callback
        threading.Thread(target=_stream_synth_worker, args=(tx, audio_q), daemon=True).start()
        threading.Thread(
            target=_stream_play_worker, args=(audio_q, done_callback), daemon=True
        ).start()
        _stream_started = True


def feed_chunk(text: str) -> None:
    """Положить кусок текста в потоковую очередь озвучки."""
    with _STREAM_LOCK:
        tx = _stream_tx
    if tx is not None and (text or "").strip():
        try:
            tx.put_nowait(text)
        except Exception:
            logger.warning("Потоковая озвучка: очередь переполнена, кусок пропущен", exc_info=True)


def finish_chunked_speech() -> None:
    """Завершить потоковую озвучку: sentinel, после доигрывания — done_cb."""
    global _stream_tx, _stream_started
    with _STREAM_LOCK:
        tx = _stream_tx
        _stream_tx = None
        _stream_started = False
    if tx is not None:
        try:
            tx.put_nowait(None)
        except Exception:
            pass


def _reset_gradio_client() -> None:
    global _client
    with _client_lock:
        old = _client
        _client = None
    if old is not None:
        try:
            old.close()
        except Exception:
            pass


def _get_client():
    global _client
    from gradio_client import Client

    with _client_lock:
        if _client is None:
            logger.info("Подключение Gradio Client к спейсу %s (длинные таймауты HTTP/SSE)", SPACE_ID)
            _client = Client(
                SPACE_ID,
                httpx_kwargs={"timeout": _HTTP_TIMEOUT},
            )
        return _client


def _f0_method_and_index_rate() -> tuple[str, float]:
    """Параметри RVC з config.json (налаштування в додатку)."""
    try:
        from paths import read_config_json

        cfg = read_config_json()
        raw = cfg.get(_CONFIG_KEY_TTS_QUALITY, True)
        high = bool(raw) if raw is not None else True
        if high:
            return "rmvpe", 1.0
        return "pm", 0.75
    except Exception:
        return "rmvpe", 1.0


def _prepare_tts_text(text: str) -> str:
    """Текст для синтеза: очистка от эмоций/RP-вставок/каомодзи + обрезка по длине."""
    from tts_text import clean_text_for_tts

    t = clean_text_for_tts(text)
    if len(t) > _MAX_INPUT_CHARS:
        t = t[:_MAX_INPUT_CHARS]
    return t


def _normalize_predict_result(result: Any) -> str:
    """Достаёт путь к .wav или .mp3 из ответа Gradio (строка, кортеж, dict, FileData)."""
    if result is None:
        raise RuntimeError("Спейс вернул пустой ответ")

    if isinstance(result, tuple) and result and isinstance(result[0], str):
        head = result[0].strip()
        if head.startswith("Traceback") or head.startswith("Error:"):
            snippet = head[:600].replace("\n", " ")
            raise RuntimeError(f"Ошибка на стороне спейса: {snippet}")

    candidates: list[str] = []

    def walk(obj: Any) -> None:
        if obj is None:
            return
        if isinstance(obj, Path):
            s = str(obj)
            if s.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                candidates.append(s)
            return
        if isinstance(obj, str):
            low = obj.lower()
            if low.endswith((".wav", ".mp3", ".ogg", ".flac")):
                candidates.append(obj)
            return
        if isinstance(obj, dict):
            for key in ("path", "name", "url"):
                if key in obj:
                    walk(obj[key])
            return
        if isinstance(obj, (list, tuple)):
            for x in obj:
                walk(x)
            return
        p = getattr(obj, "path", None)
        if isinstance(p, str):
            walk(p)

    walk(result)

    for p in reversed(candidates):
        if p.lower().endswith(".wav"):
            return p
    if candidates:
        return candidates[-1]

    raise RuntimeError(
        "Неожиданный ответ спейса: нет пути к аудио. "
        f"Тип: {type(result)!r}, кратко: {repr(result)[:200]}"
    )


def generate_miku_voice(text: str) -> str:
    """
    Синтез через Gradio /tts: русский текст + ru-RU Edge voice + RVC.
    Speed=0 (целое): иначе Edge TTS на спейсе даёт невалидный rate «+1.0%».
    """
    from gradio_client.utils import QueueError

    speech = _prepare_tts_text(text)
    if not speech:
        raise ValueError("Пустой текст для озвучки")

    last_exc: BaseException | None = None

    for attempt in range(_MAX_SUBMIT_RETRIES):
        f0_method, index_rate = _f0_method_and_index_rate()
        try:
            client = _get_client()
            with _gradio_predict_lock:
                job = client.submit(
                    DEFAULT_MODEL,
                    0,
                    0,
                    0,
                    speech,
                    TTS_VOICE_RU,
                    6,
                    f0_method,
                    index_rate,
                    0.33,
                    api_name=API_NAME,
                )
                result = job.result(timeout=_GRADIO_JOB_TIMEOUT_SEC)
        except concurrent.futures.CancelledError as e:
            last_exc = e
            logger.warning(
                "Gradio /tts: CancelledError (обрыв SSE / закрытие потока на HF), попытка %s/%s",
                attempt + 1,
                _MAX_SUBMIT_RETRIES,
            )
            _reset_gradio_client()
            time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
            continue
        except concurrent.futures.TimeoutError as e:
            last_exc = e
            logger.warning(
                "Gradio /tts: таймаут ожидания результата (%ss), попытка %s/%s",
                int(_GRADIO_JOB_TIMEOUT_SEC),
                attempt + 1,
                _MAX_SUBMIT_RETRIES,
            )
            _reset_gradio_client()
            time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
            continue
        except QueueError as e:
            last_exc = e
            logger.warning(
                "Gradio /tts: очередь спейса переполнена, попытка %s/%s",
                attempt + 1,
                _MAX_SUBMIT_RETRIES,
            )
            time.sleep(_RETRY_SLEEP_SEC * (attempt + 2))
            continue
        except Exception as e:
            logger.warning("Gradio /tts: неожиданная ошибка submit/result", exc_info=True)
            raise RuntimeError(
                "Miku TTS недоступен (спейс на HF спит, занят или перегружен). Повторите позже."
            ) from e

        try:
            path = _normalize_predict_result(result)
        except RuntimeError as e:
            last_exc = e
            logger.warning("Gradio /tts: некорректный ответ: %s", e)
            _reset_gradio_client()
            time.sleep(_RETRY_SLEEP_SEC * (attempt + 1))
            continue

        if not path or not isinstance(path, str):
            raise RuntimeError("Спейс не вернул файл озвучки")
        return path

    raise RuntimeError(
        "Miku TTS не успел ответить (HF оборвал связь или очередь). Нажмите 🔊 ещё раз через минуту."
    ) from last_exc


def play_wav_file(path: str) -> None:
    """Воспроизведение .wav / .mp3 через pygame (в том же потоке, где вызвана).

    Сообщает слушателю (см. :func:`set_playback_listener`) о реальном старте и
    окончании звука — на этом строится синхронизация анимации панды.
    """
    import pygame

    try:
        pygame.mixer.init()
        duration_ms = 0
        try:
            duration_ms = int(pygame.mixer.Sound(path).get_length() * 1000)
        except Exception:
            duration_ms = 0
        if duration_ms <= 0:
            duration_ms = 1000
        _arm_speech(duration_ms)
        pygame.mixer.music.stop()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.12)
    except Exception:
        logger.exception("Ошибка воспроизведения аудио: %s", path)
        raise


def speak_text_as_miku(text: str) -> None:
    """Синтез + воспроизведение подряд; одна очередь — без наложения дорожек."""
    with _tts_chain_lock:
        wav_path = generate_miku_voice(text)
        play_wav_file(wav_path)


def warmup_space(delay_sec: float = 2.5) -> None:
    """
    Фоновий прогрів: короткий /tts на HF, щоб інстанс і GPU прокинулись до першого натискання 🔊.
    Не відтворює звук. Помилки ігноруються (спейс може спати).
    """
    time.sleep(delay_sec)
    try:
        logger.info("TTS: фоновий прогрів спейсу (короткий синтез)...")
        generate_miku_voice("а")
        logger.info("TTS: прогрів завершено")
    except Exception as e:
        logger.debug("TTS warmup пропущено: %s", e)
