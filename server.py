import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
BASE_URL     = os.getenv("BASE_URL")  # например: https://mybot.onrender.com

# создаём приложение Telegram
application: Application = ApplicationBuilder().token(BOT_TOKEN).build()

# импортируем твой код и регистрируем хэндлеры
from bot_margarita import register_handlers
register_handlers(application)

# создаём FastAPI
app = FastAPI()

@app.post("/{tail:path}")
async def webhook(request: Request, tail: str):
    if not request.url.path.startswith(WEBHOOK_PATH):
        return {"ok": True, "skip": True}
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    webhook_url = f"{BASE_URL}{WEBHOOK_PATH}"
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(url=webhook_url)
