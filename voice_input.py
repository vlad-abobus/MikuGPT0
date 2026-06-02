# -*- coding: utf-8 -*-
"""Голосовой ввод через SpeechRecognition."""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class VoiceInputError(Exception):
    """Ошибка голосового ввода."""


class VoiceInput:
    """Асинхронный голосовой ввод с распознаванием речи."""

    def __init__(self) -> None:
        self._recognizer = None
        self._is_listening = False
        self._stop_bg = None
        self._available = False
        self._init_error: str | None = None
        self._sr = None

        try:
            import speech_recognition as sr
            self._sr = sr
            self._recognizer = sr.Recognizer()
            try:
                with sr.Microphone() as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                self._available = True
            except Exception as e:
                self._available = False
                self._init_error = f"Микрофон не найден: {e}"
        except ImportError:
            self._available = False
            self._init_error = (
                "SpeechRecognition не установлен.\n"
                "pip install SpeechRecognition pyaudio"
            )
        except Exception as e:
            self._available = False
            self._init_error = str(e)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_listening(self) -> bool:
        return self._is_listening

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def start(self, on_result, on_error=None, on_processing=None) -> None:
        if not self._available:
            if on_error:
                on_error(self._init_error or "Микрофон недоступен")
            return
        if self._is_listening:
            return

        self._is_listening = True
        self._processing = False

        def callback(recognizer, audio):
            self._is_listening = False
            self._processing = True
            if on_processing:
                on_processing()
            try:
                text = recognizer.recognize_google(audio, language="ru-RU")
                if on_result:
                    on_result(text)
            except self._sr.UnknownValueError:
                if on_error:
                    on_error("Не удалось распознать речь")
            except self._sr.RequestError as e:
                if on_error:
                    on_error(f"Ошибка сервиса распознавания: {e}")
            finally:
                self._processing = False

        def _start():
            try:
                with self._sr.Microphone() as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self._stop_bg = self._recognizer.listen_in_background(
                    self._sr.Microphone(), callback, phrase_time_limit=10
                )
            except Exception as e:
                self._is_listening = False
                if on_error:
                    on_error(f"Ошибка микрофона: {e}")

        threading.Thread(target=_start, daemon=True).start()

    def stop(self) -> None:
        self._is_listening = False
        if self._stop_bg:
            try:
                self._stop_bg(wait_for_stop=False)
            except Exception:
                pass
            self._stop_bg = None
