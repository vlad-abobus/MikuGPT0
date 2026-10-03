# -*- coding: utf-8 -*-
"""Локальная RVC-озвучка: Edge-TTS (промежуточный голос) → rvc-python (модель Мику из voice/).

Используются файлы из voice/: infamous_miku_v2 (модель), *.index (интонации),
hubert_base.pt и rmvpe.pt (базовые модели копируются в пакет rvc_python, чтобы не скачивать).
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import shutil
import tempfile
import threading
import time
from typing import Any

from paths import resource_path

logger = logging.getLogger(__name__)

# Файлы модели в папке voice/ рядом с проектом.
VOICE_DIR = resource_path("voice")
MODEL_PTH = os.path.join(VOICE_DIR, "infamous_miku_v2", "infamous_miku_v2.pth")
INDEX_FILE = os.path.join(
    VOICE_DIR, "infamous_miku_v2", "added_IVF2983_Flat_nprobe_1_infamous_miku_v2_v2.index"
)
HUBERT_PT = os.path.join(VOICE_DIR, "hubert_base.pt")
RMVPE_PT = os.path.join(VOICE_DIR, "rmvpe.pt")

# Аниме-профиль: та же модель Мику (infamous_miku_v2), но с аниме-раскладкой
# (rmvpe, pitch +6, index 0.70) — без отдельной модели Senko.
ANIME_PTH = os.path.join(VOICE_DIR, "infamous_miku_v2", "infamous_miku_v2.pth")
ANIME_INDEX = os.path.join(
    VOICE_DIR, "infamous_miku_v2", "added_IVF2983_Flat_nprobe_1_infamous_miku_v2_v2.index"
)

_VOICE_MIKU = "miku"
_VOICE_ANIME = "anime"
_VOICES = (_VOICE_MIKU, _VOICE_ANIME)

# Версия модели RVC. Для v1-моделей поставьте "v1".
MODEL_VERSION = "v2"

# Edge-TTS голоса: реалистичные имена (проверено edge-tts 7.2.8).
_TTS_VOICE_RU = "ru-RU-SvetlanaNeural"
_TTS_VOICE_JP = "ja-JP-NanamiNeural"
_MAX_INPUT_CHARS = 900

# Ключ config.json: True → rmvpe + index 1.0 (якість), False → pm + 0.75 (швидкість).
_CONFIG_KEY_TTS_QUALITY = "miku_tts_high_quality"

_rvc: Any = None
_rvc_lock = threading.Lock()
_rvc_error: str | None = None
_rvc_voice: str | None = None
_tts_chain_lock = threading.Lock()

# Активный голос озвучки: "miku" или "anime" (обе — модель Мику, разные профили).
_active_voice: str = _VOICE_MIKU

# --- Инкрементальная (потоковая) озвучка, как в miku_tts.py / silero_tts.py. ---
_STREAM_LOCK = threading.Lock()
_stream_tx: "queue.Queue[str | None]" | None = None
_stream_audio: "queue.Queue[str | None]" | None = None
_stream_started = False
_stream_done_cb: Any = None


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
                wav = generate_miku_voice(text)
                audio_q.put(wav)
            except Exception:
                logger.warning("Потоковая озвучка RVC: кусок не синтезирован", exc_info=True)
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
                logger.warning("Потоковая озвучка RVC: воспроизведение куска не удалось", exc_info=True)
    finally:
        if done_cb:
            try:
                done_cb()
            except Exception:
                pass


def start_chunked_speech(done_callback: Any = None) -> None:
    """Начать потоковую озвучку RVC: потоки синтеза и воспроизведения."""
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
    """Положить кусок текста в потоковую очередь озвучки RVC."""
    with _STREAM_LOCK:
        tx = _stream_tx
    if tx is not None and (text or "").strip():
        try:
            tx.put_nowait(text)
        except Exception:
            logger.warning("Потоковая озвучка RVC: очередь переполнена, кусок пропущен", exc_info=True)


def finish_chunked_speech() -> None:
    """Завершить потоковую озвучку RVC: sentinel, после доигрывания — done_cb."""
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


def _voice_model_paths(voice: str) -> tuple[str, str]:
    """(путь к .pth, путь к .index) для голоса озвучки."""
    if voice == _VOICE_ANIME:
        return ANIME_PTH, ANIME_INDEX
    return MODEL_PTH, INDEX_FILE


def _voice_rvc_params(voice: str) -> dict:
    """Параметры RVC-конверсии для голоса (f0, транспонирование, index_rate...).

    miku — как конфиг (rmvpe + index 1.0 / pm + 0.75 для скорости);
    anime — аниме-профиль: rmvpe, pitch +6, index_rate 0.70.
    """
    try:
        from paths import read_config_json

        raw = (read_config_json() or {}).get(_CONFIG_KEY_TTS_QUALITY, True)
        high = bool(raw) if raw is not None else True
    except Exception:
        high = True
    if voice == _VOICE_ANIME:
        return {
            "f0method": "rmvpe",
            "f0up_key": 6,
            "index_rate": 0.70,
            "filter_radius": 3,
            "rms_mix_rate": 1,
            "protect": 0.33,
        }
    return {
        "f0method": "rmvpe" if high else "pm",
        "f0up_key": 0,
        "index_rate": 1.0 if high else 0.75,
        "filter_radius": 3,
        "rms_mix_rate": 1,
        "protect": 0.33,
    }


def _apply_voice_to_rvc(rvc: Any, voice: str) -> None:
    """Загрузить веса голоса и применить его параметры конверсии."""
    pth, index = _voice_model_paths(voice)
    if not os.path.isfile(pth):
        raise RuntimeError(f"RVC: модель не найдена: {pth}")
    if index and not os.path.isfile(index):
        logger.warning("RVC: индекс не найден: %s", index)
        index = ""
    rvc.load_model(pth, version=MODEL_VERSION, index_path=index)
    rvc.set_params(**_voice_rvc_params(voice))


def set_active_voice(voice: str) -> None:
    """Выбрать голос озвучки: 'miku' или 'anime' (обе — модель Мику, разные профили)."""
    global _active_voice, _rvc_voice
    v = (voice or _VOICE_MIKU).strip().lower()
    if v not in _VOICES:
        raise ValueError(f"Неизвестный голос озвучки: {voice}")
    with _rvc_lock:
        if _active_voice == v and _rvc_voice == v:
            return
        _active_voice = v
        if _rvc is not None:
            _apply_voice_to_rvc(_rvc, v)
            _rvc_voice = v
            logger.info("RVC: переключён голос на %s", v)


def _detect_device() -> str:
    """cuda:0 если есть CUDA-карта, иначе cpu:0."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        return "cpu:0"
    except Exception:
        return "cpu:0"


