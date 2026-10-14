# -*- coding: utf-8 -*-
"""Управление отдельным окном 3D-панды (процесс ``panda_viewer.py``).

Основной процесс (Tkinter) запускает ``panda_viewer.py`` как дочерний процесс и
отправляет ему команды по localhost TCP. Это нужно, потому что pywebview требует
запуска GUI-цикла в главном потоке и не может сосуществовать с Tk mainloop в одном
процессе.
"""
import logging
import os
import socket
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _connect(port: int, timeout: float = 20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.5)
            s.connect(("127.0.0.1", port))
            s.settimeout(None)
            return s
        except OSError:
            try:
                s.close()
            except OSError:
                pass
            time.sleep(0.25)
    return None


class PandaWindowController:
    """Запускает окно-панду и шлёт ему команды. Молча деградирует при ошибках."""

    def __init__(self) -> None:
        self._proc = None
        self._sock = None
        self._lock = threading.Lock()

    def start(self, html_path: str, x: int, y: int, width: int = 300, height: int = 380) -> None:
        if self._proc is not None:
            return
        try:
            port = _free_port()
        except OSError as e:
            logger.warning("Не удалось выбрать порт для окна панды: %s", e)
            return

        cmd = self._build_cmd(port, html_path, width, height, x, y)
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        try:
            self._proc = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            logger.warning("Не удалось запустить окно панды: %s", e)
            self._proc = None
            return

        threading.Thread(target=self._connect_worker, args=(port,), daemon=True).start()

    @staticmethod
    def _viewer_args(port: int, html: str, width: int, height: int, x: int, y: int):
        return [
            "--port", str(port),
            "--html", str(html),
            "--width", str(width),
            "--height", str(height),
            "--x", str(x),
            "--y", str(y),
        ]

    def _build_cmd(self, port: int, html: str, width: int, height: int, x: int, y: int):
        args = self._viewer_args(port, html, width, height, x, y)
        if getattr(sys, "frozen", False):
            return [sys.executable, "--panda-viewer"] + args
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panda_viewer.py")
        return [sys.executable, script] + args

    def _connect_worker(self, port: int) -> None:
        sock = _connect(port)
        if sock is None:
            logger.warning("Окно панды не ответило на порт %s", port)
            return
        with self._lock:
            if self._proc is None:
                try:
                    sock.close()
                except OSError:
                    pass
                return
            self._sock = sock

    def send(self, cmd: str) -> None:
        with self._lock:
            sock = self._sock
        if sock is None:
            return
        try:
            sock.sendall((cmd + "\n").encode("utf-8"))
        except OSError as e:
            logger.debug("Не удалось отправить команду панде (%s): %s", cmd, e)
            with self._lock:
                self._sock = None

    def stop(self) -> None:
        self.send("quit")
        with self._lock:
            proc, self._proc = self._proc, None
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
