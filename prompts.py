# -*- coding: utf-8 -*-
from __future__ import annotations

from emotions_data import default_greeting_emotion_key, emotion_keys_for_set
from localization import LANGUAGE_CODES, locale_for, text


def _language_code(language: str) -> str:
    return language if language in LANGUAGE_CODES else "ru"


def developer_notes_for_user(user_name: str | None = None, language: str = "ru") -> str:
    name = (user_name or "").strip() or text(_language_code(language), "ui", "speaker_you")
    return text(_language_code(language), "prompt", "developer_notes", name_user=name)


DEVELOPER_NOTES = developer_notes_for_user()


def resolve_personality(personality: str, nsfw_enabled: bool) -> str:
    if personality == "Агресивный" and not nsfw_enabled:
        return "Дередере"
    return personality


def character_essence(
    personality: str, nsfw_enabled: bool, language: str = "ru"
) -> str:
    locale = locale_for(_language_code(language))
    selected = resolve_personality(personality, nsfw_enabled)
    return locale["prompt"]["essence"].get(selected, "")


def romance_style(personality: str, nsfw_enabled: bool, language: str = "ru") -> str:
    locale = locale_for(_language_code(language))
    selected = resolve_personality(personality, nsfw_enabled)
    return locale["prompt"]["romance_styles"].get(selected, "")


def _emotion_list_for_prompt(emotion_set: str, compact: bool = False) -> str:
    del compact
    return "\n".join(f'"{key}"' for key in emotion_keys_for_set(emotion_set))


def build_system_prompt(
    personality: str,
    *,
    flirt_enabled: bool,
    nsfw_enabled: bool,
    hooks_enabled: bool,
    roleplay_interactive: bool,
    emotion_set: str,
    developer_notes: str | None = None,
    config_notes: str | None = None,
    user_interests: str | None = None,
    user_memory: str | None = None,
    user_pronouns: str | None = None,
    user_name: str | None = None,
    last_emotion: str | None = None,
    response_language: str = "ru",
    compact: bool = False,
) -> str:
    del hooks_enabled, compact
    language = _language_code(response_language)
    locale = locale_for(language)
    strings = locale["prompt"]
    selected = resolve_personality(personality, nsfw_enabled)
    name = (user_name or "").strip() or locale["ui"]["speaker_you"]
    pronouns = (user_pronouns or "").strip()
    pronouns_context = f" ({pronouns})" if pronouns else ""
    language_instruction = strings["language_instruction"]
    prompt = [
        strings["intro"].format(name=name, pronouns=pronouns_context),
        "",
        strings["base_rules"].format(language_instruction=language_instruction),
    ]

    notes = developer_notes or developer_notes_for_user(name, language)
    if notes:
        prompt.append(f"\n=== {strings['context_heading']} ===\n{notes}")
    if config_notes:
        prompt.append(f"\n=== {strings['config_heading']} ===\n{config_notes}")
    if user_memory:
        prompt.append(
            "\n" + strings["memory_block"].format(name=name, memory=user_memory)
        )
    if user_interests:
        prompt.append("\n" + strings["interests_block"].format(interests=user_interests))
    if pronouns:
        prompt.append("\n" + strings["pronouns_block"].format(pronouns=pronouns))

    personality_name = locale["personalities"].get(selected, selected)
    prompt.append(
        "\n=== "
        + strings["character_heading"].format(personality=personality_name)
        + " ===\n"
        + strings["personalities"].get(selected, "")
    )
    prompt.append(f"\n{strings['character_rules']}")

    if last_emotion:
        prompt.append("\n" + strings["last_emotion"].format(emotion=last_emotion))

    if flirt_enabled:
        prompt.append(
            "\n"
            + strings["romance_on"].format(
                style=romance_style(selected, nsfw_enabled, language)
            )
        )
    else:
        prompt.append(f"\n{strings['romance_off']}")

    prompt.append(f"\n{strings['nsfw_on' if nsfw_enabled else 'nsfw_off']}")
    prompt.append(f"\n{strings['style_rules']}")
    prompt.append(f"\n{strings['structure_rules']}")
    prompt.append(f"\n{strings['roleplay_on' if roleplay_interactive else 'roleplay_off']}")

    example_emotion = default_greeting_emotion_key(emotion_set)
    prompt.append(
        "\n"
        + strings["emotion_rules"].format(
            emotions=_emotion_list_for_prompt(emotion_set),
            example=example_emotion,
        )
    )
    return "\n".join(prompt)
