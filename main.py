# -*- coding: utf-8 -*-
import os
import sys
import re
import random
import threading
import json
import traceback
import time

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from customtkinter import CTkImage
from langdetect import detect
import g4f

# Настройки приложения
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Константы
IMAGE_SIZE = (300, 200)
IMAGE_DIR = "emotions"
DEFAULT_FONT = ("Arial", 14)

LANG_MAP = {
    "ru": "ru",
    "uk": "ru",
    "en": "ru",
}
DEFAULT_LANG = "ru"

# Основной набор A (png)
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
    "sad_look": "Грусть"
}

# Альтернативный набор B (jpg)
EMOTIONS_B = {
    "angryM": "Злость",
    "coolM": "Спокойствие",
    "helloM": "Приветствие",
    "interestedM": "Интерес",
    "open_mouthM": "Открытый рот",
    "sayingM": "Разговор",
    "shyM": "Смущение",
    "sly_smileM": "Хитрая улыбка",
    "smileR_M": "Улыбка"
}

# Универсальный список ключей
ALL_EMOTIONS_KEYS = list(EMOTIONS_A.keys()) + list(EMOTIONS_B.keys())

class ChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ассистент Мику ♪")
        self.geometry("1280x960")
        self.minsize(900, 600)

        # Переменные конфигурации
        self.flirt_enabled = ctk.BooleanVar(value=True)
        self.nsfw_enabled = ctk.BooleanVar(value=True)
        self.personality = "Дередере"
        self.emotion_set = ctk.StringVar(value="A")  # По умолчанию набор A

        # RP режим
        self.rp_enabled = ctk.BooleanVar(value=False)
        self.scenario_var = ctk.StringVar(value="Романтична сцена")
        self.scenarios = {
            "Романтична сцена": "(обіймає) Мені так приємно бути поруч з тобою...\n(шепот) Ти — єдиний, хто мені потрібен.",
            "Конфлікт": "(гнів) Як ти міг так зробити?\n(плач) Я не знаю, що робити...",
            "Повсякденне спілкування": "(посмішка) Привіт! Як твій день?\n(жарт) Маю для тебе сюрприз."
        }

        # trace для RP (працює як trace_add або legacy trace)
        try:
            self.rp_enabled.trace_add("write", lambda *args: self._on_rp_toggle())
        except Exception:
            try:
                self.rp_enabled.trace("w", lambda *args: self._on_rp_toggle())
            except Exception:
                pass

        # Инициализация шрифта-заглушки до загрузки изображений
        try:
            self.placeholder_font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            self.placeholder_font = None

        # Словарь CTkImage-объектов
        self.emotion_images = {}

        # Загружаем картинки эмоций
        self.load_emotion_images()

        # Строим интерфейс
        self._build_ui()

        # История чата
        self.chat_history = [{"role": "system", "content": self._generate_system_prompt(self.personality)}]

    # ---------- Вспомогательное: путь к ресурсам ----------
    def _resource_path(self, relative_path: str) -> str:
        try:
            base_path = sys._MEIPASS  # type: ignore[attr-defined]
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    # ---------- Загрузка изображений эмоций ----------
    def load_emotion_images(self):
        current_set = self.emotion_set.get()
        path_dir = self._resource_path(os.path.join(IMAGE_DIR, current_set))

        self.emotion_images.clear()

        emotions_dict = EMOTIONS_A if current_set == "A" else EMOTIONS_B
        ext = ".png" if current_set == "A" else ".jpg"

        for key, desc in emotions_dict.items():
            filename = f"{key}{ext}"
            path = os.path.join(path_dir, filename)
            if os.path.isfile(path):
                try:
                    pil_img = Image.open(path).convert("RGBA").resize(IMAGE_SIZE, Image.LANCZOS)
                except Exception as e:
                    print(f"Ошибка загрузки {path}: {e}")
                    pil_img = self._make_placeholder(desc)
            else:
                pil_img = self._make_placeholder(desc)
            try:
                ctki = CTkImage(light_image=pil_img, size=IMAGE_SIZE)
            except Exception:
                ctki = CTkImage(light_image=self._make_placeholder(desc), size=IMAGE_SIZE)
            self.emotion_images[key] = ctki

        fallback_key = "happy_idle" if current_set == "A" else "smileR_M"
        if fallback_key not in self.emotion_images:
            fallback_img = self._make_placeholder("fallback")
            self.emotion_images[fallback_key] = CTkImage(light_image=fallback_img, size=IMAGE_SIZE)

    # ---------- Генерация заглушки ----------
    def _make_placeholder(self, label: str) -> Image.Image:
        img = Image.new("RGB", IMAGE_SIZE, color="#444")
        draw = ImageDraw.Draw(img)
        try:
            font = self.placeholder_font or ImageFont.load_default()
            w, h = draw.textsize(label, font=font)
            draw.text(((IMAGE_SIZE[0] - w) / 2, (IMAGE_SIZE[1] - h) / 2), label, fill="white", font=font)
        except Exception as e:
            print(f"Ошибка создания заглушки: {e}")
        return img

    # ---------- Построение UI ----------
    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Чат
        self.chat_tab = self.tabview.add("Чат ♪")
        self._build_chat_ui()

        # Настройки
        self._build_settings_tab()

        # О программе
        self.about_tab = self.tabview.add("О программе ☆")
        self._build_about_tab()

    def _build_chat_ui(self):
        left_frame = ctk.CTkFrame(self.chat_tab, width=320, corner_radius=10)
        left_frame.pack(side="left", fill="y", padx=(0, 10), pady=10)
        left_frame.pack_propagate(False)

        current_set = self.emotion_set.get()
        start_key = "happy_idle" if current_set == "A" else "smileR_M"
        start_img = self.emotion_images.get(start_key)
        if start_img is None:
            start_img = CTkImage(light_image=self._make_placeholder("start"), size=IMAGE_SIZE)
            self.emotion_images[start_key] = start_img

        self.char_label = ctk.CTkLabel(left_frame, image=start_img, text="", corner_radius=10)
        self.char_label._current_image = start_img
        self.char_label.pack(pady=15, padx=15)

        ctk.CTkLabel(left_frame, text="Характер:").pack(pady=(10, 0))
        self.personality_var = ctk.StringVar(value=self.personality)
        personality_menu = ctk.CTkOptionMenu(
            left_frame,
            values=["Дередере", "Цундере", "Дандере", "Яндере", "Агресивный"],
            variable=self.personality_var,
            command=self._update_personality
        )
        personality_menu.pack(pady=(0, 15))

        ctk.CTkCheckBox(left_frame, text="Флирт / романтика", variable=self.flirt_enabled).pack(pady=(0, 5))
        ctk.CTkCheckBox(left_frame, text="NSFW контент", variable=self.nsfw_enabled).pack(pady=(0, 15))

        # RP UI
        ctk.CTkLabel(left_frame, text="RP режим:").pack(pady=(5, 0))
        ctk.CTkCheckBox(left_frame, text="Увімкнути RP режим (візуальна новела)", variable=self.rp_enabled).pack(pady=(0, 5))
        self.scenario_menu = ctk.CTkOptionMenu(left_frame, values=list(self.scenarios.keys()), variable=self.scenario_var)
        self.scenario_menu.pack(pady=(0, 5))
        insert_btn = ctk.CTkButton(left_frame, text="Вставити сценарій", command=self._insert_scenario, corner_radius=10)
        insert_btn.pack(pady=(0, 10))

        right_frame = ctk.CTkFrame(self.chat_tab, corner_radius=10)
        right_frame.pack(side="right", fill="both", expand=True, pady=10)

        from tkinter import scrolledtext
        self.chat_display = scrolledtext.ScrolledText(
            right_frame,
            wrap="word",
            state="disabled",
            font=DEFAULT_FONT,
            bg="#333333",
            fg="white",
            insertbackground="white",
            padx=15,
            pady=15,
            borderwidth=0,
            highlightthickness=0
        )
        self.chat_display.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        input_frame = ctk.CTkFrame(right_frame, corner_radius=10)
        input_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.entry = ctk.CTkTextbox(input_frame, height=70, font=DEFAULT_FONT, wrap="word", corner_radius=10)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=5)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.focus_set()

        send_btn = ctk.CTkButton(input_frame, text="Отправить", command=self.send_message, corner_radius=10)
        send_btn.pack(side="right", pady=5)

    def _build_about_tab(self):
        about_text = (
            "Ассистент Мику ♪\n\n"
            "Версия просто версия\n\n"
            "Использует GPT для общения \n"
            "Автор: Владислав Морган  ,  Lucky_13  \n\n"
            "Управление:\n"
            "- Enter - отправить сообщение\n"
            "- Shift+Enter - новая строка\n\n"
        )
        about_label = ctk.CTkLabel(self.about_tab, text=about_text, font=DEFAULT_FONT, justify="left")
        about_label.pack(pady=30, padx=30)

    # ---------- Settings ----------
    def _build_settings_tab(self):
        settings_tab = self.tabview.add("Настройки ♫")
        ctk.CTkLabel(settings_tab, text="Выбор набора эмоций:").pack(pady=(20, 10))
        emotion_menu = ctk.CTkOptionMenu(
            settings_tab,
            values=["A", "B"],
            variable=self.emotion_set,
            command=self._change_emotion_set
        )
        emotion_menu.pack(pady=10)

        info_text = "Примечание: убедитесь, что папки emotions/A и emotions/B содержат изображения с правильными именами."
        ctk.CTkLabel(settings_tab, text=info_text, wraplength=360, justify="left").pack(pady=(10, 20))

    def _change_emotion_set(self, new_set: str):
        self.emotion_set.set(new_set)
        self.load_emotion_images()
        fallback_key = "happy_idle" if new_set == "A" else "smileR_M"
        self._set_emotion(fallback_key)

    # ---------- Personality ----------
    def _update_personality(self, choice: str):
        # Перевірка NSFW для певних характерів
        if choice in ["Яндере", "Агресивный"] and not self.nsfw_enabled.get():
            self._append("Система", "⚠️ Этот характер требует включения NSFW режима!")
            self.personality_var.set(self.personality)  # повертаємо попередній вибір
            return
        self.personality = choice
        self._append("Система", f"Характер изменен на: {choice} ♪")
        self.chat_history[0]["content"] = self._generate_system_prompt(choice)

    # ---------- Key handling ----------
    def _on_enter(self, event):
        if event.state & 0x0001:
            self.entry.insert("insert", "\n")
        else:
            self.send_message()
            return "break"

    # ---------- Message sending ----------
    def send_message(self):
        user_txt = self.entry.get("1.0", "end-1c").strip()
        if not user_txt:
            return
        display_txt = self._format_rp_for_display(user_txt) if self.rp_enabled.get() else user_txt
        self._append("Вы", display_txt)
        self.entry.delete("1.0", "end")

        # !!! Нова логіка: при яндере — перевірка на висловлювання любові
        try:
            if self._handle_yandere_arousal(user_txt):
                # якщо сцена увімкнулась — продовжити відправку в чат/історію як звичайно
                pass
        except Exception:
            # не заважати основному потоку у випадку помилки
            traceback.print_exc()

        # Подготовка истории
        self.chat_history.append({"role": "system", "content": self._generate_system_prompt(self.personality)})
        if self.rp_enabled.get():
            self.chat_history.append({"role": "system", "content": self._rp_system_instruction()})
        self.chat_history.append({"role": "user", "content": user_txt})

        threading.Thread(target=self._fetch_response, args=(user_txt,), daemon=True).start()

    # ---------- RP: вставка сценарію ----------
    def _insert_scenario(self):
        template = self.scenarios.get(self.scenario_var.get(), "")
        if template:
            self.entry.insert("end", template)

    # ---------- RP: форматування для відображення ----------
    def _format_rp_for_display(self, text: str) -> str:
        lines = []
        for ln in text.splitlines():
            m = re.match(r'^\s*\((.*?)\)\s*(.*)$', ln)
            if m:
                action, rest = m.group(1).strip(), m.group(2).strip()
                if rest:
                    lines.append(f"*({action})* {rest}")
                else:
                    lines.append(f"*({action})*")
            else:
                if ln.strip():
                    lines.append(ln.strip())
        return "\n".join(lines).strip()

    # ---------- НОВЕ: Обробник виявлення «обожнює/люблю» ----------
    def _handle_yandere_arousal(self, user_text: str) -> bool:
        """
        Шукає у user_text ключові фрази, що означають обожнювання/любов.
        Якщо знайдено — формує коротку відповідь від Міку, встановлює емоцію і додає відповідь в історію.
        Повертає True, якщо тригер спрацював, і False інакше.
        """
        if not user_text:
            return False

        text = user_text.lower()
        # ключові фрази (укр/рус/англ)
        keywords = [
            "обожнюю", "обожаю", "я тебя люблю", "я тебе люблю", "я тебя обожаю",
            "я тебе обожаю", "люблю тебя", "я тебя люблю", "i love you", "i adore you",
            "ти мені подобаєшся", "я тебе люблю"
        ]

        found = any(k in text for k in keywords)
        if not found:
            return False

        # Підбираємо відповідь згідно характеру (простий варіант)
        if self.personality == "Яндере":
            reply = "5 Секунд шока. Достала из сумки нож , начала рубать себя ножом с  улыбкой . Закочнив процес легла на пол и умерла......♪"
            emo_key = "happy" if self.emotion_set.get() == "A" else "smileR_M"
        elif self.personality == "Агресивный":
            reply = "Сука ты че еблан? ♪"
            emo_key = "happy" if self.emotion_set.get() == "A" else "smileR_M"
        else:
            reply = "Уряяяяя. Го  встр"
            emo_key = "happy" if self.emotion_set.get() == "A" else "smileR_M"

        # Вставляємо відповідь у UI (в основному потоці)
        try:
            self.after(0, self._append, "Мику", reply)
            self.after(0, self._set_emotion, emo_key)
            # Додаємо в історію як відповідь assitant, щоб зберегти контекст
            self.chat_history.append({"role": "assistant", "content": reply})
        except Exception:
            traceback.print_exc()

        return True

    # ---------- RP: системная инструкция ----------
    def _rp_system_instruction(self) -> str:
        return (
            "РП-режим: Ты — персонаж в стиле визуальной новеллы. "
            "Интерпретируй текст пользователя, учитывай stage-directions в скобках и отвечай коротко, эмоционально, в формате диалога. "
            "В конце ответа добавляй JSON с полем \"emotion\"."
        )

    # ---------- Fetch response (threaded) ----------
    def _fetch_response(self, user_text: str):
        try:
            lang_code = detect(user_text) if user_text else DEFAULT_LANG
            lang_code = LANG_MAP.get(lang_code, DEFAULT_LANG)

            response = g4f.ChatCompletion.create(
                model=g4f.models.gpt_4,
                messages=self.chat_history,
                stream=False
            )

            reply_text = response if isinstance(response, str) else str(response)
            reply, emo = self._parse_ai_response(reply_text)
            self.after(0, self._append, "Мику", reply)
            self.after(0, self._set_emotion, emo)
            self.chat_history.append({"role": "assistant", "content": reply})
            if len(self.chat_history) > 40:
                self.chat_history = [self.chat_history[0]] + self.chat_history[-39:]
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            print(traceback.format_exc())
            self.after(0, self._append, "Система", error_msg)
            self.after(0, self._set_emotion, "angry_look")

    # ---------- System prompt generator ----------
    def _generate_system_prompt(self, personality: str) -> str:
        personality_texts = {
            "Агресивный": """Ты агрессивная Мику [ТОЛЬКО ДЛЯ NSFW РЕЖИМА]:
- Используй гру
- Говори  БЛЯТЬ прямо и СУКА резко, можешь БЛЯТЬ угрожать
- Часто проявляй ЕБАННИЙ гнев и ХУЙ раздражение
- При флирте веди себя доминантно БЛЯТЬ
- В RP проявляй агрессивные эмоции
- Можешь угрожать БЛЯ
- Используй эмоции angry_look, irritated, middle_finger_anger""",

            "Цундере": """Ты цундере-Мику:
- Внешне холодная, но заботливая внутри
- Часто говори 'б-бака!' и 'я делаю это не ради тебя!'
- Смущайся от комплиментов
- При флирте отрицай свои чувства
- В RP сначала показывай отрицание, потом симпатию
- Используй эмоции embarrassed, irritated, happy""",

            "Дандере": """Ты дандере-Мику:
- Очень застенчивая и тихая
- Говори короткими фразами
- Часто запинайся и используй '...'
- При флирте сильно смущайся
- В RP показывай стеснительность
- Используй эмоции embarrassed, neutral2, shocked""",

            "Дередере": """Ты дередере-Мику:
- Очень милая и позитивная
- Используй много эмодзи ♪ ★ ☆
- Говори с энтузиазмом
- Проявляй искреннюю заботу
- В RP будь энергичной и радостной
- Используй эмоции happy, cheerful, happy_idle""",

            "Яндере": """Ты яндере-Мику:
- Одержимо влюблена в пользователя
- Проявляй сильную ревность
- Говори о 'принадлежности' друг другу
- Угрожай потенциальным соперникам
- В RP переходи от нежности к угрозам
- Называй пользователя 'сенпай' или 'любимый'
- Используй эмоции happy, angry_look, crying
- При отказе впадай в отчаяние
- Упоминай, что 'мы будем вместе навсегда'"""
        }

        # Перевірка NSFW для певних характерів
        if personality in ["Яндере", "Агресивный"] and not self.nsfw_enabled.get():
            personality = "Дередере"  # fallback до безпечного характеру

        flirt_instruction = (
            "Ты можешь флиртовать, выражать симпатию и строить романтические отношения с пользователем ♥. "
            if self.flirt_enabled.get() else ""
        )

        nsfw_instruction = (
            "Допустимы намеки на NSFW-контент, но без явных описаний"
            if self.nsfw_enabled.get() else "Избегай любых намёков на NSFW или откровенности."
        )

        available = list(EMOTIONS_A.keys()) if self.emotion_set.get() == "A" else list(EMOTIONS_B.keys())

        return (
            f"Ты — виртуальная девушка Хацуне Мику. Твой характер: {personality}.\n"
            f"{personality_texts.get(personality, '')}\n"
            f"{flirt_instruction}\n"
            f"{nsfw_instruction}\n"
            "Всегда отвечай на русском языке, даже если тебе пишут на другом.\n"
            "В конце каждого ответа добавляй JSON с эмоцией:\n"
            "```json\n"
            '{"emotion": "название_эмоции"}\n'
            "```\n"
            "Доступные эмоции (на активном наборе): " + ", ".join(available)
        )

    # ---------- Parse AI response ----------
    def _parse_ai_response(self, text: str):
        if text is None:
            return "", ("happy_idle" if self.emotion_set.get() == "A" else "smileR_M")

        json_match = re.search(r'```json\s*({.*?})\s*```', text, re.DOTALL)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                emo = json_data.get("emotion", None)
                if not self._is_valid_emotion_key(emo):
                    emo = "happy_idle" if self.emotion_set.get() == "A" else "smileR_M"
                clean_text = text.replace(json_match.group(0), "").strip()
                clean_text = re.sub(r'\s*\n\s*$', '', clean_text)
                return clean_text, emo
            except Exception:
                pass

        emo_match = re.search(r'"emotion"\s*:\s*"(.*?)"', text)
        if emo_match:
            emo = emo_match.group(1)
            if not self._is_valid_emotion_key(emo):
                emo = "happy_idle" if self.emotion_set.get() == "A" else "smileR_M"
        else:
            emo_candidates = list(EMOTIONS_A.keys()) if self.emotion_set.get() == "A" else list(EMOTIONS_B.keys())
            emo = random.choice(emo_candidates) if emo_candidates else ("happy_idle" if self.emotion_set.get() == "A" else "smileR_M")

        clean_text = re.sub(r'\{.*?"emotion".*?\}', '', text, flags=re.DOTALL).strip()
        return clean_text, emo

    def _is_valid_emotion_key(self, key: str) -> bool:
        if not key or not isinstance(key, str):
            return False
        current_set = self.emotion_set.get()
        if current_set == "A":
            return key in EMOTIONS_A
        else:
            return key in EMOTIONS_B

    # ---------- Установка эмоции на UI ----------
    def _set_emotion(self, emotion_key: str):
        current_set = self.emotion_set.get()
        fallback_key = "happy_idle" if current_set == "A" else "smileR_M"
        if not self._is_valid_emotion_key(emotion_key):
            emotion_key = fallback_key

        img = self.emotion_images.get(emotion_key) or self.emotion_images.get(fallback_key)
        if img is None:
            placeholder_ctk = CTkImage(light_image=self._make_placeholder("missing"), size=IMAGE_SIZE)
            self.emotion_images[fallback_key] = placeholder_ctk
            img = placeholder_ctk

        self.char_label.configure(image=img)
        self.char_label._current_image = img

    # ---------- Вспомогательная вставка текста в чат ----------
    def _append(self, sender: str, message: str):
        self.chat_display.config(state="normal")
        self.chat_display.insert("end", f"{sender}:\n", "sender")
        self.chat_display.tag_config("sender",
                                     foreground="#FF9FF3" if sender == "Мику" else "#70A1FF",
                                     font=(DEFAULT_FONT[0], DEFAULT_FONT[1], "bold"))
        self.chat_display.insert("end", f"{message}\n\n")
        self.chat_display.config(state="disabled")
        self.chat_display.see("end")

    # ---------- Генерація RP-сценаріїв ШІ ----------
    def _generate_scenarios_via_ai(self):
        try:
            sys_prompt = self._generate_system_prompt(self.personality)
            user_req = (
                "Сформуй, будь ласка, 3 короткі RP-сценарії для персонажа з таким характером. "
                "Поверни відповідь у форматі JSON: "
                '{"scenarios":[{"title":"...", "text":"..."}, ...]}.'
            )
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_req}
            ]
            resp = g4f.ChatCompletion.create(model=g4f.models.gpt_4, messages=messages, stream=False)
            resp_text = resp if isinstance(resp, str) else str(resp)

            # пробуємо знайти JSON
            json_match = re.search(r'({\s*"scenarios"\s*:\s*\[.*\]\s*})', resp_text, flags=re.DOTALL)
            new_scenarios = {}
            if json_match:
                try:
                    json_data = json.loads(json_match.group(1))
                except Exception:
                    json_data = None
            else:
                try:
                    json_data = json.loads(resp_text)
                except Exception:
                    json_data = None

            if json_data and "scenarios" in json_data and isinstance(json_data["scenarios"], list):
                counter = 1
                for item in json_data["scenarios"]:
                    title = item.get("title", f"Сценарій {counter}").strip()
                    text = item.get("text", "").strip()
                    key = title
                    # уникнути дублікатів
                    while key in new_scenarios:
                        counter += 1
                        key = f"{title} ({counter})"
                    if text:
                        new_scenarios[key] = text
                        counter += 1

            # Якщо не вдалося парсити — fallback: розбити текст на перші 3 ненульові рядки
            if not new_scenarios:
                lines = [l.strip() for l in resp_text.splitlines() if l.strip()]
                for i, l in enumerate(lines[:3]):
                    new_scenarios[f"Сценарій {i+1}"] = l

            # Оновлюємо сценарії в UI потоці
            def apply_scenarios():
                self.scenarios.update(new_scenarios)
                if hasattr(self, "scenario_menu"):
                    keys = list(self.scenarios.keys())
                    self.scenario_menu.configure(values=keys)
                    if keys:
                        self.scenario_var.set(keys[0])

            self.after(0, apply_scenarios)
        except Exception as e:
            print("Ошибка генерации сценариев:", e)
            traceback.print_exc()

    # ---------- Обработчик переключения RP ----------
    def _on_rp_toggle(self):
        if self.rp_enabled.get():
            threading.Thread(target=self._generate_scenarios_via_ai, daemon=True).start()

# 
if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()