def _copy_bundled_base_models() -> None:
    """Положить hubert/rmvpe из voice/ в пакет rvc_python/base_model (не скачивать с HF)."""
    try:
        import rvc_python
    except ImportError:
        return
    base = os.path.join(os.path.dirname(rvc_python.__file__), "base_model")
    os.makedirs(base, exist_ok=True)
    for src, name in ((HUBERT_PT, "hubert_base.pt"), (RMVPE_PT, "rmvpe.pt")):
        if not os.path.isfile(src):
            continue
        target = os.path.join(base, name)
        if os.path.isfile(target):
            continue
        try:
            shutil.copyfile(src, target)
            logger.info("RVC: базовые файлы скопированы в %s", target)
        except Exception:
            logger.warning("RVC: не удалось скопировать %s → %s", src, target)


def _patch_torch_load() -> None:
    """torch 2.6+ по умолчанию weights_only=True, а чекпоинты HuBERT содержат безопасные globals fairseq.
    Переопределяем дефолт на weights_only=False, если вызывающий код не задал флаг явно."""
    try:
        import torch

        orig = torch.load

        def _load(*args, **kwargs):
            if "weights_only" not in kwargs:
                kwargs["weights_only"] = False
            return orig(*args, **kwargs)

        torch.load = _load  # type: ignore[assignment]
    except Exception as e:
        logger.debug("Не удалось пропатчить torch.load: %s", e)


def _ensure_rvc(voice: str | None = None) -> Any:
    """Ленивая инициализация RVC (модель грузится в память один раз)."""
    global _rvc, _rvc_error, _rvc_voice
    voice = voice or _active_voice
    if _rvc is not None and _rvc_voice == voice:
        return _rvc
    with _rvc_lock:
        if _rvc is not None and _rvc_voice == voice:
            return _rvc
        if _rvc_error:
            raise RuntimeError(_rvc_error)
        try:
            _patch_torch_load()
            _copy_bundled_base_models()
            from rvc_python.infer import RVCInference

            device = _detect_device()
            logger.info(
                "RVC: инициализация на %s, голос %s, модель %s",
                device,
                voice,
                os.path.basename(_voice_model_paths(voice)[0]),
            )
            if _rvc is None:
                _rvc = RVCInference(device=device)
            _apply_voice_to_rvc(_rvc, voice)
            _rvc_voice = voice
            logger.info("RVC: модель готова (%s, голос %s)", device, voice)
        except ImportError as e:
            _rvc_error = (
                "Локальный RVC: не установлены зависимости (rvc-python, torch, fairseq). "
                "Выполните: pip install -r requirements.txt"
            )
            raise RuntimeError(_rvc_error) from e
        except Exception as e:
            _rvc_error = f"Локальный RVC: ошибка загрузки модели: {e}"
            raise RuntimeError(_rvc_error) from e
    return _rvc


def _prepare_tts_text(text: str) -> str:
    """Текст для синтеза: очистка от эмоций/RP-вставок/каомодзи + обрезка по длине."""
    from tts_text import clean_text_for_tts

    t = clean_text_for_tts(text)
    if len(t) > _MAX_INPUT_CHARS:
        t = t[:_MAX_INPUT_CHARS]
    return t


