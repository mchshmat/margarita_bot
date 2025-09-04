# server.py — стабильная обёртка с логами (без лишней магии)
import os
import sys
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

# === ENV ===
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")  # напр. /webhook/bot-a

if not TOKEN:
    print("FATAL: TELEGRAM_BOT_TOKEN is missing", file=sys.stderr)
    raise SystemExit(1)

# === Telegram Application ===
application: Application = ApplicationBuilder().token(TOKEN).build()

# импортируем регистрацию хэндлеров из твоего кода
try:
    from bot_margarita import register_handlers
    register_handlers(application)
    print("INFO: handlers registered")
except Exception as e:
    print("FATAL: cannot import/register handlers:", e, file=sys.stderr)
    raise

# === FastAPI ===
app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/{tail:path}")
async def telegram_webhook(request: Request, tail: str):
    path = "/" + tail
    print(f"HIT {path}")
    if not path.startswith(WEBHOOK_PATH):
        print(f"SKIP (expected startswith {WEBHOOK_PATH})")
        return {"ok": True, "skip": True}
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
