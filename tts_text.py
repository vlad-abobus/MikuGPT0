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
# Хотя бы одна буква/цифра: строка из одних знаков препинания не озвучивается.
_SPEAKABLE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]")
# Пробел перед знаком препинания (после удаления символов) убираем.
_PRE_PUNCT_SPACE = re.compile(r"\s+([.,!?…;:])")
_SPACES = re.compile(r"\s+")

# Конец предложения: точка, восклицательный/вопросительный знак, многоточие, ; и :
_SENTENCE_END = re.compile(r"(?<=[.!?…;:])\s+")
# Жёсткий перенос длинных кусков не разрывая слова.
_HARD_MAX_CHUNK = 220

# Служебный JSON эмоции в конце ответа LLM — в озвучку и в стрим-вывод не попадает.
_JSON_EMOTION_START = re.compile(r'\{\s*"emotion"', re.IGNORECASE)
_JSON_EMOTION_TAIL = re.compile(r'\{\s*"emotion"[\s\S]*$', re.IGNORECASE)
_LEGACY_TAG_TAIL = re.compile(r"\{[A-Za-z0-9_]+\}\s*$")
_JSON_START_PROBE = '{"emotion"'


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
    cleaned = s.strip()
    # «»?» или остатки битой кодировки: букв/цифр нет — синтезировать нечего.
    return cleaned if _SPEAKABLE.search(cleaned) else ""


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


class StreamingSpeechBuffer:
    """Накопитель текста LLM-стрима, который отдаёт готовые фразы по мере ответа.

    Границы фраз — перевод строки, конец предложения или жёсткий предел длины.
    Служебный JSON эмоции в конце ответа придерживается и не попадает ни в
    озвучку, ни в синхронный вывод текста.

    ``feed`` вызывается по мере прихода токенов, ``finish`` — после окончания
    ответа; оба метода возвращают список готовых фраз.
    """

    def __init__(self, max_chunk: int = _HARD_MAX_CHUNK) -> None:
        self._buf = ""
        self._max = max(40, int(max_chunk))

    def feed(self, text: str | None) -> list[str]:
        """Добавить кусок ответа и вернуть фразы, которые уже можно озвучить."""
        if not text:
            return []
        self._buf += str(text)
        return self._drain()

    def finish(self) -> list[str]:
        """Завершить стрим: отдать оставшийся текст без служебного JSON."""
        out = self._drain()
        guard = self._service_tail_start()
        if guard >= 0:
            self._buf = self._buf[:guard]
        tail = _JSON_EMOTION_TAIL.sub("", self._buf)
        tail = _LEGACY_TAG_TAIL.sub("", tail).strip()
        self._buf = ""
        if not tail:
            return out
        out.extend(_split_long_chunk(tail))
        return [p for p in out if p.strip()]

    def _drain(self) -> list[str]:
        out: list[str] = []
        while True:
            limit = len(self._buf)
            guard = self._service_tail_start()
            if guard >= 0:
                limit = min(limit, guard)
            cut = self._find_cut(limit)
            if cut <= 0:
                break
            chunk = self._buf[:cut]
            self._buf = self._buf[cut:]
            if chunk.strip():
                out.append(chunk)
        return out

    def _service_tail_start(self) -> int:
        """Индекс начала возможного JSON/тега эмоции в хвосте буфера или -1."""
        m = _JSON_EMOTION_START.search(self._buf)
        if m:
            # ```json перед эмоцией тоже относится к служебному блоку.
            fence = re.search(r"```(?:json)?\s*$", self._buf[: m.start()], re.IGNORECASE)
            return fence.start() if fence else m.start()
        # Открывающий ```json пришёл раньше самого JSON — придерживаем его.
        fence = re.search(r"```(?:json)?\s*$", self._buf, re.IGNORECASE)
        if fence and fence.end() == len(self._buf):
            return fence.start()
        brace = self._buf.rfind("{")
        if brace < 0:
            return -1
        # Частично пришедший маркер '{"emo…' — придерживаем до следующего токена.
        tail = re.sub(r"\s+", "", self._buf[brace:]).lower()
        if tail and len(tail) <= len(_JSON_START_PROBE) and _JSON_START_PROBE.startswith(tail):
            fence = re.search(r"```(?:json)?\s*$", self._buf[:brace], re.IGNORECASE)
            return fence.start() if fence else brace
        return -1

    def _find_cut(self, limit: int) -> int:
        if limit <= 0:
            return 0
        newline = self._buf.find("\n", 0, limit)
        if newline >= 0:
            return newline + 1
        sentence = _SENTENCE_END.search(self._buf, 0, limit)
        if sentence:
            return sentence.end()
        if limit > self._max:
            cut = self._buf.rfind(" ", 0, self._max)
            if cut < 1:
                cut = self._max
            return cut
        return 0
