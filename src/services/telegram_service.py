import httpx
from . import secret_service
from src.utils import util, logging_utils

TELEGRAM_BOT_TOKEN = secret_service.get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"


async def send_message(chat_id: int, text: str):
    html_text = util.to_html(text)
    chunks = util.split_html_message(html_text)
    return await _send_message_chunks(chat_id, chunks)


async def send_message_with_reply_markup(chat_id: int, text: str, reply_markup: dict):
    html_text = util.to_html(text)
    chunks = [html_text]
    return await _send_message_chunks(chat_id, chunks, reply_markup)


async def _send_message_chunks(chat_id: int, chunks: list[str], reply_markup: dict | None = None):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    last_result = None

    async with httpx.AsyncClient(timeout=10) as client:
        for idx, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup

            try:
                response = await client.post(url, json=payload)
                logging_utils.log_http_result("SEND_MESSAGE", response)
                if not response.is_success:
                    return None
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        last_result = body.get("result")
                except Exception:
                    last_result = None
            except Exception as e:
                print("SEND_MESSAGE_ERROR:", repr(e))
                return None
    return last_result


async def answer_callback_query(callback_query_id: str):
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            logging_utils.log_http_result("ANSWER_CALLBACK_QUERY", response)
        except Exception as e:
            print("ANSWER_CALLBACK_QUERY_ERROR:", repr(e))
            return


async def clear_message_reply_markup(chat_id: int, message_id: int):
    url = f"{TELEGRAM_API_URL}/editMessageReplyMarkup"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": {"inline_keyboard": []},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            logging_utils.log_http_result("EDIT_MESSAGE_REPLY_MARKUP", response)
        except Exception as e:
            print("EDIT_MESSAGE_REPLY_MARKUP_ERROR:", repr(e))
            return


async def send_chat_action(chat_id: int, action: str = "typing"):
    url = f"{TELEGRAM_API_URL}/sendChatAction"
    payload = {"chat_id": chat_id, "action": action}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload)
            logging_utils.log_http_result("SEND_CHAT_ACTION", response)
        except Exception as e:
            print("SEND_CHAT_ACTION_ERROR:", repr(e))
            return
        

async def download_file_from_telegram(file_id: str):
    async with httpx.AsyncClient(timeout=10) as client:
        file_path = await _get_telegram_file_path(client, file_id)
        if not file_path:
            return None

        return await _download_telegram_file(client, file_path)


async def _get_telegram_file_path(client: httpx.AsyncClient, file_id: str) -> str | None:
    url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
    try:
        response = await client.get(url)
    except Exception as exc:
        print("TELEGRAM_GET_FILE_ERROR:", repr(exc))
        return None

    if not response.is_success:
        logging_utils.log_http_result("TELEGRAM_GET_FILE", response)
        return None

    try:
        payload = response.json()
    except Exception as exc:
        print("TELEGRAM_GET_FILE_JSON_ERROR:", repr(exc))
        return None

    if not payload.get("ok"):
        logging_utils.log_prefixed_message_full("Error getting file path from Telegram", payload)
        return None

    return payload["result"]["file_path"]


async def _download_telegram_file(client: httpx.AsyncClient, file_path: str) -> bytes | None:
    url = f"{TELEGRAM_FILE_URL}/{file_path}"
    try:
        response = await client.get(url)
    except Exception as exc:
        print("TELEGRAM_FILE_DOWNLOAD_ERROR:", repr(exc))
        return None

    if not response.is_success:
        logging_utils.log_http_result("TELEGRAM_FILE_DOWNLOAD", response)
        return None

    return response.content
