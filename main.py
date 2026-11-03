# -*- coding: utf-8 -*-
from __future__ import annotations
import locale
import os
import sys

# Windows-фикс: UTF-8 везде
if sys.platform == "win32":
    try:
        locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import logging
import random
import re
import threading

import customtkinter as ctk
import tkinter.messagebox as tkmsg
try:
    from panda_window import PandaWindowController
except Exception:
    PandaWindowController = None
from PIL import Image, ImageDraw, ImageFont
from customtkinter import CTkImage

from emotions_data import (
    default_greeting_emotion_key,
    emotion_ext_for_set,
    emotion_keys_for_set,
    emotion_labels_for_set,
    pick_emotion,
)
from ai_chat import (
    DEFAULT_TEMPERATURE,
    ChatProviderError,
    chat,
    chat_short,
    chat_stream,
    get_temperature,
)
from paths import read_config_json, resource_path, update_config_json
from localization import LANGUAGE_CODES, get_locales
from prompts import build_system_prompt
from tts_text import clean_text_for_tts
from voice_input import VoiceInput

logger = logging.getLogger(__name__)

# --- ВАШИ КЛАССИЧЕСКИЕ ЦВЕТА С СОВРЕМЕННЫМИ ФОРМАМИ ---
ctk.set_appearance_mode("dark")

APP_BG = "#333333"              # Главный фон (тот самый)
PANEL_BG = "#292929"            # Фон панелей (чуть темнее для контраста)
CARD_BG = "#3D3D3D"             # Фон карточек (светлее фона)
INPUT_BG = "#222222"            # Поле ввода (темное)

ACCENT_BLUE = "#1f6aa5"         # Тот самый синенький!
ACCENT_BLUE_HOVER = "#144870"   # Синенький при наведении
ACCENT_LIGHT = "#4AA3DF"        # Светло-синий для текста/акцентов Мику
ACCENT_PALE = "#B6DCFA"

TEXT_MAIN = "#F2F2F2"           # Мягкий белый текст
TEXT_MUTED = "#A0A0A0"          # Серый текст для подсказок
BORDER_COLOR = "#444444"        # Цвет рамок

VOICE_LANGUAGE_CODES = {
    "ru": "ru-RU",
    "kk": "kk-KZ",
    "uk": "uk-UA",
    "en": "en-US",
}

