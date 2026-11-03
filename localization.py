# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache

from paths import resource_path

LANGUAGE_CODES = ("ru", "kk", "uk", "en")


@lru_cache(maxsize=1)
def get_locales() -> dict[str, dict]:
    path = resource_path("translations.json")
    if not os.path.isfile(path) and getattr(sys, "frozen", False):
        path = os.path.join(os.path.dirname(sys.executable), "translations.json")
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load translation catalogue {path}: {exc}") from exc

    locales = data.get("languages") if isinstance(data, dict) else None
    if not isinstance(locales, dict) or set(locales) != set(LANGUAGE_CODES):
        raise ValueError("translations.json must define ru, kk, uk, and en locales")

    reference = locales["ru"]
    for code, locale in locales.items():
        if not isinstance(locale, dict):
            raise TypeError(f"Locale {code!r} must be an object")
        for section in ("name", "ui", "personalities", "prompt"):
            if section not in locale:
                raise ValueError(f"Locale {code!r} is missing {section!r}")
        if set(locale["ui"]) != set(reference["ui"]):
            raise ValueError(f"Locale {code!r} has a different UI translation key set")
        if set(locale["personalities"]) != set(reference["personalities"]):
            raise ValueError(f"Locale {code!r} has a different personality key set")
        if set(locale["prompt"]) != set(reference["prompt"]):
            raise ValueError(f"Locale {code!r} has a different prompt key set")
        for key in ("essence", "personalities", "romance_styles"):
            expected = set(reference["prompt"][key])
            if set(locale["prompt"][key]) != expected:
                raise ValueError(f"Locale {code!r} has a different {key} translation key set")

    return locales


def locale_for(language: str) -> dict:
    try:
        return get_locales()[language]
    except KeyError as exc:
        raise ValueError(f"Unsupported language code: {language!r}") from exc


def text(language: str, section: str, key: str, **values: object) -> str:
    try:
        value = locale_for(language)[section][key]
    except KeyError as exc:
        raise KeyError(f"Missing translation: {language}.{section}.{key}") from exc
    if not isinstance(value, str):
        raise TypeError(f"Translation {language}.{section}.{key} must be a string")
    return value.format(**values) if values else value
