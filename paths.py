# -*- coding: utf-8 -*-
"""Пути к ресурсам: dev и PyInstaller (sys._MEIPASS)."""
from __future__ import annotations
import json
import logging
import os
import re
import sys
import threading
import time

logger = logging.getLogger(__name__)

# Защита от гонок при чтении-модификации-записи config.json из разных потоков.
# Reentrant: update_config_json держит замок и вызывает read/write внутри.
_CONFIG_LOCK = threading.RLock()

# .env загружаем один раз при первом импорте paths — его импортируют и main,
# и gemini_client, и fish_tts, поэтому переменные доступны всем.
_ENV_LOCK = threading.Lock()
_ENV_LOADED = False
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def env_file_path() -> str:
    """Путь к .env: рядом с exe в PyInstaller, иначе в папке проекта."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), ".env")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _parse_env_line(raw: str) -> tuple[str, str] | None:
    line = (raw or "").strip()
    if not line or line.startswith("#"):
        return None
    if line.lower().startswith("export "):
        line = line[7:].lstrip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not _ENV_KEY_RE.match(key):
        return None
    value = value.strip()
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = (
                value.replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
    else:
        # Комментарий после значения: KEY=value  # пояснение
        comment = re.search(r"\s+#", value)
        if comment:
            value = value[: comment.start()].rstrip()
    return key, value


def load_env_file(path: str | None = None) -> bool:
    """Загрузить .env в os.environ, не перезаписывая уже заданные переменные.

    Реальные переменные окружения имеют приоритет над файлом — удобно для CI
    и временной подмены ключей. Возвращает True, если файл был прочитан.
    """
    global _ENV_LOADED
    with _ENV_LOCK:
        if _ENV_LOADED and path is None:
            return True
        target = path or env_file_path()
        try:
            with open(target, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
        except OSError:
            if path is None:
                _ENV_LOADED = True
            return False

        loaded = 0
        for raw in lines:
            parsed = _parse_env_line(raw)
            if parsed is None:
                continue
            key, value = parsed
            if key not in os.environ:
                os.environ[key] = value
                loaded += 1
        if path is None:
            _ENV_LOADED = True
        logger.debug("Загружено переменных из %s: %s", target, loaded)
        return True


# При импорте paths .env должен быть доступен раньше, чем gemini_client/fish_tts
# начнут читать ключи.
load_env_file()


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


def _read_unlocked(path: str) -> dict | None:
    """Читает JSON; None = файла нет / не читается (после ретраев)."""
    if not os.path.exists(path):
        return None
    for attempt in range(3):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            # Файл может быть недописан параллельным потоком — ретрай.
            if attempt < 2:
                time.sleep(0.02)
                continue
            logger.warning("config %s не читается (после ретраев)", path)
            return None
    return None


def read_config_json() -> dict:
    """Пользовательский config рядом с exe/в проекте. Встроенный — только если пользовательского ещё нет."""
    with _CONFIG_LOCK:
        primary = config_json_path()
        data = _read_unlocked(primary)
        if data is not None:
            return data
        if os.path.exists(primary):
            # Файл есть, но битый: НЕ подставляем встроенный (в нём нет памяти) —
            # иначе следующая запись сотрёт chat_history/user_memory.
            return {}
    bundled = resource_path("config.json")
    if os.path.exists(bundled):
        try:
            with open(bundled, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            logger.warning("Не удалось прочитать встроенный config %s: %s", bundled, e)
    return {}


def write_config_json(data: dict) -> None:
    """Атомарная запись только в пользовательский config (рядом с exe или каталог проекта)."""
    with _CONFIG_LOCK:
        path = config_json_path()
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)  # атомарно: читатели видят старый или новый файл целиком
        except OSError:
            logger.exception("Не удалось записать config.json: %s", path)
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


def update_config_json(updates: dict) -> dict:
    """Атомарное read-modify-write: читает, применяет правки, пишет под одним замком."""
    with _CONFIG_LOCK:
        cfg = read_config_json()
        cfg.update(updates)
        write_config_json(cfg)
        return cfg
