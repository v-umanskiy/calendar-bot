import json

from src.utils import logging_utils
from src.utils.constants import CLASSIFIER_CATEGORIES


def parse_classifier_response(raw_response: str) -> str:
    safe_response = raw_response or ""
    candidate_json = extract_json_from_response(safe_response)
    try:
        payload = json.loads(candidate_json)
    except json.JSONDecodeError:
        logging_utils.log_prefixed_message(
            "CLASSIFY_PARSE_ERROR",
            safe_response,
        )
        return "other"

    category = str(payload.get("category", "")).lower()
    if category not in CLASSIFIER_CATEGORIES:
        return "other"
    return category


def extract_json_from_response(response: str) -> str:
    stripped = response.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            content_lines = lines[1:-1]
            stripped = "\n".join(content_lines).strip()
    return stripped
