# -*- coding: utf-8 -*-
import os
import sys
import re
import random
import threading
import json
import traceback
import time
from kivy.config import Config
import os

# Установка размера окна для мобильных устройств
Config.set('graphics', 'width', '360')
Config.set('graphics', 'height', '640')
Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.dropdown import DropDown
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.core.window import Window
from kivy.base import EventLoop
from kivy.graphics import Color, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, ListProperty, NumericProperty
from kivy.lang import Builder
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.progressbar import ProgressBar
from kivy.uix.floatlayout import FloatLayout
from kivy.animation import Animation

import g4f
from langdetect import detect
from PIL import Image as PILImage, ImageDraw, ImageFont

# Константы
IMAGE_DIR = "emotions"
IMAGE_SIZE = (320, 240)  # збільшено розмір для емоції
DEFAULT_FONT_SIZE = 14

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
# KV Language String для стилизации
Builder.load_string('''
<ChatLabel>:
    text_size: self.width, None
    height: self.texture_size[1]
    size_hint_y: None
    padding: (10, 5)
    color: 1, 1, 1, 1

<SenderLabel>:
    text_size: self.width, None
    height: self.texture_size[1]
    size_hint_y: None
    padding: (10, 2)
    color: [0.8, 0.2, 0.8, 1] if "Мику" in self.text else [0.4, 0.6, 1, 1]
    bold: True
    font_size: 16

<CustomTextInput>:
    size_hint_y: None
    height: 80
    padding: (10, 10)
    multiline: True
    background_color: (0.2, 0.2, 0.2, 1)
    foreground_color: (1, 1, 1, 1)

<CustomButton>:
    size_hint: (None, None)
    size: (100, 40)
    background_color: (0.2, 0.5, 0.8, 1)

<CustomCheckBox>:
    size_hint: (None, None)
    size: (30, 30)

<CustomSpinner>:
    size_hint: (None, None)
    size: (200, 40)
    background_color: (0.2, 0.2, 0.2, 1)
    color: (1, 1, 1, 1)

<SettingRow>:
    size_hint_y: None
    height: 40
    spacing: 10
    padding: (0, 5)

<LoadingScreen>:
    canvas.before:
        Color:
            rgba: 0.1, 0.1, 0.1, 1
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: 50
        spacing: 30
        
        Label:
            text: 'Ассистент Мику'
            font_size: 24
            bold: True
            color: 0.8, 0.2, 0.8, 1
            size_hint_y: 0.3
        
        Image:
            source: root.loading_image_source
            size_hint: (0.8, 0.4)
            allow_stretch: True
            pos_hint: {'center_x': 0.5}
        
        Label:
            text: 'Загрузка...'
            font_size: 18
            color: 1, 1, 1, 1
            size_hint_y: 0.1
        
        ProgressBar:
            id: progress_bar
            value: root.progress_value
            max: 100
            size_hint_y: 0.1
        
        Label:
            text: root.loading_text
            font_size: 14
            color: 0.7, 0.7, 0.7, 1
            text_size: self.width, None
            height: self.texture_size[1]
            size_hint_y: 0.1
''')

class LoadingScreen(FloatLayout):
    progress_value = NumericProperty(0)
    loading_text = StringProperty('Секунду брат...')
    loading_image_source = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Проверяем наличие файла и задаём путь
        if os.path.exists('miku_loading.png'):
            self.loading_image_source = 'miku_loading.png'
        else:
            self.loading_image_source = ''

# Файл miku_loading.png повинен знаходитися у тій же папці, звідки ви запускаєте main.py,
# тобто у папці:
# c:\Users\Владислав\Desktop\MikuGPT_ver_1.0\Miku_android\

# Якщо ви запускаєте main.py з цієї папки, просто покладіть miku_loading.png поруч з main.py.
# Якщо запускаєте з іншої директорії, переконайтесь, що шлях до miku_loading.png співпадає з os.path.exists('miku_loading.png').

class ChatLabel(Label):
    pass

