from src.utils.constants import (
    CAPABILITIES_DOCUMENT,
    LIMITATION_PROMPT_TEMPLATE,
)


def build_capability_limitation_prompt(
    user_message: str,
    limitation_reason: str,
) -> str:
    return LIMITATION_PROMPT_TEMPLATE.format(
        document=CAPABILITIES_DOCUMENT,
        message=(user_message or "").strip(),
        limitation=limitation_reason,
    )
