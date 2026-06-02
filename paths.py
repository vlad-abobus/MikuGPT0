# -*- coding: utf-8 -*-
"""Пути к ресурсам: dev и PyInstaller (sys._MEIPASS)."""
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def config_json_path() -> str:
    """Путь к config.json для записи и приоритетного чтения: рядом с exe в PyInstaller, иначе папка проекта."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def read_config_json() -> dict:
    """Сначала пользовательский config рядом с exe/в проекте, иначе встроенный из _MEIPASS (однофайловая сборка)."""
    primary = config_json_path()
    if os.path.exists(primary):
        try:
            with open(primary, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            logger.warning("Не удалось прочитать config %s: %s", primary, e)
    bundled = resource_path("config.json")
    if os.path.exists(bundled):
        try:
            with open(bundled, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            logger.warning("Не удалось прочитать встроенный config %s: %s", bundled, e)
    return {}


def write_config_json(data: dict) -> None:
    """Запись только в пользовательский config (рядом с exe или каталог проекта), не в read-only _MEIPASS."""
    path = config_json_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        logger.exception("Не удалось записать config.json: %s", path)
        raise
