# -*- coding: utf-8 -*-
"""Очистка текста для озвучки Мику.

Из ответа убирается всё, что не должно звучать:
- JSON-блок эмоции / тег {ключ} (если ещё не вырезан);
- RP-действия и мимика в звёздочках *вот так*;
- вставки в скобках: каомодзи (≧▽≦), звуки (хи-хи), действия (улыбается), хуки;
- эмодзи и декоративные значки (♪, ✧, 💙 и т.п.);
- запятые заменяются на пробелы, чтобы синтезатор не делал лишних пауз-вздохов.
"""
from __future__ import annotations

import re

_ASTERISK_ACTION = re.compile(r"\*[^*]*\*")
_PAREN_BLOCK = re.compile(r"\([^()]*\)")
_COMMA = re.compile(r",")
# JSON-блок эмоции {"emotion": "..."} и legacy-тег {ключ} в любом месте ответа.
_EMOTION_JSON = re.compile(r'\{\s*"emotion"\s*:\s*"[^"]*"\s*\}')
_LEGACY_TAG = re.compile(r"\{[A-Za-z0-9_]+\}")
# Декоративные символы, знакомые по ответам Мику (в т.ч. остатки каомодзи).
_DECOR_SYMBOLS = re.compile(
    r"[♪♫♬✧☆★⭐✨﹒❀❁♡♥❤💕💙💛💚💜🦋🌙☀️🍃🌺🌷💫🌊🔥"
    r"🌸🌼🌻🥰😘😊😍🥺🤗👍🙃😳😱🤍💋➰°ωΔд≧▽ヮ]_"
)
# Всё, кроме букв, цифр и нормальной пунктуации — на пробел.
_JUNK = re.compile(r"[^0-9A-Za-zА-Яа-яЁё.,!?…:;—\-«»\"' ]+")
# Пробел перед знаком препинания (после удаления символов) убираем.
_PRE_PUNCT_SPACE = re.compile(r"\s+([.,!?…;:])")
_SPACES = re.compile(r"\s+")

# Конец предложения: точка, восклицательный/вопросительный знак, многоточие, ; и :
_SENTENCE_END = re.compile(r"(?<=[.!?…;:])\s+")
# Жёсткий перенос длинных кусков не разрывая слова.
_HARD_MAX_CHUNK = 220


def clean_text_for_tts(text: str | None) -> str:
    """Вернуть текст, пригодный для синтеза речи."""
    if not text:
        return ""
    s = str(text)
    s = _EMOTION_JSON.sub(" ", s)
    s = _LEGACY_TAG.sub(" ", s)
    s = _ASTERISK_ACTION.sub(" ", s)
    s = _PAREN_BLOCK.sub(" ", s)
    s = _DECOR_SYMBOLS.sub(" ", s)
    s = _COMMA.sub(" ", s)
    s = _JUNK.sub(" ", s)
    s = _PRE_PUNCT_SPACE.sub(r"\1", s)
    s = _SPACES.sub(" ", s)
    return s.strip()


def _split_long_chunk(buf: str) -> list[str]:
    """Разбить слишком длинный кусок по пробелам (чтобы не разрывать слова)."""
    out: list[str] = []
    while len(buf) > _HARD_MAX_CHUNK:
        cut = buf.rfind(" ", 0, _HARD_MAX_CHUNK)
        if cut < 1:
            cut = _HARD_MAX_CHUNK
        out.append(buf[:cut].strip())
        buf = buf[cut:].strip()
    if buf:
        out.append(buf)
    return out


def split_for_tts(text: str | None) -> list[str]:
    """Разбить очищенный текст на фразы/предложения (граница — . ! ? … ; :).

    Каждый кусок синтезируется и проигрывается отдельно, поэтому озвучка
    стартует почти сразу (после первого предложения), а не после всей фразы.
    """
    if not text:
        return []
    s = str(text).strip()
    if not s:
        return []
    parts = [p.strip() for p in _SENTENCE_END.split(s) if p and p.strip()]
    if not parts:
        return _split_long_chunk(s)

    chunks: list[str] = []
    for p in parts:
        chunks.extend(_split_long_chunk(p))
    return [c for c in chunks if c]