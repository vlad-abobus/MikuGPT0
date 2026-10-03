# -*- coding: utf-8 -*-
"""Эмоции для наборов A / B / C.

Источник истины — файл emotions.json (подписи + описания для промпта).
Если файла нет или он битый — используем встроенный фолбэк ниже.
"""
from __future__ import annotations

import logging
import os

from paths import resource_path

logger = logging.getLogger(__name__)

DEFAULT_SET = "C"
ALL_SETS = ("A", "B", "C")

EMOTIONS_JSON_PATH = resource_path(os.path.join("emotions.json"))

# Встроенный фолбэк (если emotions.json отсутствует/повреждён)
EMOTIONS_A = {
    "angry_look": "Злой взгляд",
    "embarrassed": "Смущение",
    "middle_finger_anger": "Средний палец",
    "shocked2": "Шок 2",
    "apologetic": "Извинение",
    "happy_idle": "Счастье (спокойное)",
    "neutral2": "Нейтральное 2",
    "shocked": "Шок",
    "cheerful": "Радость",
    "happy": "Счастье",
    "neutral3": "Нейтральное 3",
    "surprised": "Удивление",
    "crying": "Плач",
    "irritated": "Раздражение",
    "sad_look": "Грусть",
}

EMOTIONS_B = {
    "angryM": "Злость",
    "coolM": "Спокойствие",
    "helloM": "Приветствие",
    "interestedM": "Интерес",
    "open_mouthM": "Открытый рот",
    "sayingM": "Разговор",
    "shyM": "Смущение",
    "sly_smileM": "Хитрая улыбка",
    "smileR_M": "Улыбка",
}

EMOTIONS_C = {
    "aggressiv_comedy": "Агрессивная комедия",
    "angry_surprised": "Злость + удивление",
    "annoyed": "Раздражение",
    "blushing": "Смущение (краснеет)",
    "celebrate": "Праздник",
    "congratulations": "Поздравление",
    "crying": "Плач",
    "curios": "Любопытство",
    "defeated": "Поражение",
    "fight": "Боевой дух",
    "good_morning": "Доброе утро",
    "good_night": "Спокойной ночи",
    "happy_satisfaction": "Счастье (удовлетворение)",
    "happy_wait": "Счастье (ожидание)",
    "hi": "Привет",
    "hugging": "Обнимание",
    "im_counting_on_you": "Я на тебя надеюсь",
    "im_sorryyy": "Мне очень жаль",
    "love": "Любовь",
    "nice": "Милашка",
    "ok": "Согласие",
    "party": "Вечеринка",
    "peeking": "Подглядывание",
    "playful_pose": "Игривая поза",
    "please": "Пожалуйста",
    "relieved": "Облегчение",
    "scared": "Страх",
    "shy_request": "Стеснительная просьба",
    "sleeping": "Сон",
    "sleepy": "Сонливость",
    "surprise": "Сюрприз 1",
    "surprised": "Сюрприз 2",
    "take_a_break": "Отдохни",
    "thank_you": "Спасибо",
    "thank_you_soooo_much": "Большое спасибо",
    "thinking": "Размышление",
    "understood": "Понимание",
    "victory": "Победа",
    "withdrawn": "Застенчивость",
    "yeah": "Да!",
}

_FALLBACK_SETS = {
    "A": (EMOTIONS_A, "cheerful", "png"),
    "B": (EMOTIONS_B, "helloM", "jpg"),
    "C": (EMOTIONS_C, "hi", "png"),
}

# Структура, заполняемая из emotions.json.
# {set: {"emotions": {key: {"label": str, "desc": str}}, "greeting": str, "ext": str}}
_SETS: dict[str, dict] | None = None


def _load_sets() -> dict[str, dict]:
    global _SETS
    if _SETS is not None:
        return _SETS

    data: dict[str, dict] = {}
    loaded = False
    try:
        if os.path.exists(EMOTIONS_JSON_PATH):
            import json

            with open(EMOTIONS_JSON_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f) or {}
            raw_sets = raw.get("sets") or {}
            for set_key in ALL_SETS:
                block = raw_sets.get(set_key)
                if not isinstance(block, dict):
                    continue
                emotions_raw = block.get("emotions") or {}
                emotions: dict[str, dict[str, str]] = {}
                fallback_labels, greeting, ext = _FALLBACK_SETS[set_key]
                for key, emo in emotions_raw.items():
                    if not isinstance(emo, dict):
                        label = fallback_labels.get(key, key)
                        emotions[key] = {"label": label, "desc": label}
                    else:
                        label = (emo.get("label") or fallback_labels.get(key, key)).strip() or key
                        desc = (emo.get("desc") or "").strip() or label
                        emotions[key] = {"label": label, "desc": desc}
                akey = (block.get("greeting") or greeting or "").strip()
                aext = (block.get("ext") or ext or "png").strip()
                if emotions:
                    data[set_key] = {"emotions": emotions, "greeting": akey, "ext": aext}
                loaded = True
            if data:
                _SETS = data
                return data
    except Exception as e:
        logger.warning("Не удалось загрузить emotions.json: %s", e)

    if not loaded:
        _SETS = {}
        for set_key, (labels, greeting, ext) in _FALLBACK_SETS.items():
            _SETS[set_key] = {
                "emotions": {k: {"label": v, "desc": v} for k, v in labels.items()},
                "greeting": greeting,
                "ext": ext,
            }
    return _SETS


def emotion_keys_for_set(current_set: str) -> list[str]:
    s = (current_set or DEFAULT_SET).strip().upper()
    if s not in ALL_SETS:
        s = DEFAULT_SET
    return list(_load_sets()[s]["emotions"].keys())


def emotion_labels_for_set(current_set: str) -> dict[str, str]:
    s = (current_set or DEFAULT_SET).strip().upper()
    if s not in ALL_SETS:
        s = DEFAULT_SET
    return {k: v["label"] for k, v in _load_sets()[s]["emotions"].items()}


def emotion_descs_for_set(current_set: str) -> dict[str, str]:
    s = (current_set or DEFAULT_SET).strip().upper()
    if s not in ALL_SETS:
        s = DEFAULT_SET
    return {k: v["desc"] for k, v in _load_sets()[s]["emotions"].items()}


def emotion_ext_for_set(current_set: str) -> str:
    s = (current_set or DEFAULT_SET).strip().upper()
    if s not in ALL_SETS:
        s = DEFAULT_SET
    return _load_sets()[s]["ext"]


def default_greeting_emotion_key(emotion_set: str) -> str:
    """Стартовая / запасная эмоция «приветствие» для набора A, B или C."""
    s = (emotion_set or DEFAULT_SET).strip().upper()
    if s not in ALL_SETS:
        s = DEFAULT_SET
    return _load_sets()[s]["greeting"]


def pick_emotion(current_set: str, candidates: list[str] | tuple[str, ...]) -> str:
    """Первый ключ из candidates, который есть в наборе; иначе greeting-эмоция.

    Позволяет писать универсальные фолбэки вида
    pick_emotion(s, ["annoyed", "irritated", "angryM"]) — каждый набор
    получит свой валидный ключ, битые имена молча пропускаются.
    """
    valid = set(emotion_keys_for_set(current_set))
    for key in candidates:
        if key in valid:
            return key
    return default_greeting_emotion_key(current_set)


# Обратная совместимость: словари {ключ: подпись} для текущего набора C
EMOTIONS_C_LABELS = emotion_labels_for_set("C")