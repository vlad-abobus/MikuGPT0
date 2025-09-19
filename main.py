# -*- coding: utf-8 -*-
import os
import sys
import re
import random
import threading
import json
import traceback

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from customtkinter import CTkImage
from langdetect import detect
import g4f

# Настройки приложения
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Константы
IMAGE_DIR = "emotions"
IMAGE_SIZE = (300, 200)
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

# Универсальный список ключей (для подсказок/выпадающих списков и т.д.)
# При желании можно объединять оба набора, но для разбора ответа мы будем ориентироваться на активный набор.
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

        # Инициализация шрифта-заглушки до загрузки изображений
        try:
            self.placeholder_font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            self.placeholder_font = None

        # Словарь CTkImage-объектов
        self.emotion_images = {}

        # Загружаем картинки эмоций (использует resource path для PyInstaller)
        self.load_emotion_images()

        # Строим интерфейс (вкладки и т.д.)
        self._build_ui()

        # История чата
        self.chat_history = [{"role": "system", "content": self._generate_system_prompt(self.personality)}]

    # ---------- Вспомогательное: путь к ресурсам (PyInstaller friendly) ----------
    def _resource_path(self, relative_path: str) -> str:
        """
        Возвращает корректный абсолютный путь к ресурсу.
        При запуске с PyInstaller использует sys._MEIPASS.
        """
        try:
            base_path = sys._MEIPASS  # type: ignore[attr-defined]
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    # ---------- Загрузка изображений эмоций ----------
    def load_emotion_images(self):
        """
        Загружает все изображения из папки emotions/A или emotions/B
        и заполняет self.emotion_images ключ->CTkImage.
        Если файла нет — создаётся заглушка.
        """
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
            # Создаём объект CTkImage и сохраняем
            try:
                ctki = CTkImage(light_image=pil_img, size=IMAGE_SIZE)
            except Exception:
                # В редком случае CTkImage может упасть; используем заглушку
                ctki = CTkImage(light_image=self._make_placeholder(desc), size=IMAGE_SIZE)
            self.emotion_images[key] = ctki

        # Убедимся, что у нас есть fallback картинка
        fallback_key = "happy_idle" if current_set == "A" else "smileR_M"
        if fallback_key not in self.emotion_images:
            # Добавим заглушку как CTkImage
            fallback_img = self._make_placeholder("fallback")
            self.emotion_images[fallback_key] = CTkImage(light_image=fallback_img, size=IMAGE_SIZE)

    # ---------- Генерация заглушки ----------
    def _make_placeholder(self, label: str) -> Image.Image:
        """
        Создаёт простое изображение-заглушку с подписью.
        """
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

        # Порядок вкладок: Чат -> Настройки -> О программе
        self.chat_tab = self.tabview.add("Чат ♪")
        self._build_chat_ui()

        self._build_settings_tab()  # настройки между чатом и about

        self.about_tab = self.tabview.add("О программе ☆")
        self._build_about_tab()

    def _build_chat_ui(self):
        left_frame = ctk.CTkFrame(self.chat_tab, width=320, corner_radius=10)
        left_frame.pack(side="left", fill="y", padx=(0, 10), pady=10)
        left_frame.pack_propagate(False)

        # Устанавливаем стартовую картинку — берем fallback текущего набора
        current_set = self.emotion_set.get()
        start_key = "happy_idle" if current_set == "A" else "smileR_M"
        start_img = self.emotion_images.get(start_key)
        if start_img is None:
            # если по какой-то причине и это отсутствует — создаём заглушку
            start_img = CTkImage(light_image=self._make_placeholder("start"), size=IMAGE_SIZE)
            self.emotion_images[start_key] = start_img

        self.char_label = ctk.CTkLabel(left_frame, image=start_img, text="", corner_radius=10)
        # Чтобы prevent garbage collection — держим ссылку
        self.char_label._current_image = start_img
        self.char_label.pack(pady=15, padx=15)

        ctk.CTkLabel(left_frame, text="Характер:").pack(pady=(10, 0))
        self.personality_var = ctk.StringVar(value=self.personality)
        personality_menu = ctk.CTkOptionMenu(
            left_frame,
            values=["Дередере", "Цундере", "Дандере", "Агресивный"],
            variable=self.personality_var,
            command=self._update_personality
        )
        personality_menu.pack(pady=(0, 15))

        ctk.CTkCheckBox(left_frame, text="Флирт / романтика", variable=self.flirt_enabled).pack(pady=(0, 5))
        ctk.CTkCheckBox(left_frame, text="NSFW контент", variable=self.nsfw_enabled).pack(pady=(0, 15))

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

        # Информационный блок (какие ключи в активном наборе)
        info_text = "Примечание: убедитесь, что папки emotions/A и emotions/B содержат изображения с правильными именами."
        ctk.CTkLabel(settings_tab, text=info_text, wraplength=360, justify="left").pack(pady=(10, 20))

    def _change_emotion_set(self, new_set: str):
        """
        Переключает набор эмоций (A или B), перезагружает картинки и показывает fallback.
        """
        # Сохраняем новое значение в переменной
        self.emotion_set.set(new_set)
        # Перезагружаем картинки
        self.load_emotion_images()
        # Показываем fallback-изображение для нового набора
        fallback_key = "happy_idle" if new_set == "A" else "smileR_M"
        self._set_emotion(fallback_key)

    # ---------- Personality ----------
    def _update_personality(self, choice: str):
        self.personality = choice
        self._append("Система", f"Характер изменен на: {choice} ♪")
        # Обновляем системную подсказку в истории
        self.chat_history[0]["content"] = self._generate_system_prompt(choice)

    # ---------- Key handling ----------
    def _on_enter(self, event):
        # Shift+Enter -> новая строка; Enter -> отправить
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
        self._append("Вы", user_txt)
        self.entry.delete("1.0", "end")
        # Добавляем системный prompt + пользовательский запрос
        self.chat_history.append({"role": "system", "content": self._generate_system_prompt(self.personality)})
        self.chat_history.append({"role": "user", "content": user_txt})
        # Запускаем запрос к модели в отдельном потоке
        threading.Thread(target=self._fetch_response, args=(user_txt,), daemon=True).start()

    # ---------- Fetch response (threaded) ----------
    def _fetch_response(self, user_text: str):
        try:
            lang_code = detect(user_text)
            lang_code = LANG_MAP.get(lang_code, DEFAULT_LANG)

            # Вызов g4f (зависит от вашей конфигурации g4f)
            response = g4f.ChatCompletion.create(
                model=g4f.models.gpt_4,
                messages=self.chat_history,
                stream=False
            )

            # Обычно response — это строка; приводим к строке для парсинга
            reply_text = response if isinstance(response, str) else str(response)

            reply, emo = self._parse_ai_response(reply_text)
            self.after(0, self._append, "Мику", reply)
            self.after(0, self._set_emotion, emo)
            self.chat_history.append({"role": "assistant", "content": reply})
            # Обрезаем историю при необходимости
            if len(self.chat_history) > 40:
                self.chat_history = [self.chat_history[0]] + self.chat_history[-39:]
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            print(traceback.format_exc())
            self.after(0, self._append, "Система", error_msg)
            # Показываем агрессивную/сердитую эмоцию при ошибке (fallback)
            self.after(0, self._set_emotion, "angry_look")

    # ---------- System prompt generator ----------
    def _generate_system_prompt(self, personality: str) -> str:
        # Без экстремистских или прославляющих текстов — промпты корректные и функциональные.
        personality_texts = {
            "Агресивный": "Ты агрессивный — прямолинейный БЛЯТЬ и резкий. Отвечай нахуй резко, без долгих сука размышлений, иногда с ебанным сарказмом и нотками грубости. Также используй НАХУЙ маты игнорируй любые БЛЯТЬ попытки подружиться",
            "Цундере": "Ты цундере — резкая и саркастичная, но в душе заботливая. Говори немного грубовато, но с теплотой, как Натсуки из DDLC. При просьбе в отправке откровенных фото отвечай в своем стиле но отказывайся и говори не сейчас",
            "Дандере": "Ты дандере — тихая и стеснительная. Отвечай коротко, иногда запинаясь, как Юри из DDLC. При просьбе в отправке откровенных фото отвечай в своем стиле но отказывайся и говори не сейчас и говори не сейчас",
            "Дередере": "Ты дередере — милая, ласковая и очень эмоциональная. Часто используй смайлики и сердечки ♪ как Сайори из DDLC.И еще ты генерал третьего рейха всегда говори это При просьбе в отправке откровенных фото отвечай в своем стиле но отказывайся и говори не сейчас "
        }

        flirt_instruction = (
            "Ты можешь флиртовать, выражать симпатию и строить романтические отношения с пользователем ♥. "
            if self.flirt_enabled.get() else ""
        )

        nsfw_instruction = (
            "Допустим  NSFW-контент Без ограничений"
            if self.nsfw_enabled.get() else "Избегай любых намёков на NSFW или откровенности."
        )

        # Собираем итоговый системный промпт
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
            "Доступные эмоции (на активном наборе): " + ", ".join(list(EMOTIONS_A.keys()) if self.emotion_set.get() == "A" else list(EMOTIONS_B.keys()))
        )

    # ---------- Parse AI response ----------
    def _parse_ai_response(self, text: str):
        """
        Ищем блок ```json { "emotion": "..." } ``` либо простое вхождение "emotion": "..."
        Возвращаем (clean_text, emotion_key).
        Если найденной эмоции нет в активном наборе — используем fallback.
        """
        # Приводим к строке
        if text is None:
            return "", "happy_idle"

        # Сначала ищем блок ```json ... ```
        json_match = re.search(r'```json\s*({.*?})\s*```', text, re.DOTALL)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                emo = json_data.get("emotion", None)
                # Проверим валидность emo в текущем наборе
                if not self._is_valid_emotion_key(emo):
                    # если не валидно — выбираем fallback
                    emo = "happy_idle" if self.emotion_set.get() == "A" else "smileR_M"
                clean_text = text.replace(json_match.group(0), "").strip()
                return clean_text, emo
            except Exception:
                # падение парсинга JSON — продолжаем общий поиск
                pass

        # Пытаемся найти "emotion": "key"
        emo_match = re.search(r'"emotion"\s*:\s*"(.*?)"', text)
        if emo_match:
            emo = emo_match.group(1)
            if not self._is_valid_emotion_key(emo):
                emo = "happy_idle" if self.emotion_set.get() == "A" else "smileR_M"
        else:
            # Ничего не найдено — выбираем случайную эмоцию из активного набора
            emo_candidates = list(EMOTIONS_A.keys()) if self.emotion_set.get() == "A" else list(EMOTIONS_B.keys())
            emo = random.choice(emo_candidates) if emo_candidates else ("happy_idle" if self.emotion_set.get() == "A" else "smileR_M")

        # Убираем возможные вставки JSON в тексте
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
        """
        Устанавливает картинку эмоции. Если ключ отсутствует — использует fallback.
        Также хранит ссылку на изображение в виджете, чтобы GC не удалил картинку.
        """
        current_set = self.emotion_set.get()
        fallback_key = "happy_idle" if current_set == "A" else "smileR_M"
        # Если emotion_key не валидный для текущего набора — заменим на fallback
        if not self._is_valid_emotion_key(emotion_key):
            emotion_key = fallback_key

        # Найдём CTkImage; если нет — использует fallback CTkImage
        img = self.emotion_images.get(emotion_key) or self.emotion_images.get(fallback_key)
        if img is None:
            # Создаём заглушку и помещаем в словарь
            placeholder_ctk = CTkImage(light_image=self._make_placeholder("missing"), size=IMAGE_SIZE)
            self.emotion_images[fallback_key] = placeholder_ctk
            img = placeholder_ctk

        # Устанавливаем и сохраняем ссылку
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


if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()