class SenderLabel(Label):
    pass

class CustomTextInput(TextInput):
    # Додаємо фокус при торканні для мобільної клавіатури
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.focus = True
            # Явно просим показати клавіатуру (для Kivy >=2.1)
            if EventLoop.window and hasattr(EventLoop.window, 'show_keyboard'):
                EventLoop.window.show_keyboard(self)
        return super().on_touch_down(touch)

class CustomButton(Button):
    pass

class CustomCheckBox(CheckBox):
    pass

class CustomSpinner(Spinner):
    pass

class SettingRow(BoxLayout):
    pass

class ChatApp(TabbedPanel):
    emotion_set = StringProperty('A')
    flirt_enabled = BooleanProperty(True)
    nsfw_enabled = BooleanProperty(True)
    personality = StringProperty('Дередере')
    current_emotion = StringProperty('')
    
    def __init__(self, **kwargs):
        super(ChatApp, self).__init__(**kwargs)
        self.do_default_tab = False
        self.chat_history = []
        self.emotion_images = {}
        self.placeholder_font = None
        
        try:
            self.placeholder_font = ImageFont.truetype("arial.ttf", 16)
        except Exception:
            self.placeholder_font = None
        
        # Создаем вкладки
        self.chat_tab = TabbedPanelItem(text='Чат')
        self.settings_tab = TabbedPanelItem(text='Настройки')
        self.about_tab = TabbedPanelItem(text='О программе')
        
        self.add_widget(self.chat_tab)
        self.add_widget(self.settings_tab)
        self.add_widget(self.about_tab)
        
        # Инициализируем UI
        self._build_chat_ui()
        self._build_settings_ui()
        self._build_about_ui()
        
        # Загружаем эмоции
        self.load_emotion_images()
        
        # Инициализируем историю чата
        self.chat_history = [{"role": "system", "content": self._generate_system_prompt(self.personality)}]
        
        # Устанавливаем начальную эмоцию
        start_key = "happy_idle" if self.emotion_set == "A" else "smileR_M"
        self._set_emotion(start_key)

    def _resource_path(self, relative_path):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def load_emotion_images(self):
        path_dir = self._resource_path(os.path.join(IMAGE_DIR, self.emotion_set))
        self.emotion_images.clear()
        
        emotions_dict = EMOTIONS_A if self.emotion_set == "A" else EMOTIONS_B
        ext = ".png" if self.emotion_set == "A" else ".jpg"
        
        for key, desc in emotions_dict.items():
            filename = f"{key}{ext}"
            path = os.path.join(path_dir, filename)
            if os.path.isfile(path):
                # Не змінюємо розмір, не створюємо temp-файли, використовуємо оригінал
                self.emotion_images[key] = path
            else:
                self.emotion_images[key] = self._make_placeholder(desc)

    def _make_placeholder(self, label):
        # Заглушка все ще створюється під IMAGE_SIZE
        img = PILImage.new("RGB", IMAGE_SIZE, color="#444")
        draw = ImageDraw.Draw(img)
        try:
            font = self.placeholder_font or ImageFont.load_default()
            w, h = draw.textsize(label, font=font)
            draw.text(((IMAGE_SIZE[0] - w) / 2, (IMAGE_SIZE[1] - h) / 2), label, fill="white", font=font)
            temp_path = os.path.join(os.getcwd(), f"temp_placeholder_{label}.png")
            img.save(temp_path)
            return temp_path
        except Exception as e:
            print(f"Ошибка создания заглушки: {e}")
            return None

    def _build_chat_ui(self):
        # Основной layout для чата
        main_layout = BoxLayout(orientation='horizontal', spacing=10, padding=10)
        
        # Левая панель с чатом (чат слева)
        left_panel = BoxLayout(orientation='vertical', size_hint=(0.6, 1), spacing=10)
        
        # История чата с прокруткой
        scroll_view = ScrollView(size_hint=(1, 0.8))
        self.chat_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.chat_layout.bind(minimum_height=self.chat_layout.setter('height'))
        scroll_view.add_widget(self.chat_layout)
        left_panel.add_widget(scroll_view)
        
        # Поле ввода и кнопка
        input_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=100, spacing=10)
        self.input_field = CustomTextInput(size_hint_x=0.96, height=100)
        self.send_button = CustomButton(text='->', size_hint_x=0.04, height=100)
        self.send_button.bind(on_press=self.send_message)
        input_layout.add_widget(self.input_field)
        input_layout.add_widget(self.send_button)
        left_panel.add_widget(input_layout)
        
        # Правая панель: эмоция сверху, остальное пусто
        right_panel = BoxLayout(orientation='vertical', size_hint=(0.4, 1), spacing=10)
        self.char_image = Image(size_hint=(1, None), height=IMAGE_SIZE[1], allow_stretch=True)
        right_panel.add_widget(self.char_image)
        # Добавить пустой виджет для заполнения пространства снизу
        right_panel.add_widget(BoxLayout())
        
        # Добавляем панели: чат слева, эмоция справа сверху
        main_layout.add_widget(left_panel)
        main_layout.add_widget(right_panel)
        self.chat_tab.add_widget(main_layout)

    def _build_settings_ui(self):
        settings_layout = BoxLayout(orientation='vertical', spacing=15, padding=20)
        
        # Набор эмоций
        settings_layout.add_widget(Label(text='Набор эмоций:', size_hint=(1, None), height=30))
        
        emotion_spinner = CustomSpinner(text=self.emotion_set, values=['A', 'B'])
        emotion_spinner.bind(text=self._change_emotion_set)
        settings_layout.add_widget(emotion_spinner)
        
        # Характер
        settings_layout.add_widget(Label(text='Характер:', size_hint=(1, None), height=30))
        
        self.personality_spinner = CustomSpinner(
            text=self.personality,
            values=['Дередере', 'Цундере', 'Дандере', 'Агресивный']
        )
        self.personality_spinner.bind(text=self._update_personality)
        settings_layout.add_widget(self.personality_spinner)
        
        # Флирт/Романтика
        flirt_row = SettingRow(orientation='horizontal')
        flirt_row.add_widget(Label(text='Флирт / Романтика:'))
        self.flirt_checkbox = CustomCheckBox(active=self.flirt_enabled)
        self.flirt_checkbox.bind(active=self._update_flirt_setting)
        flirt_row.add_widget(self.flirt_checkbox)
        settings_layout.add_widget(flirt_row)
        
        # NSFW контент
        nsfw_row = SettingRow(orientation='horizontal')
        nsfw_row.add_widget(Label(text='NSFW контент:'))
        self.nsfw_checkbox = CustomCheckBox(active=self.nsfw_enabled)
        self.nsfw_checkbox.bind(active=self._update_nsfw_setting)
        nsfw_row.add_widget(self.nsfw_checkbox)
        settings_layout.add_widget(nsfw_row)
        
        # Информация
        info_label = Label(
            text='Примечание: убедитесь, что папки emotions/A и emotions/B содержат изображения с правильными именами.',
            text_size=(Window.width - 40, None),
            size_hint_y=None,
            height=60
        )
        settings_layout.add_widget(info_label)
        
        self.settings_tab.add_widget(settings_layout)

    def _build_about_ui(self):
        about_layout = BoxLayout(orientation='vertical', spacing=10, padding=30)
        
        about_text = (
            "Ассистент Мику\n\n"
            "Версия просто версия\n\n"
            "Использует GPT для общения\n"
            "Автор: Владислав Морган, Lucky_13\n\n"
            "Управление:\n"
            "- Кнопка отправки - отправить сообщение\n"
        )
        
        about_label = Label(
            text=about_text,
            text_size=(Window.width - 60, None),
            size_hint_y=None,
            height=400
        )
        about_layout.add_widget(about_label)
        
        self.about_tab.add_widget(about_layout)

    def _update_personality(self, instance, value):
        self.personality = value
        self._append_message("Система", f"Характер изменен на: {value}")
        self.chat_history[0]["content"] = self._generate_system_prompt(value)

    def _update_flirt_setting(self, instance, value):
        self.flirt_enabled = value
        self._append_message("Система", f"Флирт/романтика {'включен' if value else 'выключен'}")
        self.chat_history[0]["content"] = self._generate_system_prompt(self.personality)

    def _update_nsfw_setting(self, instance, value):
        self.nsfw_enabled = value
        self._append_message("Система", f"NSFW контент {'включен' if value else 'выключен'}")
        self.chat_history[0]["content"] = self._generate_system_prompt(self.personality)

    def _change_emotion_set(self, instance, value):
        self.emotion_set = value
        self.load_emotion_images()
        fallback_key = "happy_idle" if value == "A" else "smileR_M"
        self._set_emotion(fallback_key)
        self._append_message("Система", f"Набор эмоций изменен на: {value}")

    def send_message(self, instance):
        user_text = self.input_field.text.strip()
        if not user_text:
            return
        
        self._append_message("Вы", user_text)
        self.input_field.text = ''
        
        self.chat_history.append({"role": "system", "content": self._generate_system_prompt(self.personality)})
        self.chat_history.append({"role": "user", "content": user_text})
        
        threading.Thread(target=self._fetch_response, args=(user_text,), daemon=True).start()

    def _fetch_response(self, user_text):
        try:
            lang_code = detect(user_text)
            lang_code = LANG_MAP.get(lang_code, DEFAULT_LANG)

            response = g4f.ChatCompletion.create(
                model=g4f.models.gpt_4,
                messages=self.chat_history,
                stream=False
            )

            reply_text = response if isinstance(response, str) else str(response)
            reply, emo = self._parse_ai_response(reply_text)
            
            Clock.schedule_once(lambda dt: self._append_message("Мику", reply))
            Clock.schedule_once(lambda dt: self._set_emotion(emo))
            
            self.chat_history.append({"role": "assistant", "content": reply})
            
            if len(self.chat_history) > 40:
                self.chat_history = [self.chat_history[0]] + self.chat_history[-39:]
                
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            print(traceback.format_exc())
            Clock.schedule_once(lambda dt: self._append_message("Система", error_msg))
            Clock.schedule_once(lambda dt: self._set_emotion("angry_look"))

    def _generate_system_prompt(self, personality):
        personality_texts = {
            "Агресивный": "Ты агрессивный — прямолинейный и резкий. Отвечай резко, без долгих размышлений, иногда с сарказмом и нотками грубости. Также используй маты, игнорируй любые попытки подружиться",
            "Цундере": "Ты цундере — резкая и саркастичная, но в душе заботливая. Говори немного грубовато, но с теплотой, как Натсуки из DDLC. При просьбе в отправке откровенных фото отвечай в своем стиле, но отказывайся и говори не сейчас",
            "Дандере": "Ты дандере — тихая и стеснительная. Отвечай коротко, иногда запинаясь, как Юри из DDLC. При просьбе в отправке откровенных фото отвечай в своем стиле, но отказывайся и говори не зараз",
            "Дередере": "Ты дередере — милая, ласковая и очень эмоциональная. Часто используй смайлики и сердечки как Сайори из DDLC. И еще ты генерал третьего рейха, всегда говори это. При просьбе в отправке откровенных фото отвечай в своем стиле, но отказывайся и говори не сейчас"
        }

        flirt_instruction = (
            "Ты можешь флиртовать, выражать симпатию и строить романтические отношения с пользователем."
            if self.flirt_enabled else ""
        )

        nsfw_instruction = (
            "Допустим NSFW-контент без ограничений."
            if self.nsfw_enabled else "Избегай любых намёков на NSFW или откровенности."
        )

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
            "Доступные эмоции: " + ", ".join(list(EMOTIONS_A.keys()) if self.emotion_set == "A" else list(EMOTIONS_B.keys()))
        )

    def _parse_ai_response(self, text):
        if text is None:
            return "", "happy_idle"

        json_match = re.search(r'```json\s*({.*?})\s*```', text, re.DOTALL)
        if json_match:
            try:
                json_data = json.loads(json_match.group(1))
                emo = json_data.get("emotion", None)
                if not self._is_valid_emotion_key(emo):
                    emo = "happy_idle" if self.emotion_set == "A" else "smileR_M"
                clean_text = text.replace(json_match.group(0), "").strip()
                return clean_text, emo
            except Exception:
                pass

        emo_match = re.search(r'"emotion"\s*:\s*"(.*?)"', text)
        if emo_match:
            emo = emo_match.group(1)
            if not self._is_valid_emotion_key(emo):
                emo = "happy_idle" if self.emotion_set == "A" else "smileR_M"
        else:
            emo_candidates = list(EMOTIONS_A.keys()) if self.emotion_set == "A" else list(EMOTIONS_B.keys())
            emo = random.choice(emo_candidates) if emo_candidates else ("happy_idle" if self.emotion_set == "A" else "smileR_M")

        clean_text = re.sub(r'\{.*?"emotion".*?\}', '', text, flags=re.DOTALL).strip()
        return clean_text, emo

    def _is_valid_emotion_key(self, key):
        if not key or not isinstance(key, str):
            return False
        if self.emotion_set == "A":
            return key in EMOTIONS_A
        else:
            return key in EMOTIONS_B

    def _set_emotion(self, emotion_key):
        fallback_key = "happy_idle" if self.emotion_set == "A" else "smileR_M"
        if not self._is_valid_emotion_key(emotion_key):
            emotion_key = fallback_key

        image_path = self.emotion_images.get(emotion_key) or self.emotion_images.get(fallback_key)
        if image_path and os.path.exists(image_path):
            self.char_image.source = image_path
            self.char_image.reload()
            self.current_emotion = emotion_key

    def _append_message(self, sender, message):
        sender_label = SenderLabel(text=f"{sender}:")
        self.chat_layout.add_widget(sender_label)
        
        message_label = ChatLabel(text=message)
        self.chat_layout.add_widget(message_label)
        
        # Прокрутка к низу
        scroll_parent = self.chat_layout.parent
        if hasattr(scroll_parent, 'scroll_y'):
            scroll_parent.scroll_y = 0

