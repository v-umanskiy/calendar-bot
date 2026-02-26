from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse
from mangum import Mangum
import src.handlers.webhook_handler as webhook_handler
import src.services.secret_service as secret_service
from src.services import google_oauth_service

app = FastAPI()
handler = Mangum(app)

WEBHOOK_SECRET = secret_service.get_secret("WEBHOOK_SECRET")


@app.get("/")
def read_root():
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Bad secret")
    
    data = await request.json()
    print("Incoming update:", data)

    return await webhook_handler.handle_telegram_webhook_data(data)


@app.get("/oauth/callback", response_class=HTMLResponse)
async def google_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    status_code, html = await google_oauth_service.process_oauth_callback(
        code=code,
        state=state,
        error=error,
    )
    return HTMLResponse(content=html, status_code=status_code)
