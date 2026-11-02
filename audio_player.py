# -*- coding: utf-8 -*-
"""Воспроизведение аудио и события для анимации панды.

Модуль общий для синхронной озвучки и ручной кнопки 🔊. Все дорожки играют
последовательно: pygame.mixer.music не умеет нормально микшировать несколько
потоков, поэтому доступ защищён RLock.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# RLock: play_wav_file сам берёт блокировку, а часть вызывающих уже держит её снаружи.
_play_lock = threading.RLock()

# Слушатель получает ("start", duration_ms), когда реально начинается звук,
# и ("end", 0), когда звук закончился (после небольшой паузы без новых фраз).
_playback_listener: Callable[[str, int], None] | None = None
_speech_active = False
_speech_end_timer: threading.Timer | None = None
_speech_state_lock = threading.Lock()
_SPEECH_GAP_SEC = 0.4


def set_playback_listener(listener: Callable[[str, int], None] | None) -> None:
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


def play_wav_file(path: str) -> None:
    """Воспроизвести .wav / .mp3 через pygame в текущем потоке."""
    import pygame

    with _play_lock:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            duration_ms = 0
            try:
                duration_ms = int(pygame.mixer.Sound(path).get_length() * 1000)
            except Exception:
                duration_ms = 0
            if duration_ms <= 0:
                duration_ms = 1000
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            _arm_speech(duration_ms)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.12)
        except Exception:
            logger.exception("Ошибка воспроизведения аудио: %s", path)
            raise
        finally:
            # Освобождаем файл: на Windows pygame держит его открытым, пока
            # трек загружен, и временный WAV нельзя удалить.
            try:
                if pygame.mixer.get_init() and hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except Exception:
                logger.debug("Не удалось выгрузить аудио", exc_info=True)


def stop_playback() -> None:
    """Остановить текущее аудио (например, при отмене синхронной озвучки)."""
    try:
        import pygame

        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
    except Exception:
        logger.debug("Не удалось остановить воспроизведение", exc_info=True)
    _fire_speech_end()
