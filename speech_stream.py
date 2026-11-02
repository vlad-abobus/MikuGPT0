# -*- coding: utf-8 -*-
"""Синхронная потоковая озвучка ответа.

Текст от LLM поступает в :meth:`SpeechStream.feed`. Модуль режет его на фразы,
синтезирует по очереди и вызывает ``on_phrase(seq, text)`` ровно в момент,
когда начинается воспроизведение этой фразы. Благодаря этому интерфейс может
показывать реплику вместе с голосом, а не раньше и не позже.

Синтез и воспроизведение идут в отдельных потоках: пока звучит фраза N,
фраза N+1 уже синтезируется.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any, Callable

from tts_text import StreamingSpeechBuffer, clean_text_for_tts

logger = logging.getLogger(__name__)


class SpeechStream:
    """Очередь «текст → синтез → воспроизведение» с синхронными колбэками."""

    def __init__(
        self,
        synthesize: Callable[[str], str],
        *,
        on_phrase: Callable[[int, str], None],
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        play: Callable[[str], None] | None = None,
        max_chunk: int = 220,
    ) -> None:
        self._synthesize = synthesize
        self._on_phrase = on_phrase
        self._on_done = on_done
        self._on_error = on_error
        self._play = play

        self._buffer = StreamingSpeechBuffer(max_chunk=max_chunk)
        self._synth_q: "queue.Queue[Any]" = queue.Queue()
        self._play_q: "queue.Queue[Any]" = queue.Queue()
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._finished = threading.Event()

        self._started = False
        self._finishing = False
        self._error_reported = False
        self._seq = 0

    # ---------- публичное API ----------

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def start(self) -> None:
        """Запустить фоновые потоки синтеза и воспроизведения."""
        with self._lock:
            if self._started:
                return
            self._started = True
        threading.Thread(
            target=self._synth_worker, name="miku-sync-synth", daemon=True
        ).start()
        threading.Thread(
            target=self._play_worker, name="miku-sync-play", daemon=True
        ).start()

    def feed(self, text: str | None) -> None:
        """Добавить очередной кусок ответа LLM."""
        if not text or self._cancelled.is_set():
            return
        with self._lock:
            if self._finishing:
                return
            for chunk in self._buffer.feed(text):
                self._enqueue_chunk(chunk)

    def finish(self) -> None:
        """Завершить приём текста и доиграть оставшиеся фразы."""
        with self._lock:
            if self._finishing:
                return
            self._finishing = True
            for chunk in self._buffer.finish():
                self._enqueue_chunk(chunk)
            self._synth_q.put(None)

    def cancel(self) -> None:
        """Остановить озвучку и выбросить ещё не проигранные фразы."""
        self._cancelled.set()
        self._drain_queue(self._synth_q)
        self._drain_queue(self._play_q)
        try:
            from audio_player import stop_playback

            stop_playback()
        except Exception:
            pass
        self._synth_q.put(None)
        self._play_q.put(None)

    def wait_finished(self, timeout: float | None = None) -> bool:
        return self._finished.wait(timeout)

    # ---------- внутреннее ----------

    def _enqueue_chunk(self, chunk: str) -> None:
        if not chunk or not chunk.strip():
            return
        self._seq += 1
        self._synth_q.put((self._seq, chunk))

    def _synth_worker(self) -> None:
        sent = False
        try:
            while True:
                item = self._synth_q.get()
                if item is None:
                    self._play_q.put(None)
                    sent = True
                    return
                seq, text = item
                if self._cancelled.is_set():
                    continue

                # Действия в звёздочках и каомодзи не озвучиваются: сразу
                # показываем фразу и идём дальше, без ошибки синтеза.
                if not clean_text_for_tts(text).strip():
                    self._play_q.put((seq, text, None))
                    continue

                path: str | None = None
                try:
                    path = self._synthesize(text)
                except Exception as exc:
                    if not self._cancelled.is_set():
                        self._report_error(exc)

                if self._cancelled.is_set():
                    self._remove_file(path)
                    continue
                self._play_q.put((seq, text, path))
        finally:
            if not sent:
                self._play_q.put(None)

    def _play_worker(self) -> None:
        try:
            while True:
                item = self._play_q.get()
                if item is None:
                    return
                seq, text, path = item
                if self._cancelled.is_set():
                    self._remove_file(path)
                    continue

                # Фраза показывается ровно в момент старта её аудио.
                try:
                    self._on_phrase(seq, text)
                except Exception:
                    logger.debug("SpeechStream: ошибка on_phrase", exc_info=True)

                if not path:
                    continue
                try:
                    self._play_audio(path)
                except Exception as exc:
                    if not self._cancelled.is_set():
                        self._report_error(exc)
                finally:
                    self._remove_file(path)
        finally:
            self._finished.set()
            if not self._cancelled.is_set() and self._on_done is not None:
                try:
                    self._on_done()
                except Exception:
                    logger.debug("SpeechStream: ошибка on_done", exc_info=True)

    def _play_audio(self, path: str) -> None:
        if self._play is not None:
            self._play(path)
            return
        from audio_player import play_wav_file

        play_wav_file(path)

    def _report_error(self, exc: BaseException) -> None:
        logger.warning("SpeechStream: фраза не озвучена: %s", exc)
        if self._error_reported:
            return
        self._error_reported = True
        if self._on_error is not None:
            try:
                self._on_error(exc)
            except Exception:
                logger.debug("SpeechStream: ошибка on_error", exc_info=True)

    @staticmethod
    def _remove_file(path: str | None) -> None:
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    @classmethod
    def _drain_queue(cls, q: "queue.Queue[Any]") -> None:
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                return
            if isinstance(item, tuple) and len(item) == 3:
                cls._remove_file(item[2])

