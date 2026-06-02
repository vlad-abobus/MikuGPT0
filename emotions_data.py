# -*- coding: utf-8 -*-
"""Ключи эмоций и подписи для наборов A / B / C."""

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

ALL_EMOTIONS_KEYS = list(EMOTIONS_A.keys()) + list(EMOTIONS_B.keys()) + list(EMOTIONS_C.keys())


def emotion_keys_for_set(current_set: str) -> list[str]:
    if current_set == "A":
        return list(EMOTIONS_A.keys())
    if current_set == "B":
        return list(EMOTIONS_B.keys())
    return list(EMOTIONS_C.keys())


def default_greeting_emotion_key(emotion_set: str) -> str:
    """Стартовая / запасная эмоция «приветствие» для набора A, B или C."""
    if emotion_set == "B":
        return "helloM"
    if emotion_set == "C":
        return "hi"
    # В наборе A нет отдельного «hi» — «Радость» как приветственное настроение
    return "cheerful"
