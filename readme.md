
<div align="center">
  <img src="LLK.png" alt="MikuGPT Logo" width="300"/>

  # 🎀 MikuGPT — Твоя Мику на ПК 🎀

  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-8B5CF6?style=for-the-badge&logo=tkinter&logoColor=white)](https://github.com/TomSchimansky/CustomTkinter)
  [![AI](https://img.shields.io/badge/AI-Local%20LLM-FF6B9D?style=for-the-badge&logo=python&logoColor=white)](https://llama.cpp)
  [![License](https://img.shields.io/badge/License-MIT-FFD93D?style=for-the-badge)](LICENSE)
  [![Download](https://img.shields.io/badge/Скачать-FF6B9D?style=for-the-badge&logo=github&logoColor=white)](https://github.com/vlad-abobus/MikuGPT0/releases)

</div>

---

## 🌸 О проекте

**MikuGPT** — это десктопный ИИ-чат с Хацунэ Мику. Она живёт у тебя на компьютере, реагирует с **эмоциями**, озвучивает ответы и запоминает твои предпочтения.

> 💬 *«Привет! Я Мику!»*

---

## 🌟 Возможности

| Иконка | Фича | Описание |
|:------:|:----:|:---------|
| 🎭 | **Эмоции** | Мику показывает 40+ эмоций — от смущения до агрессии. Поддерживает 3 набора (A / B / C) |
| 🎤 | **Голосовой ввод** | Говори в микрофон — Мику распознает и поймёт твою речь |
| 🔊 | **Озвучка (TTS)** | Читает ответы вслух своим голосом (Hugging Face + RVC) |
| 🧠 | **Память** | Запоминает твои интересы, факты и историю диалога |
| 💕 | **Романтика / NSFW** | Переключение режимов общения одной галочкой |
| 🎪 | **roleplay** | Отыгрыш действий и речи (*действие* + фраза), как в Character.AI |
| 🎛️ | **6 характеров** | Дередере, Цундере, Дандере, Яндере, Агрессивный, Уку-Мамадере |
| 🔥 | **Smart Memory** | Автоматически конспектирует диалог каждые N сообщений |
| 🖼️ | **Живые эмоции** | Изображение Мику меняется в реальном времени под настроение |
| 🌙 | **Тёмная тема** | Стильный и удобный GUI в тёмных тонах |

---

## 🖥️ Скриншоты

| Главный экран | Настройки |
|:-------------:|:---------:|
| *Чат с Мику, эмоции, голосовой ввод* | *Профиль, память, API, характер* |
| ![Главный экран](screen.PNG) | ![Настройки](screen2.PNG) |

---

## 🚀 Установка и запуск

### 📦 Готовая сборка (EXE)
1. Скачай последний релиз со страницы [Releases](https://github.com/vlad-abobus/MikuGPT0/releases).
2. Распакуй архив и запусти `main.exe`.

### 🐍 Из исходного кода

```bash
# 1. Клонируй репозиторий
git clone [https://github.com/vlad-abobus/MikuGPT0.git](https://github.com/vlad-abobus/MikuGPT0.git)
cd MikuGPT0

# 2. Создай и активируй виртуальное окружение
python -m venv venv

# Для Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Для Linux / macOS:
source venv/bin/activate

# 3. Установи зависимости
pip install -r requirements.txt

# 4. Запусти приложение
python main.py

```

---

## 🎮 Управление

| Элемент / Клавиша | Функция |
| --- | --- |
| `Enter` | Отправить сообщение |
| `Shift + Enter` | Перенос строки |
| 🎤 | Активация голосового ввода |
| 🎭 | Выбор набора эмоций (A / B / C) |
| 💕 | Переключение режима романтики |
| 🔞 | Переключение NSFW-режима |

---

## 🧩 Структура проекта

```text
MikuGPT0/
├── main.py             # 🖥️ GUI (CustomTkinter) и основная логика
├── ai_chat.py          # 🤖 Взаимодействие с LLM (локальная GGUF: D:\model\llm_model.gguf)
├── local_llm.py        # 🖥️ Локальная LLM (llama-cpp-python + CUDA, D:\model\llm_model.gguf)
├── prompts.py          # 📝 Системные промпты и характеры
├── emotions.json        # 🎭 Пресеты эмоций (наборы A/B/C: ключи, подписи, описания для промпта)
├── emotions_data.py    # 🎭 Загрузка эмоций из emotions.json (наборы A/B/C)
├── miku_tts.py         # 🔊 Модуль озвучки (RVC / Hugging Face)
├── voice_input.py      # 🎤 Модуль распознавания речи
├── paths.py            # 📂 Утилиты для работы с путями
├── app_logging.py      # 📋 Логирование ошибок и событий
├── config.json         # ⚙️ Пользовательская конфигурация
├── requirements.txt    # 📦 Зависимости Python
├── LLK.png             # 🖼️ Логотип приложения
├── icon.ico            # 🏷️ Иконка окна / EXE
├── build_exe.bat       # 🔨 Скрипт сборки PyInstaller
├── emotions/           # 🎭 Папки с графикой эмоций
│   ├── A/              #    19 эмоций (PNG)
│   ├── B/              #    9 эмоций (JPG)
│   └── C/              #    40+ эмоций (PNG)
└── dist/               # 📦 Папка готовой сборки

```

---

## 💖 Поддержать проект

Поддержите разработку — финансовая помощь идёт на оплату серверов и API ИИ-моделей:

* **Monobank:** [send.monobank.ua/jar/HTxkQ2n5w](https://send.monobank.ua/jar/HTxkQ2n5w?utm_source=gemini)

---

## 👨‍💻 Авторы

| Роль | Участник |
| --- | --- |
| 🎨 **Идея, дизайн, эмоции** | **Lucky_13** |
| 🛠️ **Код, архитектура, промпты** | **VladislavMorgan** |
| 👥 **Тестирование и фидбек** | **Community LK_13** |

---

## 📜 Лицензия

Проект распространяется под лицензией **MIT**. Подробности см. в файле [LICENSE](https://www.google.com/search?q=LICENSE&utm_source=gemini).

---

**★ Сделано с любовью специально для LK_13 ★**

MikuGPT © Community LK_13
