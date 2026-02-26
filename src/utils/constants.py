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

GOOGLE_CONNECT_MESSAGE_TEMPLATE = (
    "Connect Google Calendar:\n{url}\n\n"
    "After authorization, return to this chat."
)


CLEAR_HISTORY_CONFIRM_CALLBACK_DATA = "clear_history_confirm_yes"
CLEAR_HISTORY_CANCEL_CALLBACK_DATA = "clear_history_confirm_cancel"


CLEAR_HISTORY_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "Yes", "callback_data": CLEAR_HISTORY_CONFIRM_CALLBACK_DATA}],
        [{"text": "Cancel", "callback_data": CLEAR_HISTORY_CANCEL_CALLBACK_DATA}],
    ]
}
