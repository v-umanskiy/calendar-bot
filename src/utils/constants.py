import os


def _get_bool_env(var_name: str) -> bool:
    value = os.getenv(var_name)
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized == "true"


DOCUMENT_LANGUAGE = os.getenv("DOCUMENT_LANGUAGE", "English").strip() or "English"
MESSAGE_CATEGORIZATION_ENABLED = _get_bool_env("ENABLE_MESSAGE_CATEGORIZATION")


TRANSCRIBED_VOICE_PROMPT_TEMPLATE = (
    "You are continuing a chat with the user. "
    "The next message was transcribed from a voice note and may contain "
    "speech-recognition mistakes. Respond directly to the user, be forgiving of "
    "possible errors, and ask for clarification only if meaning is unclear.\n\n"
    "User (transcribed):\n{message}"
)


WELCOME_MESSAGE = (
    "👋 Welcome! I’m your assistant bot.\n\n"
    "You can send me text, voice messages, or photos, and I’ll help you out.\n\n"
    "⏱ Please be patient. I currently take around 10 seconds to process text or photos, "
    "and around 30 seconds to process a voice message.\n\n"
    "Your messages are stored in a database. We don't forward them to any parties but Google Gemini, AWS Transcribe."
)


MODEL_PROVIDER_LIMIT_REACHED_MESSAGE = (
    "We've hit the current AI usage limit. It is expected during the test phase. Let's try again tomorrow."
)


MODEL_PROVIDER_UNAVAILABLE_MESSAGE = (
    "I ran into an issue talking to the AI service. Let's try again in a moment."
)


CLEAR_HISTORY_MESSAGE = (
    "Are you sure you want to clear the bot's history? You will still see the messages in Telegram, "
    "but the bot will forget them."
)


HISTORY_CLEARED_MESSAGE = "Got it, the bot's history has been cleared."


CLEAR_HISTORY_CONFIRM_CALLBACK_DATA = "clear_history_confirm_yes"
CLEAR_HISTORY_CANCEL_CALLBACK_DATA = "clear_history_confirm_cancel"


CLEAR_HISTORY_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "Yes", "callback_data": CLEAR_HISTORY_CONFIRM_CALLBACK_DATA}],
        [{"text": "Cancel", "callback_data": CLEAR_HISTORY_CANCEL_CALLBACK_DATA}],
    ]
}


CLASSIFIER_CATEGORIES = (
    "image_generation_request",
    "latest_news_request",
    "other",
)
_CLASSIFIER_CATEGORY_LABELS = ", ".join(f'"{category}"' for category in CLASSIFIER_CATEGORIES)


CLASSIFICATION_PROMPT_TEMPLATE = (
    "You are classifying Telegram messages for a custom assistant bot. "
    "Categorize the user's latest message into exactly one of these values: "
    f"{_CLASSIFIER_CATEGORY_LABELS}. "
    "Interpret 'image_generation_request' as the user asking for an image to be created or edited. "
    "Interpret 'latest_news_request' as the user asking for live updates, current events, actual weather, "
    "time or browsing the internet. Respond with a compact JSON object of the form {\"category\": \"value\"}. "
    "Prefer 'other' if uncertain. Support any language, slang, and typos.\n\n"
    "User message:\n"
)


LIMITATION_PROMPT_TEMPLATE = (
    "You are a custom assistant for a Telegram bot, powered by Gemini. "
    "The user's latest request is outside your capabilities because: {limitation}. "
    "Using the capabilities document as your main source of truth, compose a concise "
    "reply that explains the limitation, offers any helpful alternatives, and keeps a "
    "friendly tone. Answer in the same language as the user when possible; otherwise, "
    "respond in English.\n\n"
    "Capabilities document (English):\n{document}\n\n"
    "User message:\n{message}\n\n"
)


CATEGORY_LIMITATION_REASONS = {
    "image_generation_request": (
        "You can describe or brainstorm image ideas, but you cannot generate or edit "
        "actual pictures because the assistant only produces text."
    ),
    "latest_news_request": (
        "You lack live internet or browsing access."
    ),
}


CAPABILITIES_DOCUMENT = (
    "This assistant is powered by Google Gemini to help with everyday conversations.\n"
    "It can explain topics, draft and translate text, and discuss the content of user-provided photos.\n"
    "It can also respond to short voice notes. It can NOT generate or edit images. It can respond only in a text form.\n"
    "Response to a text or a photo takes around 20 seconds, response to a voice note takes around 30 seconds.\n"
    "User's messages and assistant's responses are being stored on the developer's servers. User can get them deleted using the bot's \n"
    "menu in Telegram. They are also being forwarded to Google Gemini and being stored on Google's servers accordingly to \n"
    "Google's own policies.\n"
    "The assistant cannot browse the internet, fetch live weather, or process arbitrary file attachments beyond photos and short audio notes."
)
