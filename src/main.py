from fastapi import FastAPI, Request, Header, HTTPException
from mangum import Mangum
import src.handlers.webhook_handler as webhook_handler
import src.services.secret_service as secret_service

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
