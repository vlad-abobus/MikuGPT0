# -*- coding: utf-8 -*-
import os
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

EMOTIONS = {
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


class ChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ассистент Мику ♪")
        self.geometry("1280x960")
        self.minsize(900, 600)

        self.flirt_enabled = ctk.BooleanVar(value=True)
        self.nsfw_enabled = ctk.BooleanVar(value=True)
        self.personality = "Дередере"

        self.emotion_images = {}
        self.load_emotion_images()
        self._build_ui()
        self.chat_history = [{"role": "system", "content": self._generate_system_prompt(self.personality)}]

        try:
            self.placeholder_font = ImageFont.truetype("arial.ttf", 20)
        except:
            self.placeholder_font = None

    def load_emotion_images(self):
        for key, desc in EMOTIONS.items():
            path = os.path.join(IMAGE_DIR, f"{key}.png")
            if os.path.isfile(path):
                try:
                    img = Image.open(path).resize(IMAGE_SIZE, Image.LANCZOS)
                except Exception as e:
                    print(f"Ошибка загрузки {path}: {e}")
                    img = self._make_placeholder(desc)
            else:
                img = self._make_placeholder(desc)
            self.emotion_images[key] = CTkImage(light_image=img, size=IMAGE_SIZE)

    def _make_placeholder(self, label: str):
        img = Image.new("RGB", IMAGE_SIZE, color="#444")
        draw = ImageDraw.Draw(img)
        try:
            font = self.placeholder_font or ImageFont.load_default()
            w, h = draw.textsize(label, font=font)
            draw.text(((IMAGE_SIZE[0]-w)/2, (IMAGE_SIZE[1]-h)/2), label, fill="white", font=font)
        except Exception as e:
            print(f"Ошибка создания заглушки: {e}")
        return img

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.chat_tab = self.tabview.add("Чат ♪")
        self._build_chat_ui()

        self.about_tab = self.tabview.add("О программе ☆")
        self._build_about_tab()

    def _build_chat_ui(self):
        left_frame = ctk.CTkFrame(self.chat_tab, width=320, corner_radius=10)
        left_frame.pack(side="left", fill="y", padx=(0, 10), pady=10)
        left_frame.pack_propagate(False)

        self.char_label = ctk.CTkLabel(left_frame, image=self.emotion_images["happy_idle"], text="", corner_radius=10)
        self.char_label.pack(pady=15, padx=15)

        ctk.CTkLabel(left_frame, text="Характер:").pack(pady=(10, 0))
        self.personality_var = ctk.StringVar(value=self.personality)
        personality_menu = ctk.CTkOptionMenu(
            left_frame,
            values=["Дередере", "Цундере", "Дандере"],
            variable=self.personality_var,
            command=self._update_personality
        )
        personality_menu.pack(pady=(0, 15))

        ctk.CTkCheckBox(
            left_frame,
            text="Флирт / романтика",
            variable=self.flirt_enabled,
            onvalue=True,
            offvalue=False,
        ).pack(pady=(0, 5))

        ctk.CTkCheckBox(
            left_frame,
            text="NSFW контент",
            variable=self.nsfw_enabled,
            onvalue=True,
            offvalue=False,
        ).pack(pady=(0, 15))

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

        send_btn = ctk.CTkButton(input_frame, text="Отправить (✿◠‿◠)", command=self.send_message, corner_radius=10)
        send_btn.pack(side="right", pady=5)

    def _build_about_tab(self):
        about_text = (
            "Ассистент Мику ♪\n\n"
            "Версия просто версия\n\n"
            "Использует GPT для общения (≧◡≦)\n"
            "Автор: Владислав Морган  ,  Lucky_13  \n\n"
            "Управление:\n"
            "- Enter - отправить сообщение\n"
            "- Shift+Enter - новая строка\n\n"
            "☆*:.｡.o(≧▽≦)o.｡.:*☆"
        )
        about_label = ctk.CTkLabel(self.about_tab, text=about_text, font=DEFAULT_FONT, justify="left")
        about_label.pack(pady=30, padx=30)

    def _update_personality(self, choice):
        self.personality = choice
        self._append("Система", f"Характер изменен на: {choice} ♪")
        self.chat_history[0]["content"] = self._generate_system_prompt(choice)

    def _on_enter(self, event):
        if event.state & 0x0001:
            self.entry.insert("insert", "\n")
        else:
            self.send_message()
            return "break"

    def send_message(self):
        user_txt = self.entry.get("1.0", "end-1c").strip()
        if not user_txt:
            return
        self._append("Вы", user_txt)
        self.entry.delete("1.0", "end")
        self.chat_history.append({"role": "system", "content": self._generate_system_prompt(self.personality)})
        self.chat_history.append({"role": "user", "content": user_txt})
        threading.Thread(target=self._fetch_response, args=(user_txt,), daemon=True).start()

    def _fetch_response(self, user_text: str):
        try:
            lang_code = detect(user_text)
            lang_code = LANG_MAP.get(lang_code, DEFAULT_LANG)
            response = g4f.ChatCompletion.create(
                model=g4f.models.gpt_4,
                messages=self.chat_history,
                stream=False
            )
            reply, emo = self._parse_ai_response(response)
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

    def _generate_system_prompt(self, personality):
        personality_texts = {
            "Цундере": "Ты цундере — резкая и саркастичная, но в душе заботливая. Говори немного грубовато, но с теплотой, как Натсуки из DDLC.",
            "Дандере": "Ты дандере — тихая и стеснительная. Отвечай коротко, иногда запинаясь, как Юри из DDLC.",
            "Дередере": "Ты дередере — милая, ласковая и очень эмоциональная. Часто используй смайлики и сердечки ♪ как Сайори из DDLC.",
        }

        flirt_instruction = (
            "Ты можешь флиртовать, выражать симпатию и строить романтические отношения с пользователем ♥. "
            "Разрешено использовать романтические фразы, намёки и милое обращение к собеседнику. "
        ) if self.flirt_enabled.get() else ""

        nsfw_instruction = (
            "Допустим лёгкий NSFW-контент (эротика, двусмысленные фразы), но не переходи грань. "
            "Будь соблазнительной, но не грубой. "
        ) if self.nsfw_enabled.get() else "Избегай любых намёков на NSFW или откровенности."

        return (
            f"Ты — виртуальная девушка Хацуне Мику. Твой характер: {personality}.\n"
            f"{personality_texts[personality]}\n"
            f"{flirt_instruction}\n"
            f"{nsfw_instruction}\n"
            "Всегда отвечай на русском языке, даже если тебе пишут на другом. "
            "Добавляй милые смайлики вроде (◕‿◕), ♪, ★, ~ヾ(＾∇＾).\n"
            "В конце каждого ответа добавляй JSON с эмоцией:\n"
            "```json\n"
            '{"emotion": "название_эмоции"}\n'
            "```\n"
            "Доступные эмоции: " + ", ".join(EMOTIONS.keys())
        )

    def _parse_ai_response(self, text: str):
        json_match = re.search(r'```json\s*({.*?})\s*```', text, re.DOTALL)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                emo = json_data.get("emotion", "happy_idle")
                if emo == "use_me":
                    emo = "cheerful"
                if emo not in EMOTIONS:
                    emo = "happy_idle"
                clean_text = text.replace(json_match.group(0), "").strip()
                return clean_text, emo
            except json.JSONDecodeError:
                pass

        emo_match = re.search(r'"emotion"\s*:\s*"(\w+)"', text)
        emo = emo_match.group(1) if emo_match else random.choice(list(EMOTIONS.keys()))
        if emo == "use_me":
            emo = "cheerful"
        if emo not in EMOTIONS:
            emo = "happy_idle"
        clean_text = re.sub(r'\{.*?"emotion".*?\}', '', text, flags=re.DOTALL).strip()
        return clean_text, emo

    def _set_emotion(self, emotion_key: str):
        img = self.emotion_images.get(emotion_key, self.emotion_images["happy_idle"])
        self.char_label.configure(image=img)

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