def _is_japanese(text: str) -> bool:
    return any("\u3040" <= ch <= "\u30ff" for ch in text)


def _new_wav_path() -> str:
    fd, path = tempfile.mkstemp(prefix="miku_rvc_", suffix=".wav")
    os.close(fd)
    return path


def _edge_tts_to_wav(text: str, voice: str) -> str:
    """Edge-TTS → временный .wav (промежуточный голос для конверсии). Чуть быстрее темп."""
    import edge_tts

    fd, path = tempfile.mkstemp(prefix="miku_rvc_in_", suffix=".wav")
    os.close(fd)
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate="+10%")
        asyncio.run(communicate.save(path))
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        raise
    return path


def _trim_silence(path: str, margin: float = 0.05) -> str:
    """Обрезать тишину по краям .wav (16-bit PCM) — фразы идут подряд почти без паузы."""
    import wave

    import numpy as np

    try:
        with wave.open(path, "rb") as w:
            params = w.getparams()
            if params.sampwidth != 2:
                return path
            sr = params.framerate
            nch = params.nchannels
            frames = w.readframes(params.nframes)
        data = np.frombuffer(frames, dtype=np.int16)
        if data.size == 0:
            return path
        amp = np.abs(data.reshape(-1, nch).max(axis=1)) if nch > 1 else np.abs(data)
        peak = int(amp.max()) if amp.size else 0
        if peak <= 256:
            return path
        thr = max(400, int(peak * 0.02))
        active = np.flatnonzero(amp > thr)
        if active.size == 0:
            return path
        start = max(0, int(active[0] - margin * sr))
        end = min(amp.size, int(active[-1] + margin * sr + 1))
        if end - start >= amp.size:
            return path
        out = data[start * nch : end * nch]
        tmp = path + ".tmp.wav"
        with wave.open(tmp, "wb") as w:
            w.setnchannels(nch)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(out.tobytes())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(path + ".tmp.wav")
        except Exception:
            pass
    return path


def generate_miku_voice(text: str, voice: str | None = None) -> str:
    """Синтез: Edge-TTS (русский/японский) → локальный RVC-инференс. Возвращает путь к .wav."""
    voice = voice or _active_voice
    rvc = _ensure_rvc(voice)
    speech = _prepare_tts_text(text)
    if not speech:
        raise ValueError("Пустой текст для озвучки")

    voice = _TTS_VOICE_JP if _is_japanese(speech) else _TTS_VOICE_RU
    raw = _edge_tts_to_wav(speech, voice)
    try:
        out_path = _new_wav_path()
        rvc.infer_file(raw, out_path)
        _trim_silence(out_path)
    finally:
        try:
            os.remove(raw)
        except Exception:
            pass
    return out_path


def play_wav_file(path: str) -> None:
    """Воспроизведение .wav через pygame (та же реализация, что и остальные движки)."""
    from miku_tts import play_wav_file as _play

    _play(path)


def _synth_chunks_worker(
    chunks: list[str], voice: str | None, q: "queue.Queue[str | None]"
) -> None:
    """Синтез фраз по очереди в фоне: звук фразы N готов, пока играет N-1."""
    try:
        for chunk in chunks:
            try:
                wav = generate_miku_voice(chunk, voice=voice)
                q.put(wav)
            except Exception:
                logger.warning("RVC: фраза не синтезирована: %s", chunk[:40])
    finally:
        q.put(None)


def _play_chunked(text: str, voice: str | None = None) -> None:
    """Озвучить текст по предложениям, начиная с первого предложения сразу.

    Синтез следующих фраз идёт в фоне параллельно с воспроизведением текущей —
    так озвучка стартует быстро и читает «по точкам»."
    """
    from tts_text import split_for_tts

    chunks = split_for_tts(text)
    if not chunks:
        return
    if len(chunks) == 1:
        wav = generate_miku_voice(chunks[0], voice=voice)
        try:
            play_wav_file(wav)
        finally:
            try:
                os.remove(wav)
            except Exception:
                pass
        return

    q: "queue.Queue[str | None]" = queue.Queue(maxsize=6)
    threading.Thread(
        target=_synth_chunks_worker, args=(chunks, voice, q), daemon=True
    ).start()
    while True:
        item = q.get()
        if item is None:
            break
        try:
            play_wav_file(item)
        finally:
            try:
                os.remove(item)
            except Exception:
                pass


def speak_text_as_miku(text: str, voice: str | None = None) -> None:
    """Синтез + воспроизведение подряд по предложениям; одна очередь — без наложения дорожек."""
    with _tts_chain_lock:
        _play_chunked(text, voice=voice)


def warmup(delay_sec: float = 2.5, voice: str | None = None) -> None:
    """Фоновый прогрев: копирование базовых файлов и загрузка модели до первого нажатия 🔊."""
    time.sleep(delay_sec)
    try:
        if voice:
            set_active_voice(voice)
        _ensure_rvc()
        logger.info("Локальный RVC: модель прогрета")
    except Exception as e:
        logger.debug("Локальный RVC warmup пропущено: %s", e)