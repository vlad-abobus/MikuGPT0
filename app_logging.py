# -*- coding: utf-8 -*-
"""Единая настройка логирования: консоль + ротация файла рядом с exe / проектом."""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOG_DIR_NAME = "logs"
_LOG_FILE_NAME = "mikugpt.log"
_MAX_BYTES = 1_048_576
_BACKUP_COUNT = 5


def _app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _parse_level(name: str | None) -> int:
    if not name:
        return logging.INFO
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(name.strip().upper(), logging.INFO)


def setup_logging() -> None:
    """
    Инициализация root-логгера (идемпотентно).
    Уровень: переменная окружения MIKUGPT_LOG_LEVEL (DEBUG/INFO/WARNING/ERROR), иначе INFO.
    Файл: <base>/logs/mikugpt.log с ротацией; при ошибке записи — только stderr.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    level = _parse_level(os.environ.get("MIKUGPT_LOG_LEVEL"))
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(level)
    stderr.setFormatter(fmt)
    root.addHandler(stderr)

    log_path = ""
    try:
        log_dir = os.path.join(_app_base_dir(), _LOG_DIR_NAME)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, _LOG_FILE_NAME)
        fh = RotatingFileHandler(
            log_path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        logging.getLogger(__name__).warning(
            "Не удалось создать файл лога в %s — пишем только в консоль",
            os.path.join(_app_base_dir(), _LOG_DIR_NAME),
        )

    for name in ("urllib3", "requests", "httpx", "httpcore", "gradio_client"):
        logging.getLogger(name).setLevel(max(logging.WARNING, level))

    log = logging.getLogger(__name__)
    if log_path:
        log.info("Логи: %s", log_path)
    else:
        log.info("Логи только в stderr (файл недоступен)")