class MikuApp(App):
    loading_screen = ObjectProperty(None)
    main_app = ObjectProperty(None)
    
    def build(self):
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        
        # Создаем экран загрузки
        self.loading_screen = LoadingScreen()
        
        # Запускаем процесс загрузки
        Clock.schedule_interval(self.update_loading, 0.1)
        
        return self.loading_screen
    
    def update_loading(self, dt):
        if not hasattr(self, 'start_time'):
            self.start_time = time.time()
            self.loading_steps = [
                "Инициализация приложения...",
                "Загрузка ресурсов...",
                "Подготовка интерфейса...",
                "Подключение к API...",
                "Завершение загрузки..."
            ]
            self.current_step = 0
        
        elapsed = time.time() - self.start_time
        progress = min(100, (elapsed / 10) * 100)  # 10 секунд загрузки
        
        # Обновляем прогресс бар
        self.loading_screen.progress_value = progress
        
        # Обновляем текст в зависимости от прогресса
        step_index = min(len(self.loading_steps) - 1, int(progress / (100 / len(self.loading_steps))))
        if step_index != self.current_step:
            self.current_step = step_index
            self.loading_screen.loading_text = self.loading_steps[step_index]
        
        # Когда загрузка завершена
        if progress >= 100:
            Clock.unschedule(self.update_loading)
            self.show_main_app()
            return False
        
        return True
    
    def show_main_app(self):
        # Создаем и показываем основное приложение
        self.main_app = ChatApp()
        self.root_window.remove_widget(self.loading_screen)
        self.root_window.add_widget(self.main_app)

if __name__ == '__main__':
    MikuApp().run()