# Константы
IMAGE_SIZE = (340, 255)
LEFT_PANEL_WIDTH = 390
_EMOTION_CANVAS_BG = (41, 41, 41) # Соответствует PANEL_BG (#292929) в RGB
IMAGE_DIR = "emotions"
DEFAULT_FONT = ("Segoe UI", 14) if sys.platform == "win32" else ("Roboto", 14)
class ChatApp(ctk.CTk):
    def t(self, key: str, **values: object) -> str:
        translation = self.locales[self.response_language]["ui"].get(key)
        if not isinstance(translation, str):
            raise KeyError(f"Missing UI translation: {self.response_language}.{key}")
        return translation.format(**values) if values else translation

    def __init__(self):
        super().__init__()
        self.locales = get_locales()
        self.response_language = "ru"
        self.title(self.t("app_title"))
        self.geometry("1280x960")
        self.minsize(900, 600)
        self.configure(fg_color=APP_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

        # Переменные конфигурации
        self.flirt_enabled = ctk.BooleanVar(value=False)
        self.nsfw_enabled = ctk.BooleanVar(value=False)
        self.hooks_enabled = ctk.BooleanVar(value=True)
        self.typing_animation_enabled = ctk.BooleanVar(value=True)
        self.personality = "Дередере"
        self.current_view_mode = "view_2d"
        self.emotion_set = ctk.StringVar(value="C")  

        self.interactive = ctk.BooleanVar(value=False)
        self.auto_tts_enabled = ctk.BooleanVar(value=True)
        self.sync_tts_enabled = ctk.BooleanVar(value=True)

        try:
            self.placeholder_font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            self.placeholder_font = None

        self.emotion_images = {}

        self.user_name = ""
        self.user_pronouns = ""
        self.config_notes = ""
        self.user_interests = ""
        self.user_memory = ""
        self.smart_memory_enabled = ctk.BooleanVar(value=True)
        self.smart_memory_every_n = ctk.StringVar(value="6")
        self._smart_memory_counter = 0
        try:
            cfg = read_config_json()
            self.user_name = cfg.get("user_name", "") or ""
            self.user_pronouns = (cfg.get("user_pronouns") or "").strip()
            self.config_notes = (cfg.get("notes") or "").strip()
            self.user_interests = (cfg.get("user_interests") or "").strip()
            self.user_memory = (cfg.get("user_memory") or "").strip()
            stored_language = str(cfg.get("response_language", "ru")).strip().lower()
            self.response_language = stored_language if stored_language in LANGUAGE_CODES else "ru"
            sme = cfg.get("smart_memory_enabled", True)
            self.smart_memory_enabled.set(bool(sme) if sme is not None else True)
            smn = cfg.get("smart_memory_every_n", 6)
            try:
                smn_int = int(smn)
            except Exception:
                smn_int = 6
            smn_int = max(2, min(20, smn_int))
            self.smart_memory_every_n.set(str(smn_int))
            ta = cfg.get("typing_animation", True)
            self.typing_animation_enabled.set(bool(ta) if ta is not None else True)
            at = cfg.get("auto_tts_enabled", True)
            self.auto_tts_enabled.set(bool(at) if at is not None else True)
            st = cfg.get("sync_tts_enabled", True)
            self.sync_tts_enabled.set(bool(st) if st is not None else True)
            es = (cfg.get("emotion_set") or "C").strip().upper()
            self.emotion_set.set(es if es in ("A", "B", "C") else "C")
            try:
                temp = float(cfg.get("ai_temperature", DEFAULT_TEMPERATURE))
            except (TypeError, ValueError):
                temp = DEFAULT_TEMPERATURE
            self.ai_temperature = max(0.0, min(2.0, temp))
        except Exception:
            self.ai_temperature = DEFAULT_TEMPERATURE
        self.title(self.t("app_title"))

        try:
            if "chat_history" in read_config_json():
                update_config_json({"chat_history": []})
        except Exception:
            pass

        self._miku_type_gen = 0
        self._tts_seq = 0
        self._status_tags: set[str] = set()
        self._status_after_id = None
        self._panda_window = None
        self._panda_state = "idle"
        self._tts_in_progress = False

        # Синхронная озвучка: поколение ответа, карточка, которая заполняется
        # фразами ровно в момент старта их аудио, и активный SpeechStream.
        self._reply_gen = 0
        self._reply_gen_lock = threading.Lock()
        self._sync_gen = 0
        self._sync_card = None
        self._sync_label = None
        self._sync_text = ""
        self._sync_last_seq = 0
        self._pending_reply_text: dict[int, str] = {}
        self._active_speech = None

        self.load_emotion_images()
        self.chat_history = []

        self._build_ui()
        self.update()
        self._prompt_user_name_on_startup()
        
        try:
            from fish_tts import configuration_error, is_configured as fish_configured
            if not fish_configured():
                _fish_error = configuration_error()
                logger.warning("Fish Audio is not configured: %s", _fish_error)
                self.after(900, lambda: self._append("Система", self.t("fish_not_configured")))
        except Exception:
            pass

        try:
            from gemini_client import warmup as gemini_warmup
            threading.Thread(target=gemini_warmup, kwargs={"delay_sec": 3.0}, daemon=True).start()
        except Exception:
            pass

        try:
            from gemini_client import has_key as gemini_has_key
            if not gemini_has_key():
                self.after(700, lambda: self._append(
                    "Система",
                    self.t("gemini_missing"),
                ))
        except Exception:
            pass

        self.voice_input = VoiceInput()
        if not self.voice_input.available:
            logger.warning("Голосовой ввод недоступен: %s", self.voice_input.init_error)

        self.last_emotion_key = default_greeting_emotion_key(self.emotion_set.get())
        self._install_tts_playback_listener()

        try:
            self.after(800, self._start_panda_window)
        except Exception:
            pass

    # ---------- 3D-панда ----------
    def _start_panda_window(self):
        if PandaWindowController is None:
            return
        try:
            self.update_idletasks()
            ax, ay = self.winfo_rootx(), self.winfo_rooty()
            aw = self.winfo_width() or 1280
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            win_w, win_h = 300, 380
            x = ax + aw + 8
            if x + win_w > sw - 10:
                x = max(10, ax - win_w - 8)
            y = max(10, ay + 40)
            if y + win_h > sh - 40:
                y = max(10, sh - win_h - 40)
            self._panda_window = PandaWindowController()
            self._panda_window.start(resource_path("view3d.html"), x, y, win_w, win_h)
            if self.view_mode_var.get() == self.t("view_3d"):
                self._panda_window.send("show")
        except Exception:
            logger.debug("Не удалось запустить окно панды", exc_info=True)

    def _on_app_close(self):
        try:
            self._cancel_active_speech()
        except Exception:
            pass
        try:
            if getattr(self, "_panda_window", None) is not None:
                self._panda_window.stop()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    # ---------- Логика текста и эмоций ----------
    def _resource_path(self, relative_path: str) -> str:
        return resource_path(relative_path)

    @staticmethod
    def _chat_text(value: str | None) -> str:
        return (value or "").strip()

    def _ensure_miku_reply(self, text: str | None) -> str:
        cleaned = self._chat_text(text)
        return cleaned if cleaned else self.t("empty_reply")

    def _normalize_emotion_key(self, key: str | None) -> str | None:
        if key is None:
            return None
        if not isinstance(key, str):
            return None
        k = key.strip().strip('"').strip("'")
        return k if k else None

    def _emotion_key_from_json_blob(self, blob: str) -> str | None:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            m = re.search(r'"emotion"\s*:\s*"([^"]+)"', blob)
            return self._normalize_emotion_key(m.group(1)) if m else None
        if not isinstance(data, dict):
            return None
        return self._normalize_emotion_key(data.get("emotion"))

    def _strip_emotion_tag(self, text: str) -> tuple[str, str | None]:
        if not text:
            return "", None
        s = text.strip()
        key, pos = self._find_trailing_json_emotion(s)
        if key is not None and pos >= 0:
            return self._chat_text(s[:pos].strip()), key
        m = re.search(r'\{\s*"emotion"\s*:\s*"([^"]+)"\s*\}\s*$', s, re.DOTALL)
        if m:
            key = self._normalize_emotion_key(m.group(1))
            if key:
                return self._chat_text(s[: m.start()].strip()), key
        m = re.search(r"\{([A-Za-z0-9_]+)\}\s*$", s)
        if m:
            key = self._normalize_emotion_key(m.group(1))
            if key:
                return self._chat_text(s[: m.start()].strip()), key
        return self._strip_emotion_json_legacy(s)

    def _find_trailing_json_emotion(self, s: str) -> tuple[str | None, int]:
        last_brace = s.rfind('{"emotion"')
        if last_brace < 0:
            return None, -1
        tail = s[last_brace:]
        m = re.match(r'\{\s*"emotion"\s*:\s*"([^"]+)"\s*\}', tail)
        if m:
            return self._normalize_emotion_key(m.group(1)), last_brace
        return None, -1

    def _strip_emotion_json_legacy(self, s: str) -> tuple[str, str | None]:
        for pat in (
            r"```json\s*(\{[\s\S]*?\})\s*```\s*$",
            r"```\s*(\{[\s\S]*?\})\s*```\s*$",
        ):
            m = re.search(pat, s, re.IGNORECASE | re.DOTALL)
            if m:
                key = self._emotion_key_from_json_blob(m.group(1))
                if key:
                    return self._chat_text(s[: m.start()]), key

        m = re.search(r'(\{\s*"emotion"\s*:\s*"[^"]+"\s*\})\s*$', s, re.DOTALL)
        if m:
            key = self._emotion_key_from_json_blob(m.group(1))
            if key:
                return self._chat_text(s[: m.start()]), key

        last_match = None
        for m in re.finditer(r'\{\s*"emotion"\s*:\s*"([^"]+)"', s):
            last_match = m
        if last_match and len(s) - last_match.end() < 100:
            brace = s.rfind("{", 0, last_match.start())
            if brace >= 0 and len(s) - brace < 160:
                tail = s[brace:]
                if re.match(r'\{\s*"emotion"', tail):
                    key = self._normalize_emotion_key(last_match.group(1))
                    if key:
                        return self._chat_text(s[:brace]), key

        m = re.search(r'"emotion"\s*:\s*"([^"]+)"', s)
        if m:
            key = self._normalize_emotion_key(m.group(1))
            if key:
                cleaned = re.sub(r'\{[^{}]*"emotion"[^{}]*\}', "", s, flags=re.DOTALL)
                cleaned = re.sub(r"```json\s*```", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"```\s*```", "", cleaned)
                return self._chat_text(cleaned), key
        return self._chat_text(s), None

    def _parse_ai_response(
        self, text: str | None
    ) -> tuple[str, str | None, str | None]:
        if text is None:
            return "", default_greeting_emotion_key(self.emotion_set.get()), None

        clean_text, raw_emotion = self._strip_emotion_tag(text)
        emotion = self._resolve_emotion_key(raw_emotion)
        action_match = re.search(r'"stage_action"\s*:\s*"([^"]+)"', text)
        stage_action = action_match.group(1) if action_match else None
        return clean_text, emotion, stage_action

    def _is_valid_emotion_key(self, key: str | None) -> bool:
        return bool(key and key in emotion_keys_for_set(self.emotion_set.get()))

    def _resolve_emotion_key(self, raw_key: str | None) -> str:
        key = self._normalize_emotion_key(raw_key)
        current_set = self.emotion_set.get()
        if key and self._is_valid_emotion_key(key):
            return key
        return default_greeting_emotion_key(current_set)

    def _ensure_different_emotion(self, raw_key: str | None) -> str | None:
        key = self._resolve_emotion_key(raw_key)
        if key is None:
            return None
        if key == self.last_emotion_key:
            current_set = self.emotion_set.get()
            keys = emotion_keys_for_set(current_set)
            others = [k for k in keys if k != key]
            if others:
                chosen = random.choice(others)
                return chosen
        return key

    _REFUSAL_PHRASES = (
        "я не могу продолжить", "я не могу выполнить", "я не могу генерировать",
        "i cannot fulfill", "i cannot continue", "i cannot generate",
        "я не могу предоставить", "я не могу ответить",
        "извини", "извините", "как ии, я не могу",
        "я не могу участвовать", "я ассистент и не могу",
        "i apologize", "i cannot", "i'm sorry", "я ассистент",
    )

    def _is_refusal(self, text: str) -> bool:
        low = text.lower().strip()
        if not low or len(low) < 20:
            return True
        for phrase in self._REFUSAL_PHRASES:
            if phrase in low:
                return True
        return False

    def _fetch_miku_reply(self, api_messages: list[dict]) -> tuple[str, str]:
        nsfw_on = self.nsfw_enabled.get()
        raw = chat(api_messages, nsfw=nsfw_on)
        attempt = 0
        softeners = [
            self.t("retry_softener_1"),
            self.t("retry_softener_2"),
            self.t("retry_softener_3"),
        ]
        max_attempts = len(softeners) if nsfw_on else 0
        while self._is_refusal(raw) and attempt < max_attempts:
            attempt += 1
            soft_msg = {"role": "system", "content": softeners[attempt - 1]}
            retry_messages = api_messages + [soft_msg]
            raw = chat(retry_messages, nsfw=nsfw_on)
        return self._finalize_ai_reply(raw)

    def _prompt_user_name_on_startup(self):
        default = (self.user_name or "").strip()
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.t("startup_title"))
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(fg_color=PANEL_BG)
        try:
            dialog.attributes("-topmost", True)
        except Exception:
            pass
        dialog.lift(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=self.t("startup_question"),
            font=(DEFAULT_FONT[0], DEFAULT_FONT[1] + 4, "bold"),
            text_color=TEXT_MAIN
        ).pack(pady=(26, 12), padx=24)

        name_var = ctk.StringVar(value=default)
        entry = ctk.CTkEntry(
            dialog, textvariable=name_var, width=320, 
            placeholder_text=self.t("name_placeholder"),
            fg_color=INPUT_BG, border_color=ACCENT_BLUE, border_width=1, corner_radius=12
        )
        entry.pack(padx=24, pady=(0, 8))
        entry.focus_set()
        entry.select_range(0, "end")

        hint = ctk.CTkLabel(dialog, text="", text_color=TEXT_MUTED, font=(DEFAULT_FONT[0], 12))
        hint.pack(padx=24, pady=(0, 4))

        result: dict[str, str | None] = {"name": None}

        def apply_name() -> None:
            name = (name_var.get() or "").strip()
            if not name:
                hint.configure(text=self.t("name_required"))
                return
            result["name"] = name
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()
            try:
                self.lift()
                self.focus_force()
            except Exception:
                pass

        entry.bind("<Return>", lambda _e: apply_name())
        ctk.CTkButton(
            dialog, text=self.t("continue"), width=200, corner_radius=12,
            command=apply_name, fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER, text_color="#FFFFFF"
        ).pack(pady=(8, 26))

        dialog.update_idletasks()
        w, h = 420, 220
        x = self.winfo_x() + max(0, (self.winfo_width() - w) // 2)
        y = self.winfo_y() + max(0, (self.winfo_height() - h) // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.protocol("WM_DELETE_WINDOW", apply_name)
        self.wait_window(dialog)

        name = (result.get("name") or "").strip()
        if not name:
            name = default or "Вы"
        self.user_name = name
        if hasattr(self, "user_name_var"):
            self.user_name_var.set(name)
        try:
            update_config_json({"user_name": name})
        except Exception:
            pass

    # ---------- UI BUILDER ----------
    def _build_ui(self):
        self._ui_root = ctk.CTkFrame(self, fg_color="transparent")
        self._ui_root.pack(fill="both", expand=True)
        self._ui_root.grid_columnconfigure(0, weight=1)
        self._ui_root.grid_rowconfigure(1, weight=1)

        # Верхняя навигация
        navigation = ctk.CTkFrame(self._ui_root, fg_color="transparent")
        navigation.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 4))
        navigation.grid_columnconfigure(0, weight=1)
        self.page_selector = ctk.CTkSegmentedButton(
            navigation,
            values=[
                self.t("page_chat"),
                self.t("page_settings"),
                self.t("page_about"),
            ],
            selected_color=ACCENT_BLUE,
            selected_hover_color=ACCENT_BLUE_HOVER,
            unselected_color=PANEL_BG,
            unselected_hover_color=CARD_BG,
            text_color="#FFFFFF",
            corner_radius=16,
            command=self._switch_page,
            font=(DEFAULT_FONT[0], 13, "bold")
        )
        self.page_selector.set(self.t("page_chat"))
        self.page_selector.grid(row=0, column=0)

        # Контейнер для страниц
        pages = ctk.CTkFrame(self._ui_root, fg_color="transparent")
        pages.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        pages.grid_rowconfigure(0, weight=1)
        pages.grid_columnconfigure(0, weight=1)

        self.chat_tab = ctk.CTkFrame(pages, fg_color="transparent")
        self.chat_tab.grid(row=0, column=0, sticky="nsew")
        self._build_chat_ui()

        self.settings_tab = ctk.CTkFrame(pages, fg_color="transparent")
        self.settings_tab.grid(row=0, column=0, sticky="nsew")
        self.settings_tab.grid_remove()
        self._build_settings_tab()

        self.about_tab = ctk.CTkFrame(pages, fg_color="transparent")
        self.about_tab.grid(row=0, column=0, sticky="nsew")
        self.about_tab.grid_remove()
        self._build_about_tab()

    def _switch_page(self, page: str):
        pages = {
            self.t("page_chat"): self.chat_tab,
            self.t("page_settings"): self.settings_tab,
            self.t("page_about"): self.about_tab,
        }
        selected = pages.get(page)
        if selected is None:
            return
        for frame in pages.values():
            frame.grid_remove()
        selected.grid()

    def _rebuild_ui_for_language(
        self, page_key: str = "page_chat", settings_tab_key: str | None = None
    ) -> None:
        history = list(self.chat_history)
        self._ui_root.destroy()
        self.title(self.t("app_title"))
        self._build_ui()
        if settings_tab_key is not None:
            self.settings_tabview.set(self.t(settings_tab_key))
        self.page_selector.set(self.t(page_key))
        self._switch_page(self.t(page_key))
        for message in history:
            if message["role"] == "user":
                sender = self.user_name or "Вы"
            else:
                sender = "Мику"
            self._append(sender, message["content"])

    def _build_chat_ui(self):
        self.chat_tab.grid_columnconfigure(0, weight=0, minsize=LEFT_PANEL_WIDTH)
        self.chat_tab.grid_columnconfigure(1, weight=1)
        self.chat_tab.grid_rowconfigure(0, weight=1)

        # Левая панель (Мягкий фон, скругление)
        left_frame = ctk.CTkFrame(self.chat_tab, width=LEFT_PANEL_WIDTH, corner_radius=18, fg_color=PANEL_BG)
        left_frame.grid(row=0, column=0, sticky="ns", padx=(0, 16), pady=0)
        left_frame.grid_propagate(False)
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(3, weight=1)

        self.view_mode_var = ctk.StringVar(value=self.t(self.current_view_mode))
        self.view_mode_selector = ctk.CTkSegmentedButton(
            left_frame,
            values=[self.t("view_2d"), self.t("view_3d")],
            variable=self.view_mode_var,
            selected_color=ACCENT_BLUE,
            selected_hover_color=ACCENT_BLUE_HOVER,
            unselected_color=CARD_BG,
            unselected_hover_color=APP_BG,
            text_color=TEXT_MAIN,
            corner_radius=12,
            command=self._set_view_mode,
        )
        self.view_mode_selector.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 16))

        current_set = self.emotion_set.get()
        start_key = default_greeting_emotion_key(current_set)
        start_img = self.emotion_images.get(start_key)

        # Карточка с артом 
        self.art_card = ctk.CTkFrame(left_frame, corner_radius=16, fg_color=CARD_BG)
        self.art_card.grid(row=1, column=0, sticky="n", padx=20, pady=(0, 16))
        
        self.char_label = ctk.CTkLabel(self.art_card, image=start_img, text="", corner_radius=12)
        self.char_label._current_image = start_img
        self.char_label.pack(padx=8, pady=8)
        
        self.character_status = ctk.CTkLabel(
            self.art_card,
            text=self.t("ready"),
            fg_color="#222222",
            text_color="#2ECC71",
            corner_radius=10,
            font=(DEFAULT_FONT[0], 12, "bold"),
            padx=10, pady=2
        )
        self.character_status.place(x=16, y=16)

        self.panda_panel = ctk.CTkFrame(
            left_frame, width=350, height=263, corner_radius=16, fg_color=CARD_BG
        )
        self.panda_panel.grid(row=1, column=0, sticky="n", padx=20, pady=(0, 16))
        self.panda_panel.grid_propagate(False)
        ctk.CTkLabel(
            self.panda_panel,
            text=self.t("panda_panel"),
            justify="center", text_color=TEXT_MUTED, font=DEFAULT_FONT
        ).place(relx=0.5, rely=0.5, anchor="center")
        self.panda_panel.grid_remove()

        controls = ctk.CTkFrame(left_frame, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="new", padx=24, pady=(0, 16))
        controls.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            controls, text=self.t("personality_label"), anchor="w", text_color=TEXT_MUTED,
            font=(DEFAULT_FONT[0], 13, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        
        personality_labels = self.locales[self.response_language]["personalities"]
        self._personality_key_by_label = {
            label: personality for personality, label in personality_labels.items()
        }
        self.personality_var = ctk.StringVar(value=personality_labels[self.personality])
        personality_menu = ctk.CTkOptionMenu(
            controls,
            values=list(personality_labels.values()),
            variable=self.personality_var,
            command=self._update_personality,
            fg_color=CARD_BG, button_color=CARD_BG, button_hover_color=APP_BG,
            text_color=TEXT_MAIN, corner_radius=10
        )
        personality_menu.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        cb_kwargs = {"checkbox_width": 20, "checkbox_height": 20, "border_width": 2, 
                     "fg_color": ACCENT_BLUE, "hover_color": ACCENT_BLUE_HOVER, 
                     "border_color": BORDER_COLOR, "text_color": TEXT_MAIN}

        self._flirt_cb = ctk.CTkCheckBox(controls, text=self.t("romance"), variable=self.flirt_enabled, **cb_kwargs)
        self._flirt_cb.grid(row=2, column=0, sticky="w", pady=6)
        
        self._nsfw_cb = ctk.CTkCheckBox(controls, text=self.t("nsfw"), variable=self.nsfw_enabled, **cb_kwargs)
        self._nsfw_cb.grid(row=3, column=0, sticky="w", pady=6)
        
        self._roleplay_cb = ctk.CTkCheckBox(controls, text=self.t("roleplay"), variable=self.interactive, **cb_kwargs)
        self._roleplay_cb.grid(row=4, column=0, sticky="w", pady=6)

        # Правая панель (Чат)
        right_frame = ctk.CTkFrame(self.chat_tab, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", pady=0)
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(0, weight=1)

        # История чата
        self.chat_history_frame = ctk.CTkScrollableFrame(
            right_frame, fg_color=PANEL_BG, corner_radius=18, scrollbar_button_color=CARD_BG
        )
        self.chat_history_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
        self.chat_history_frame.grid_columnconfigure(0, weight=1)
        self._message_labels = []
        self._message_card_count = 0
        self.chat_history_frame.bind("<Configure>", self._resize_message_wraps)
        self.chat_history_frame.bind("<MouseWheel>", self._on_chat_mouse_wheel)
        self.chat_history_frame.bind("<Shift-MouseWheel>", self._on_chat_mouse_wheel)
        self.chat_history_frame.bind("<Button-4>", self._on_chat_mouse_wheel)
        self.chat_history_frame.bind("<Button-5>", self._on_chat_mouse_wheel)
        self._bind_chat_wheel_target(self.chat_history_frame)

        # Статус бар
        self._chat_status_strip = ctk.CTkFrame(
            right_frame, height=32, fg_color=INPUT_BG, corner_radius=16
        )
        self._chat_status_strip.grid(row=1, column=0, sticky="ew", padx=0, pady=(0, 10))
        self._chat_status_strip.pack_propagate(False)
        self._chat_status_label = ctk.CTkLabel(
            self._chat_status_strip, text="", font=(DEFAULT_FONT[0], 12), text_color=TEXT_MUTED,
        )
        self._chat_status_label.pack(expand=True, fill="both", padx=14)

        # Поле ввода
        input_frame = ctk.CTkFrame(right_frame, corner_radius=0, fg_color="transparent")
        input_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_frame, placeholder_text=self.t("input_placeholder"),
            height=48, corner_radius=24, border_width=1, border_color=BORDER_COLOR,
            fg_color=INPUT_BG, font=DEFAULT_FONT, text_color=TEXT_MAIN, placeholder_text_color=TEXT_MUTED
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry.bind("<Return>", self._on_enter)

        self.mic_btn = ctk.CTkButton(
            input_frame, text="🎤", width=48, height=48, corner_radius=24,
            command=self._toggle_voice_input, fg_color=CARD_BG, hover_color=BORDER_COLOR, text_color=TEXT_MAIN
        )
        self.mic_btn.grid(row=0, column=1, padx=(0, 10))

        self.send_btn = ctk.CTkButton(
            input_frame, text="➤", width=48, height=48, corner_radius=24,
            command=self.send_message, fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER,
            text_color="#FFFFFF", font=(DEFAULT_FONT[0], 18, "bold"),
        )
        self.send_btn.grid(row=0, column=2)
        self._set_view_mode(self.view_mode_var.get())

    def _create_message_card(self, sender: str, message: str):
        _card, body_label = self._create_message_card_ex(sender, message)
        return body_label

    def _create_message_card_ex(self, sender: str, message: str, *, show_speaker: bool = True):
        """Создать карточку сообщения и вернуть ``(card, body_label)``."""
        is_miku = sender == "Мику"
        is_sys = sender == "Система"
        sender_labels = {
            "Мику": self.t("speaker_miku"),
            "Система": self.t("speaker_system"),
            "Вы": self.t("speaker_you"),
        }
        display_sender = sender_labels.get(sender, sender)
        
        # Мику имеет чуть синеватый оттенок на карточке, остальные - стандартные
        bg_color = "#2B333B" if is_miku else (CARD_BG if not is_sys else APP_BG)
        accent = ACCENT_LIGHT if is_miku else ("#8FC8FF" if not is_sys else "#A0A0A0")
        
        card = ctk.CTkFrame(
            self.chat_history_frame, fg_color=bg_color, corner_radius=16,
        )
        card.grid(row=self._message_card_count, column=0, sticky="ew", padx=16, pady=8)
        self._message_card_count += 1
        card.grid_columnconfigure(1, weight=1)
        
        ctk.CTkFrame(card, width=6, height=6, fg_color=accent, corner_radius=3).grid(
            row=0, column=0, rowspan=2, sticky="nw", padx=(16, 12), pady=18
        )
        
        ctk.CTkLabel(
            card, text=display_sender, text_color=accent, font=(DEFAULT_FONT[0], 13, "bold"), anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 0))
        
        body_label = ctk.CTkLabel(
            card, text=message, text_color=TEXT_MAIN, font=DEFAULT_FONT,
            anchor="w", justify="left", wraplength=620,
        )
        body_label.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(2, 16))
        self._message_labels.append(body_label)

        if is_miku and show_speaker:
            self._add_speaker_button(card, self._text_for_tts(message))
            
        self._scroll_chat_end()
        return card, body_label

    def _add_speaker_button(self, card, speech: str) -> None:
        """Добавить кнопку 🔊, читающую переданный текст."""
        if not (speech or "").strip():
            return
        speaker = ctk.CTkButton(
            card, text="🔊", width=36, height=36, corner_radius=10,
            fg_color="transparent", hover_color="#3A4A5A", text_color=TEXT_MUTED,
            command=lambda payload=speech, lang=self.response_language: self._request_tts(
                payload, lang
            ),
        )
        speaker.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(0, 8), pady=8)

    def _build_settings_tab(self):
        inner = ctk.CTkTabview(
            self.settings_tab, fg_color=PANEL_BG,
            segmented_button_fg_color=INPUT_BG, segmented_button_selected_color=CARD_BG,
            segmented_button_selected_hover_color=CARD_BG, segmented_button_unselected_color=INPUT_BG,
            text_color=TEXT_MAIN, corner_radius=16
        )
        self.settings_tabview = inner
        inner.pack(fill="both", expand=True, padx=20, pady=0)

        tab_prof = inner.add(self.t("tab_profile"))
        tab_ai = inner.add(self.t("tab_ai"))
        tab_mem = inner.add(self.t("tab_memory"))
        tab_chat = inner.add(self.t("tab_chat"))
        for tab in (tab_prof, tab_ai, tab_mem, tab_chat):
            tab.configure(fg_color=PANEL_BG)

        # —— Профиль ——
        prof = self._settings_pad(tab_prof)
        self._settings_label(prof, self.t("profile_address"))
        self.user_name_var = ctk.StringVar(value=getattr(self, "user_name", "") or "")
        ctk.CTkEntry(prof, textvariable=self.user_name_var, placeholder_text=self.t("your_name"), **self._entry_kwargs()).pack(fill="x", pady=(0, 12))
        self.user_pronouns_var = ctk.StringVar(value=getattr(self, "user_pronouns", "") or "")
        ctk.CTkEntry(prof, textvariable=self.user_pronouns_var, placeholder_text=self.t("pronouns"), **self._entry_kwargs()).pack(fill="x", pady=(0, 16))
        self._save_btn(prof, self.t("save_profile"), self._save_user_profile)

        # —— ИИ ——
        ai = self._settings_pad(tab_ai)
        self._settings_label(ai, self.t("language_label"))
        self._language_labels = {
            code: self.locales[code]["name"] for code in LANGUAGE_CODES
        }
        self._language_code_by_label = {
            label: code for code, label in self._language_labels.items()
        }
        self.response_language_var = ctk.StringVar(
            value=self._language_labels[self.response_language]
        )
        ctk.CTkOptionMenu(
            ai,
            values=list(self._language_code_by_label),
            variable=self.response_language_var,
            command=self._save_response_language,
            width=190,
            **self._menu_kwargs(),
        ).pack(anchor="w", pady=(0, 16))

        self._settings_label(ai, self.t("temperature"))
        temp_row = ctk.CTkFrame(ai, fg_color="transparent")
        temp_row.pack(fill="x", pady=(0, 8))
        self.ai_temperature_var = ctk.DoubleVar(value=getattr(self, "ai_temperature", DEFAULT_TEMPERATURE))
        self.ai_temp_value_label = ctk.CTkLabel(temp_row, text=f"{self.ai_temperature_var.get():.2f}", width=40, font=DEFAULT_FONT)

        self.ai_temp_slider = ctk.CTkSlider(
            temp_row, from_=0.0, to=2.0, number_of_steps=40, variable=self.ai_temperature_var,
            command=lambda v: self.ai_temp_value_label.configure(text=f"{float(v):.2f}"),
            progress_color=ACCENT_BLUE, button_color=ACCENT_BLUE, button_hover_color=ACCENT_BLUE_HOVER,
        )
        self.ai_temp_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.ai_temp_value_label.pack(side="right")
        self._settings_label(ai, self.t("temperature_hint"), hint=True)
        self._save_btn(ai, self.t("save_temperature"), self._save_ai_temperature)

        # —— Память ——
        mem = self._settings_pad(tab_mem)
        self._settings_label(mem, self.t("interests"))
        self.user_interests_box = ctk.CTkTextbox(mem, height=70, font=DEFAULT_FONT, wrap="word", **self._entry_kwargs())
        self.user_interests_box.pack(fill="x", pady=(0, 12))
        if self.user_interests: self.user_interests_box.insert("1.0", self.user_interests)

        self._settings_label(mem, self.t("user_facts"))
        self.user_memory_box = ctk.CTkTextbox(mem, height=70, font=DEFAULT_FONT, wrap="word", **self._entry_kwargs())
        self.user_memory_box.pack(fill="x", pady=(0, 16))
        if self.user_memory: self.user_memory_box.insert("1.0", self.user_memory)

        ctk.CTkCheckBox(mem, text=self.t("smart_memory"), variable=self.smart_memory_enabled, **self._cb_kwargs()).pack(anchor="w", pady=(0, 10))
        self._save_btn(mem, self.t("save_memory"), self._save_memory_tab)

        # —— Чат ——
        chat = self._settings_pad(tab_chat)
        emo_row = ctk.CTkFrame(chat, fg_color="transparent")
        emo_row.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(emo_row, text=self.t("emotion_set"), width=120, anchor="w", font=DEFAULT_FONT).pack(side="left")
        ctk.CTkOptionMenu(
            emo_row, values=["A", "B", "C"], variable=self.emotion_set, command=self._change_emotion_set,
            width=80, **self._menu_kwargs()
        ).pack(side="left")

        ctk.CTkCheckBox(chat, text=self.t("typing_animation"), variable=self.typing_animation_enabled, **self._cb_kwargs()).pack(anchor="w", pady=(0, 10))
        
        self._settings_label(chat, self.t("tts_heading"))
        ctk.CTkLabel(
            chat, text=self.t("tts_voice"), anchor="w",
            font=DEFAULT_FONT, text_color=TEXT_MAIN,
        ).pack(fill="x", pady=(0, 4))
        self._settings_label(
            chat, self.t("tts_keys_hint"),
            hint=True,
        )
        ctk.CTkCheckBox(
            chat, text=self.t("auto_tts"),
            variable=self.auto_tts_enabled, **self._cb_kwargs()
        ).pack(anchor="w", pady=(0, 10))
        ctk.CTkCheckBox(
            chat, text=self.t("sync_tts"),
            variable=self.sync_tts_enabled, **self._cb_kwargs()
        ).pack(anchor="w", pady=(0, 10))
        self._save_btn(chat, self.t("save_tts"), self._save_tts_settings)

    def _build_about_tab(self):
        self.about_tab.grid_columnconfigure(0, weight=1)
        self.about_tab.grid_rowconfigure(0, weight=1)

        content = ctk.CTkFrame(self.about_tab, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content.grid_columnconfigure((0, 1), weight=1, uniform="about_cards")
        
        title = ctk.CTkLabel(content, text=self.t("about_title"), font=(DEFAULT_FONT[0], 28, "bold"), text_color=ACCENT_LIGHT)
        title.grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 24))

        info_card = ctk.CTkFrame(content, fg_color=PANEL_BG, corner_radius=16)
        info_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(info_card, text="MikuGPT ♪", font=(DEFAULT_FONT[0], 22, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=24, pady=(24, 16))
        self._about_detail(info_card, self.t("version"), "1.5")
        self._about_detail(info_card, self.t("ai_engine"), "Google Gemini 3.5 Flash-Lite")
        self._about_detail(info_card, self.t("languages"), self.t("about_languages"))
        self._about_detail(info_card, self.t("telegram"), "@dev_miku")

        help_card = ctk.CTkFrame(content, fg_color=PANEL_BG, corner_radius=16)
        help_card.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(help_card, text=self.t("controls"), font=(DEFAULT_FONT[0], 22, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=24, pady=(24, 16))
        self._about_detail(help_card, "Enter", self.t("send"))
        self._about_detail(help_card, "🎤", self.t("voice_input"))

    def _settings_pad(self, parent, **kwargs) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=16)
        box.pack(fill="both", expand=True, padx=10, pady=10, **kwargs)
        return box

    def _settings_label(self, parent, text: str, *, hint: bool = False) -> None:
        ctk.CTkLabel(
            parent, text=text, font=(DEFAULT_FONT[0], 12 if hint else 14, "normal" if hint else "bold"),
            text_color=TEXT_MUTED if hint else TEXT_MAIN, anchor="w",
        ).pack(anchor="w", pady=(0, 6), padx=4)

    def _entry_kwargs(self):
        return {"fg_color": INPUT_BG, "border_color": BORDER_COLOR, "border_width": 1, "corner_radius": 10, "text_color": TEXT_MAIN}
        
    def _cb_kwargs(self):
        return {"fg_color": ACCENT_BLUE, "hover_color": ACCENT_BLUE_HOVER, "border_color": BORDER_COLOR, "text_color": TEXT_MAIN, "corner_radius": 6}
        
    def _menu_kwargs(self):
        return {"fg_color": INPUT_BG, "button_color": INPUT_BG, "button_hover_color": CARD_BG, "text_color": TEXT_MAIN, "corner_radius": 10}

    def _save_btn(self, parent, text, command):
        ctk.CTkButton(
            parent, text=text, width=180, command=command, 
            fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOVER, 
            text_color="#FFFFFF", corner_radius=10, font=(DEFAULT_FONT[0], 13, "bold")
        ).pack(anchor="w", pady=(10, 0))

    @staticmethod
    def _about_detail(parent, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 12))
        ctk.CTkLabel(row, text=label, width=90, anchor="w", text_color=TEXT_MUTED, font=(DEFAULT_FONT[0], 14, "bold")).pack(side="left")
        ctk.CTkLabel(row, text=value, anchor="w", justify="left", text_color=TEXT_MAIN, font=DEFAULT_FONT).pack(side="left", fill="x", expand=True)

    def _set_view_mode(self, mode: str):
        show_3d = mode == self.t("view_3d")
        self.current_view_mode = "view_3d" if show_3d else "view_2d"
        if show_3d:
            self.art_card.grid_remove()
            self.panda_panel.grid()
            if self._panda_window is not None:
                self._panda_window.send("show")
        else:
            self.panda_panel.grid_remove()
            self.art_card.grid()
            if self._panda_window is not None:
                self._panda_window.send("hide")

    def _save_memory_tab(self) -> None:
        self._save_user_interests()
        self._save_user_memory()
        self._save_smart_memory_settings()

    def _save_user_profile(self):
        new_name = (self.user_name_var.get() or "").strip()
        new_pro = (self.user_pronouns_var.get() or "").strip()
        try:
            update_config_json({
                "user_name": new_name,
                "user_pronouns": new_pro,
                "typing_animation": bool(self.typing_animation_enabled.get()),
            })
            self.user_name = new_name
            self.user_pronouns = new_pro
            self._append("Система", self.t("profile_saved"))
        except Exception as e:
            logger.exception("Ошибка сохранения профиля: %s", e)

    def _save_user_interests(self):
        try:
            raw = self.user_interests_box.get("1.0", "end-1c")
            new_interests = (raw or "").strip()
            update_config_json({"user_interests": new_interests})
            self.user_interests = new_interests
            self._append("Система", self.t("interests_saved"))
        except Exception as e:
            logger.exception("Ошибка сохранения интересов: %s", e)

    def _save_user_memory(self):
        try:
            raw = self.user_memory_box.get("1.0", "end-1c")
            new_memory = (raw or "").strip()
            update_config_json({"user_memory": new_memory})
            self.user_memory = new_memory
            self._append("Система", self.t("memory_saved"))
        except Exception as e:
            logger.exception("Ошибка сохранения памяти: %s", e)

    def _save_smart_memory_settings(self):
        enabled = bool(self.smart_memory_enabled.get())
        try:
            update_config_json({"smart_memory_enabled": enabled})
            state = self.t("enabled" if enabled else "disabled")
            self._append("Система", self.t("smart_memory_saved", state=state))
        except Exception as e:
            logger.exception("Ошибка сохранения настроек: %s", e)

    def _save_ai_temperature(self):
        try:
            t = float(self.ai_temperature_var.get())
            t = max(0.0, min(2.0, t))
            self.ai_temperature_var.set(t)
            self.ai_temperature = t
            update_config_json({"ai_temperature": round(t, 2)})
            self._append("Система", self.t("temperature_saved", value=t))
        except Exception:
            pass

    def _save_response_language(self, choice: str) -> None:
        language_code = self._language_code_by_label.get(choice)
        if language_code is None:
            logger.warning("Выбран неизвестный язык интерфейса: %r", choice)
            self.response_language_var.set(self._language_labels[self.response_language])
            return

        selected_page = self.page_selector.get()
        page_key = next(
            (
                key for key in ("page_chat", "page_settings", "page_about")
                if self.t(key) == selected_page
            ),
            "page_chat",
        )
        settings_tab_key = None
        if page_key == "page_settings":
            selected_tab = self.settings_tabview.get()
            settings_tab_key = next(
                (
                    key for key in ("tab_profile", "tab_ai", "tab_memory", "tab_chat")
                    if self.t(key) == selected_tab
                ),
                None,
            )
        try:
            update_config_json({"response_language": language_code})
        except Exception as exc:
            logger.exception("Failed to save interface language: %s", exc)
            self.response_language_var.set(self._language_labels[self.response_language])
            self._append("Система", self.t("language_save_failed"))
            return

        self.response_language = language_code
        self._rebuild_ui_for_language(page_key, settings_tab_key)
        self._append(
            "Система",
            self.t("language_saved", language=self.locales[language_code]["name"]),
        )

    def _save_tts_settings(self):
        try:
            update_config_json({
                "auto_tts_enabled": bool(self.auto_tts_enabled.get()),
                "sync_tts_enabled": bool(self.sync_tts_enabled.get()),
            })
            self._append("Система", self.t("tts_saved"))
        except Exception as exc:
            logger.exception("Failed to save TTS settings")
            self._append("Система", self.t("tts_save_failed", error=exc))

    def _change_emotion_set(self, new_set: str):
        self.emotion_set.set(new_set)
        self.load_emotion_images()
        self._set_emotion(default_greeting_emotion_key(new_set))
        try:
            update_config_json({"emotion_set": new_set})
        except Exception:
            pass

    def _update_personality(self, choice: str):
        personality = self._personality_key_by_label.get(choice)
        if personality is None:
            logger.warning("Выбран неизвестный характер: %r", choice)
            self.personality_var.set(
                self.locales[self.response_language]["personalities"][self.personality]
            )
            return
        if personality == "Яндере":
            self.flirt_enabled.set(True)
        elif personality == "Агресивный":
            self.nsfw_enabled.set(True)
        self.personality = personality
        self._append(
            "Система",
            self.t(
                "personality_changed",
                personality=self.locales[self.response_language]["personalities"][personality],
            ),
        )

    def _on_enter(self, event):
        self.send_message()
        return "break"

    def send_message(self):
        user_txt = self._chat_text(self.entry.get())
        if not user_txt:
            return
        self._cancel_active_speech()
        self._append(self.user_name or "Вы", user_txt)
        self.entry.delete(0, "end")
        self.chat_history.append({"role": "user", "content": user_txt})
        threading.Thread(target=self._fetch_response, args=(user_txt,), daemon=True).start()

    def _next_reply_gen(self) -> int:
        with self._reply_gen_lock:
            self._reply_gen += 1
            return self._reply_gen

    def _start_synced_speech(self, gen: int):
        """Подготовить синхронную озвучку ответа. ``None`` — если она недоступна."""
        if not self.sync_tts_enabled.get():
            return None
        try:
            from fish_tts import generate_miku_voice
            from speech_stream import SpeechStream

            language = self.response_language
            speech = SpeechStream(
                lambda text: generate_miku_voice(text, language=language),
                on_phrase=lambda seq, text: self.after(
                    0, lambda: self._on_spoken_phrase(gen, seq, text)
                ),
                on_done=lambda: self.after(0, lambda: self._on_speech_done(gen)),
                on_error=lambda exc: self.after(
                    0, lambda m=str(exc): self._on_speech_error(gen, m)
                ),
            )
            speech.start()
        except Exception as exc:
            logger.warning("Синхронная озвучка недоступна: %s", exc)
            return None

        self._active_speech = speech
        self._tts_in_progress = True
        self.after(0, lambda: self._status_begin("tts"))
        return speech

    def _on_spoken_phrase(self, gen: int, seq: int, text: str) -> None:
        """Фраза начинает звучать — показываем её в карточке ответа."""
        if gen != self._reply_gen:
            return
        if self._sync_gen != gen:
            self._sync_gen = gen
            self._sync_card = None
            self._sync_label = None
            self._sync_text = ""
            self._sync_last_seq = 0
        if seq <= self._sync_last_seq:
            return
        self._sync_last_seq = seq

        chunk = text or ""
        if not chunk.strip():
            return
        if self._sync_label is None:
            self._sync_card, self._sync_label = self._create_message_card_ex(
                "Мику", "", show_speaker=False
            )
        self._sync_text += chunk
        try:
            self._sync_label.configure(text=self._sync_text.strip())
        except Exception:
            pass
        self._scroll_chat_end()

    def _on_speech_done(self, gen: int) -> None:
        """Озвучка ответа доиграла: фиксируем полный текст и кнопку 🔊."""
        if gen != self._reply_gen:
            return
        full = self._pending_reply_text.pop(gen, "")
        self._tts_in_progress = False
        self._active_speech = None
        self._status_end("tts")

        text = (full or self._sync_text).strip()
        if self._sync_label is None:
            if text:
                self._append("Мику", text)
            self._set_panda_state("idle")
            return

        try:
            self._sync_label.configure(text=text)
            self._add_speaker_button(self._sync_card, self._text_for_tts(text))
        except Exception:
            logger.debug("Не удалось завершить карточку синхронной озвучки", exc_info=True)
        self._sync_card = None
        self._sync_label = None
        self._sync_text = ""
        self._set_panda_state("idle")

    def _on_speech_error(self, gen: int, message: str) -> None:
        if gen != self._reply_gen:
            return
        logger.warning("Ошибка синхронной озвучки: %s", message)
        self._append("Система", self.t("tts_error", error=message))

    def _cancel_active_speech(self) -> None:
        """Остановить текущую синхронную озвучку (перед новым сообщением)."""
        speech = self._active_speech
        self._active_speech = None
        if speech is not None:
            try:
                speech.cancel()
            except Exception:
                logger.debug("Не удалось отменить озвучку", exc_info=True)
        self._pending_reply_text.clear()
        # Старая карточка остаётся как есть, но новый ответ не должен в неё дописываться.
        self._sync_gen = 0
        self._sync_card = None
        self._sync_label = None
        self._sync_text = ""
        self._sync_last_seq = 0
        if self._tts_in_progress:
            self._tts_in_progress = False
            self._status_end("tts")

    def _update_idle_state(self) -> None:
        if not self._tts_in_progress:
            self._set_panda_state("idle")

    def _fetch_response(self, _user_text: str):
        speech = None
        gen = self._next_reply_gen()
        try:
            self.after(0, lambda: self._status_begin("chat"))
            self.after(0, lambda: self._set_panda_state("thinking"))
            try:
                sys_prompt = build_system_prompt(
                    self.personality, flirt_enabled=self.flirt_enabled.get(), nsfw_enabled=self.nsfw_enabled.get(),
                    hooks_enabled=self.hooks_enabled.get(), roleplay_interactive=self.interactive.get(),
                    emotion_set=self.emotion_set.get(), user_name=self.user_name,
                    response_language=self.response_language, compact=True,
                )
                api_messages = [{"role": "system", "content": sys_prompt}]
                for m in self.chat_history[-14:]:
                    api_messages.append(m)

                if self.auto_tts_enabled.get() and self.sync_tts_enabled.get():
                    speech = self._start_synced_speech(gen)

                if speech is not None and not self.nsfw_enabled.get():
                    # Gemini отдаёт текст токенами, а SpeechStream озвучивает
                    # готовые фразы и показывает их ровно в момент старта аудио.
                    reply, emo = self._fetch_miku_reply_stream(api_messages, speech.feed)
                else:
                    reply, emo = self._fetch_miku_reply(api_messages)
                    if speech is not None:
                        speech.feed(reply)
            except Exception as exc:
                if speech is not None:
                    speech.cancel()
                    self._active_speech = None
                    self._tts_in_progress = False
                    self.after(0, lambda: self._status_end("tts"))
                self.after(
                    0,
                    self._append,
                    "Система",
                    self.t("ai_error", error=exc),
                )
                return

            self._pending_reply_text[gen] = reply
            self.chat_history.append({"role": "assistant", "content": reply})
            self.after(0, self._set_emotion, emo)

            if speech is not None:
                speech.finish()
            elif self.auto_tts_enabled.get():
                self.after(0, self._append_miku_with_typing, reply)
                clean_tts = self._text_for_tts(reply)
                if clean_tts:
                    language = self.response_language
                    self.after(
                        200,
                        lambda payload=clean_tts, lang=language: self._request_tts(
                            payload, lang
                        ),
                    )
            else:
                self.after(0, self._append_miku_with_typing, reply)
        finally:
            self.after(0, lambda: self._status_end("chat"))
            self.after(0, self._update_idle_state)

    def _fetch_miku_reply_stream(self, api_messages: list[dict], on_delta=None) -> tuple[str, str]:
        """Потоковый ответ Gemini с передачей токенов в синхронную озвучку."""
        parts: list[str] = []
        pending: list[str] = []
        released = False
        for token in chat_stream(api_messages):
            if not token:
                continue
            parts.append(token)
            if on_delta is None:
                continue
            if released:
                on_delta(token)
                continue

            # Первые ~20 символов придерживаем: так отказ модели не успевает
            # попасть в озвучку до того, как его распознает _is_refusal().
            pending.append(token)
            prefix = "".join(pending)
            if len(prefix) >= 24 and not self._is_refusal(prefix):
                released = True
                on_delta(prefix)
            elif len(prefix) >= 300:
                released = True
                on_delta(prefix)

        if on_delta is not None and not released:
            prefix = "".join(pending)
            if prefix and not self._is_refusal(prefix):
                released = True
                on_delta(prefix)

        reply, emo = self._finalize_ai_reply("".join(parts))
        if on_delta is not None and not released and reply:
            # Отказ или пустой стрим заменяется готовой репликой — её тоже
            # нужно показать вместе с озвучкой, а не молча добавить в конце.
            on_delta(reply)
        return reply, emo

    def _finalize_ai_reply(self, raw: str) -> tuple[str, str]:
        reply, emo, _ = self._parse_ai_response(raw)
        emo = self._ensure_different_emotion(emo)
        last_emo = emo or self.last_emotion_key
        if self._chat_text(reply) and not self._is_refusal(reply):
            self.last_emotion_key = emo or self.last_emotion_key
            return reply, emo
        return self._ensure_miku_reply(""), last_emo

    def _append_miku_with_typing(self, message: str):
        message = self._ensure_miku_reply(message)
        if not self.typing_animation_enabled.get():
            self._append("Мику", message)
            return
        self._miku_type_gen += 1
        gen = self._miku_type_gen
        def start():
            self._miku_type_label = self._create_message_card("Мику", message)
            self._miku_type_label.configure(text="")
            self._miku_type_pending = message
            self._miku_type_index = 0
            self.after(8, lambda: self._miku_type_step(gen))
        self.after(0, start)

    def _miku_type_step(self, gen: int):
        if gen != self._miku_type_gen: return
        pending = getattr(self, "_miku_type_pending", "")
        i = getattr(self, "_miku_type_index", 0)
        if i >= len(pending): return
        rest = pending[i:]
        chunk = rest[:3] if len(rest) >= 3 else rest[:1]
        self._miku_type_index = i + len(chunk)
        self._miku_type_label.configure(text=pending[:self._miku_type_index])
        self._scroll_chat_end()
        delay = 8 if len(chunk) > 1 else 14
        self.after(delay, lambda: self._miku_type_step(gen))

    def _append(self, sender: str, message: str):
        body = self._chat_text(message)
        if body:
            self._create_message_card(sender, body)

    def _text_for_tts(self, raw: str) -> str:
        clean, _ = self._strip_emotion_tag(raw or "")
        return clean_text_for_tts(clean)

    def _set_emotion(self, emotion_key: str):
        current_set = self.emotion_set.get()
        fallback_key = default_greeting_emotion_key(current_set)
        emotion_key = self._resolve_emotion_key(emotion_key)
        self.last_emotion_key = emotion_key
        img = self.emotion_images.get(emotion_key) or self.emotion_images.get(fallback_key)
        self.char_label.configure(image=img)

    def _bind_chat_wheel_target(self, target):
        if target is None:
            return
        canvas = getattr(target, "_parent_canvas", None)
        if canvas is None:
            return
        for seq in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                canvas.bind(seq, self._on_chat_mouse_wheel)
            except Exception:
                pass

    def _on_chat_mouse_wheel(self, event):
        canvas = getattr(self.chat_history_frame, "_parent_canvas", None)
        if canvas is None:
            return "break"

        try:
            if hasattr(event, "delta") and event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
        except Exception:
            pass
        return "break"

    def _refresh_chat_scroll_region(self):
        frame = getattr(self, "chat_history_frame", None)
        if frame is None:
            return
        canvas = getattr(frame, "_parent_canvas", None)
        if canvas is None:
            return
        try:
            frame.update_idletasks()
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _resize_message_wraps(self, _event=None):
        width = max(220, self.chat_history_frame.winfo_width() - 110)
        for label in self._message_labels:
            if label.winfo_exists():
                label.configure(wraplength=width)
        self._refresh_chat_scroll_region()

    def _scroll_chat_end(self):
        frame = getattr(self, "chat_history_frame", None)
        if frame is None:
            return

        canvas = getattr(frame, "_parent_canvas", None)
        if canvas is None:
            canvas = getattr(frame, "_canvas", None)
        if canvas is None:
            scrollbar = getattr(frame, "_scrollbar", None)
            canvas = getattr(scrollbar, "_canvas", None)
        if canvas is None:
            return

        try:
            self._refresh_chat_scroll_region()
            canvas.update_idletasks()
            canvas.after_idle(lambda: canvas.yview_moveto(1.0))
        except Exception:
            pass

    def _status_tick(self, step: int) -> None:
        if not self._status_tags:
            self._status_after_id = None
            return
        base = self.t("thinking")
        if "tts" in self._status_tags:
            base = self.t("tts_loading")
        dots = "." * (1 + (step % 3))
        try: self._chat_status_label.configure(text=f"{base}{dots}")
        except Exception: pass
        self._status_after_id = self.after(400, lambda: self._status_tick(step + 1))

    def _status_begin(self, tag: str) -> None:
        self._status_tags.add(tag)
        if self._status_after_id is None: self._status_tick(0)

    def _status_end(self, tag: str) -> None:
        self._status_tags.discard(tag)
        if not self._status_tags:
            if self._status_after_id:
                try: self.after_cancel(self._status_after_id)
                except Exception: pass
                self._status_after_id = None
            try: self._chat_status_label.configure(text="")
            except Exception: pass

    def _request_tts(self, text: str, language: str | None = None) -> None:
        if not text.strip(): return
        language = language or self.response_language
        self._tts_in_progress = True
        self.after(0, lambda: self._status_begin("tts"))
        def worker():
            try:
                from fish_tts import speak_text_as_miku
                speak_text_as_miku(text, language=language)
            except Exception as e:
                self.after(0, lambda m=str(e): self._append(
                    "Система", self.t("tts_error", error=m)
                ))
            finally:
                self._tts_in_progress = False
                self.after(0, lambda: self._status_end("tts"))
                self.after(0, self._update_idle_state)
        threading.Thread(target=worker, daemon=True).start()

    def _install_tts_playback_listener(self):
        try:
            import audio_player
            def _on_playback(event, _duration_ms=0):
                if event == "start": self.after(0, lambda: self._set_panda_state("speaking"))
                elif event == "end": self.after(0, lambda: self._set_panda_state("idle"))
            audio_player.set_playback_listener(_on_playback)
        except Exception: pass

    def _set_panda_state(self, state: str):
        pw = getattr(self, '_panda_window', None)
        if not pw: return
        try:
            self._panda_state = state
            pw.send(f"state:{state}")
            if hasattr(self, "character_status"):
                sp = state == "speaking"
                self.character_status.configure(
                    text=self.t("speaking" if sp else "ready"),
                    text_color=ACCENT_LIGHT if sp else TEXT_MUTED,
                )
        except Exception: pass

    def _toggle_voice_input(self):
        if self.voice_input.is_listening:
            self.voice_input.stop()
            self._mic_stop_ui()
        else:
            self.mic_btn.configure(text="⏹", fg_color="#E06C75", hover_color="#C25961", text_color="#FFFFFF")
            self._chat_status_label.configure(text=self.t("recording"), text_color="#E06C75")
            self.voice_input.start(
                on_result=lambda text: self.after(0, self._insert_voice_text, text),
                on_error=lambda err: self.after(0, self._show_voice_error, err),
                on_processing=lambda: self.after(0, lambda: self._chat_status_label.configure(text=self.t("processing"), text_color="#E5C07B")),
                language=VOICE_LANGUAGE_CODES.get(self.response_language, VOICE_LANGUAGE_CODES["ru"]),
            )

    def _insert_voice_text(self, text: str):
        self._mic_stop_ui()
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()

    def _show_voice_error(self, error: str):
        self._mic_stop_ui()
        localized_error = error
        if error == "Не удалось распознать речь":
            localized_error = self.t("voice_recognition_failed")
        elif error == "Микрофон недоступен":
            localized_error = self.t("voice_unavailable")
        elif error.startswith("Микрофон не найден:"):
            localized_error = self.t("microphone_not_found")
        elif error.startswith("Ошибка сервиса распознавания:"):
            detail = error.partition(":")[2].strip()
            localized_error = self.t("speech_service_error", error=detail)
        elif error.startswith("Ошибка микрофона:"):
            detail = error.partition(":")[2].strip()
            localized_error = self.t("microphone_error", error=detail)
        elif "SpeechRecognition" in error or "pip install" in error:
            localized_error = self.t("voice_unavailable")
        self._chat_status_label.configure(text=f"⚠ {localized_error}", text_color="#E06C75")
        self.after(4000, lambda: self._chat_status_label.configure(text=""))

    def _mic_stop_ui(self):
        self.mic_btn.configure(text="🎤", fg_color=CARD_BG, hover_color=BORDER_COLOR, text_color=TEXT_MAIN)
        self._chat_status_label.configure(text="")

    def _fit_emotion_image(self, pil_img: Image.Image) -> Image.Image:
        tw, th = IMAGE_SIZE
        bg = _EMOTION_CANVAS_BG
        try: src = pil_img.convert("RGBA")
        except Exception: return Image.new("RGB", (tw, th), bg)
        w, h = src.size
        if w < 1 or h < 1: return Image.new("RGB", (tw, th), bg)
        scale = min(tw / w, th / h)
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        fitted = src.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (tw, th), bg + (255,))
        ox, oy = (tw - nw) // 2, (th - nh) // 2
        canvas.paste(fitted, (ox, oy), fitted)
        out = Image.new("RGB", (tw, th), bg)
        out.paste(canvas, mask=canvas.split()[3])
        return out

    def load_emotion_images(self):
        current_set = self.emotion_set.get()
        path_dir = self._resource_path(os.path.join(IMAGE_DIR, current_set))
        self.emotion_images.clear()
        emotions_dict = emotion_labels_for_set(current_set)
        ext = "." + emotion_ext_for_set(current_set)

        for key, desc in emotions_dict.items():
            path = os.path.join(path_dir, f"{key}{ext}")
            if os.path.isfile(path):
                try: pil_img = self._fit_emotion_image(Image.open(path))
                except Exception: pil_img = self._make_placeholder(desc)
            else:
                pil_img = self._make_placeholder(desc)
            self.emotion_images[key] = CTkImage(light_image=pil_img, size=IMAGE_SIZE)

    def _make_placeholder(self, label: str) -> Image.Image:
        img = Image.new("RGB", IMAGE_SIZE, color=_EMOTION_CANVAS_BG)
        draw = ImageDraw.Draw(img)
        try:
            font = self.placeholder_font or ImageFont.load_default()
            if hasattr(draw, "textbbox"):
                bbox = draw.textbbox((0, 0), label, font=font)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            else: w, h = (len(label) * 6, 10)
            draw.text(((IMAGE_SIZE[0] - w) / 2, (IMAGE_SIZE[1] - h) / 2), label, fill="#64748B", font=font)
        except Exception: pass
        return img


if __name__ == '__main__':
    from app_logging import setup_logging
    setup_logging()
    app = ChatApp()
    app.mainloop()