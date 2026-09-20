# -*- coding: utf-8 -*-
"""Локальная озвучка Silero TTS (v4_ru): голос baya/kseniya, SSML prosody по характеру."""
from __future__ import annotations

import html
import logging
import os
import queue
import sys
import tempfile
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

MODEL_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
MODEL_FILENAME = "v4_ru.pt"
SAMPLE_RATE = 48000
_MAX_INPUT_CHARS = 900

DEFAULT_PRESET = {"voice": "baya", "pitch": "+15%", "rate": "105%"}

# Разные голос и темп/высота для разных характеров (аналог справочника Silero SSML).
PERSONALITY_PRESETS = {
    "Дередере": {"voice": "baya", "pitch": "high", "rate": "105%"},      # милая, нежная Мику
    "Цундере": {"voice": "baya", "pitch": "+20%", "rate": "118%"},       # резкая, колкая
    "Дандере": {"voice": "kseniya", "pitch": "-5%", "rate": "92%"},      # тихая, застенчивая
    "Яндере": {"voice": "baya", "pitch": "+35%", "rate": "115%"},        # тягуче-слащавая
    "Агресивный": {"voice": "kseniya", "pitch": "-10%", "rate": "125%"}, # злая, быстрая
    "Уку-Мамадере": {"voice": "kseniya", "pitch": "x-low", "rate": "95%"},  # спокойная «мама»
}

_model = None
_model_lock = threading.Lock()
_tts_chain_lock = threading.Lock()

# --- Инкрементальная (потоковая) озвучка во время LLM-стрима. ---
_STREAM_LOCK = threading.Lock()
_stream_tx: "queue.Queue[str | None]" | None = None
_stream_audio: "queue.Queue[str | None]" | None = None
_stream_started = False
_stream_done_cb: Any = None
_stream_personality: str | None = None


def _stream_synth_worker(tx: "queue.Queue", audio_q: "queue.Queue") -> None:
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
                personality = _stream_personality
                wav = synthesize(text, personality)
                audio_q.put(wav)
            except Exception:
                logger.warning("Потоковая озвучка Silero: кусок не синтезирован", exc_info=True)
    finally:
        if not sent:
            try:
                audio_q.put_nowait(None)
            except Exception:
                pass


def _stream_play_worker(audio_q: "queue.Queue", done_cb: Any) -> None:
    from miku_tts import play_wav_file

    try:
        while True:
            path = audio_q.get()
            if path is None:
                return
            try:
                play_wav_file(path)
            except Exception:
                logger.warning("Потоковая озвучка Silero: воспроизведение куска не удалось", exc_info=True)
    finally:
        if done_cb:
            try:
                done_cb()
            except Exception:
                pass


def start_chunked_speech(done_callback: Any = None, personality: str | None = None) -> None:
    """Начать потоковую озвучку Silero."""
    global _stream_tx, _stream_audio, _stream_started, _stream_done_cb, _stream_personality
    with _STREAM_LOCK:
        if _stream_started:
            _stream_done_cb = done_callback or _stream_done_cb
            if personality is not None:
                _stream_personality = personality
            return
        tx: "queue.Queue[str | None]" = queue.Queue()
        audio_q: "queue.Queue[str | None]" = queue.Queue()
        _stream_tx, _stream_audio = tx, audio_q
        _stream_done_cb = done_callback
        _stream_personality = personality
        threading.Thread(target=_stream_synth_worker, args=(tx, audio_q), daemon=True).start()
        threading.Thread(
            target=_stream_play_worker, args=(audio_q, done_callback), daemon=True
        ).start()
        _stream_started = True


def feed_chunk(text: str) -> None:
    """Положить кусок текста в потоковую очередь озвучки Silero."""
    with _STREAM_LOCK:
        tx = _stream_tx
    if tx is not None and (text or "").strip():
        try:
            tx.put_nowait(text)
        except Exception:
            logger.warning("Потоковая озвучка Silero: очередь переполнена, кусок пропущен", exc_info=True)


def finish_chunked_speech() -> None:
    """Завершить потоковую озвучку Silero."""
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


def _model_cache_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    d = os.path.join(base, "silero_cache")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        home = os.path.join(os.path.expanduser("~"), ".silero_cache")
        os.makedirs(home, exist_ok=True)
        return home


def _model_path() -> str:
    return os.path.join(_model_cache_dir(), MODEL_FILENAME)


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        import torch
        from torch import package

        path = _model_path()
        if not os.path.isfile(path):
            logger.info("Скачивание модели Silero (%s)...", MODEL_FILENAME)
            torch.hub.download_url_to_file(MODEL_URL, path, progress=True)
        logger.info("Загрузка модели Silero v4_ru (baya)...")
        imp = package.PackageImporter(path)
        model = imp.load_pickle("tts_models", "model")
        if hasattr(model, "eval"):
            model.eval()
        try:
            model.to(torch.device("cpu"))
        except Exception:
            pass
        _model = model
        logger.info("Модель Silero v4_ru готова")
    return _model


def _build_ssml(text: str, preset: dict) -> str:
    safe = html.escape(text.strip(), quote=False)
    return (
        "<speak>"
        f"<prosody pitch='{preset['pitch']}' rate='{preset['rate']}'>"
        f"{safe}</prosody>"
        "</speak>"
    )


def _audio_to_pcm(audio, model) -> Any:
    import numpy as np

    seq = audio[0] if isinstance(audio, (list, tuple)) else audio
    if hasattr(seq, "detach"):
        seq = seq.detach().cpu()
        arr = seq.numpy()
    else:
        arr = seq
    if arr.ndim > 1:
        arr = arr[0]
    arr = np.clip(np.asarray(arr, dtype=np.float32), -1.0, 1.0)
    return (arr * 32767.0).astype(np.int16)


def _write_wav(pcm, path: str, sample_rate: int) -> None:
    import wave

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _new_wav_path() -> str:
    fd, path = tempfile.mkstemp(prefix="silero_miku_", suffix=".wav")
    os.close(fd)
    return path


def synthesize(text: str, personality: str | None = None) -> str:
    """Синтез SSML-фразы по характеру, сохранение .wav, возврат пути."""
    model = _load_model()
    preset = PERSONALITY_PRESETS.get((personality or "").strip(), DEFAULT_PRESET)
    ssml = _build_ssml(text[:_MAX_INPUT_CHARS], preset)

    audio = model.apply_tts(
        ssml_text=ssml,
        speaker=preset["voice"],
        sample_rate=SAMPLE_RATE,
        put_accent=True,
        put_yo=True,
    )

    pcm = _audio_to_pcm(audio, model)
    wav_path = _new_wav_path()
    _write_wav(pcm, wav_path, SAMPLE_RATE)
    return wav_path


def speak_text_as_miku(text: str, personality: str | None = None) -> None:
    """Синтез + воспроизведение подряд; одна очередь — без наложения дорожек."""
    from miku_tts import play_wav_file

    with _tts_chain_lock:
        wav_path = synthesize(text, personality)
        play_wav_file(wav_path)


def warmup(delay_sec: float = 2.5) -> None:
    """Фоновый прогрев: скачивание и загрузка модели до первого нажатия 🔊."""
    time.sleep(delay_sec)
    try:
        _load_model()
        logger.info("Silero TTS: модель прогрета")
    except Exception as e:
        logger.debug("Silero TTS warmup пропущено: %s", e)