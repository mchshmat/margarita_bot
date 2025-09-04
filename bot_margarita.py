
import locale
import sys
import requests
import random
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import os

# для локального запуска удобно подгружать .env (на сервере Render это не нужно)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

NOTION_TOKEN = os.environ["NOTION_TOKEN"]          # из окружения
DATABASE_ID  = os.environ["DATABASE_ID"]           # из окружения
BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]    # из окружения

# === НАСТРОЙКИ ===


headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def split_text(text, max_length=1800):
    parts = []
    while len(text) > max_length:
        split_pos = text.rfind(" ", 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    parts.append(text)
    return parts

def get_ready_reels():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "Статус",
            "select": {
                "equals": "Готов"
            }
        }
    }
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    data = res.json()
    if not data["results"]:
        return None
    return random.choice(data["results"])

def extract_reel_info(page):
    props = page["properties"]
    video = props["Видео"]["title"][0]["text"]["content"] if props["Видео"]["title"] else ""
    hook = "".join([part["text"]["content"] for part in props["Хук"]["rich_text"]])
    desc = "".join([part["text"]["content"] for part in props["Описание"]["rich_text"]])
    return video, hook, desc, page["id"]

def update_status(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "Статус": {
                "select": {
                    "name": "Залит"
                }
            }
        }
    }
    res = requests.patch(url, headers=headers, json=payload)
    res.raise_for_status()

async def send_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = get_ready_reels()
    if not page:
        await update.message.reply_text("Нет доступных Reels со статусом 'Готов'.")
        return

    video, hook, desc, page_id = extract_reel_info(page)
    await update.message.reply_text(hook)
    await update.message.reply_text(desc)
    update_status(page_id)

async def get_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "Статус",
            "select": {
                "equals": "Готов"
            }
        }
    }
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    data = res.json()
    count = len(data["results"])
    await update.message.reply_text(f"📊 Сейчас {count} Reels со статусом 'Готов'.")

def add_to_notion(hook, description, video):
    url = "https://api.notion.com/v1/pages"
    data = {
        "parent": { "database_id": DATABASE_ID },
        "properties": {
            "Видео": {
                "title": [{
                    "text": { "content": str(video) }
                }]
            },
            "Хук": {
                "rich_text": [{"text": {"content": part}} for part in split_text(str(hook))]
            },
            "Описание": {
                "rich_text": [{"text": {"content": part}} for part in split_text(str(description))]
            },
            "Статус": {
                "select": { "name": "Готов" }
            }
        }
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

async def add_combined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message.text.replace("/add", "", 1).strip()
        if not message:
            await update.message.reply_text("Пожалуйста, отправьте хук и описание одним сообщением после /add.")
            return
        parts = message.split("\n\n", 1)
        hook = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        add_to_notion(hook, description, "-")
        await update.message.reply_text("✅ Запись добавлена в таблицу.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при добавлении: {e}")


from telegram.ext import ConversationHandler

TEXT_INPUT, VIDEO_INPUT = range(2)

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи хук и описание в одном сообщении. Первый абзац — хук, остальное — описание.")
    return TEXT_INPUT

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    message = update.message.text.strip()
    parts = message.split("\n\n", 1)
    hook = parts[0].strip()
    description = parts[1].strip() if len(parts) > 1 else ""
    try:
        add_to_notion(hook, description, "")
        # Ответ: два сообщения (хук и рилс)
        await update.message.reply_text("✅ Запись добавлена в таблицу.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при добавлении: {e}")
    return ConversationHandler.END

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    video = update.message.text.strip()
    hook = user_data[uid]["hook"]
    desc = user_data[uid]["desc"]
    try:
        add_to_notion(hook, desc, video)
        await update.message.reply_text("✅ Запись добавлена в таблицу.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при добавлении: {e}")
    user_data.pop(uid)
    return ConversationHandler.END


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("reel", send_reel))
    app.add_handler(CommandHandler("score", get_score))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", start_add)],
        states={
            TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    
    print("✅ Бот запущен. Пиши /reel или /add.")
    # --- ВСТАВЬ ЭТО В КОНЕЦ bot_margarita.py ---

from telegram.ext import CommandHandler, MessageHandler, filters

# Примеры обработчиков (можешь оставить как есть — это проверка, что всё живо)
async def _start(update, context):
    await update.message.reply_text("Бот на Render готов. Пиши текст — отвечу эхо.")

async def _echo(update, context):
    if update.message and update.message.text:
        await update.message.reply_text(update.message.text)

def register_handlers(application):
    # Добавь сюда ВСЕ твои обработчики, которые раньше добавлял(а) через add_handler(...)
    # Минимум — /start и эхо
    application.add_handler(CommandHandler("start", _start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _echo))

