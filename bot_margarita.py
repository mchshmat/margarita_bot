# bot_margarita.py — логика 1-в-1 как в старом боте, но без лишних «резов» текста

import os
import random
import requests
from typing import Tuple, Optional

from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    Application,  # тип для подсказок
    filters,
)

# === ENV ===
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
DATABASE_ID  = os.environ.get("DATABASE_ID", "").strip()

if not NOTION_TOKEN or not DATABASE_ID:
    print("WARN: NOTION_TOKEN or DATABASE_ID not set")

# === Константы/утилиты ===
TEXT_INPUT, VIDEO_INPUT = range(2)

# Жёсткий лимит Телеграма ~4096; оставим запас, чтобы не упираться ровно в 4096
TELEGRAM_HARD_LIMIT = 4096
SAFE_LIMIT = 3900

def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

def split_text(text: str, max_length: int = SAFE_LIMIT):
    """Режем текст ТОЛЬКО если он реально длиннее лимита.
    Стараемся резать по пробелу, чтобы не рвать слова.
    """
    parts = []
    while len(text) > max_length:
        split_pos = text.rfind(" ", 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    if text:
        parts.append(text)
    return parts

def get_ready_reels() -> Optional[dict]:
    """Берём случайную страницу со Статусом == 'Готов'."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {"filter": {"property": "Статус", "select": {"equals": "Готов"}}}
    res = requests.post(url, headers=_headers(), json=payload, timeout=30)
    res.raise_for_status()
    data = res.json()
    if not data.get("results"):
        return None
    return random.choice(data["results"])

def extract_reel_info(page: dict) -> Tuple[str, str, str, str]:
    """Достаём (video, hook, desc, page_id) из свойств страницы."""
    props = page.get("properties", {})
    def _title(prop):
        arr = props.get(prop, {}).get("title", [])
        return arr[0]["text"]["content"] if arr else ""
    def _rt(prop):
        arr = props.get(prop, {}).get("rich_text", [])
        return "".join(part.get("text", {}).get("content", "") for part in arr)

    video = _title("Видео")
    hook  = _rt("Хук")
    desc  = _rt("Описание")
    return video, hook, desc, page["id"]

def update_status(page_id: str):
    """Меняем Статус на 'Залит'."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": {"Статус": {"select": {"name": "Залит"}}}}
    res = requests.patch(url, headers=_headers(), json=payload, timeout=30)
    res.raise_for_status()

def add_to_notion(hook: str, description: str, video: str):
    """Добавляем новую запись (Статус = 'Готов')."""
    url = "https://api.notion.com/v1/pages"
    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Видео": {"title": [{"text": {"content": str(video)}}]},
            "Хук": {"rich_text": [{"text": {"content": part}} for part in split_text(str(hook))]},
            "Описание": {"rich_text": [{"text": {"content": part}} for part in split_text(str(description))]},
            "Статус": {"select": {"name": "Готов"}},
        },
    }
    res = requests.post(url, headers=_headers(), json=data, timeout=30)
    res.raise_for_status()


# === HANDLERS (async, PTB v20) ===

async def send_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /reel — взять случайную 'Готов' и прислать Хук + Описание, затем пометить 'Залит'."""
    try:
        page = get_ready_reels()
        if not page:
            await update.message.reply_text("Нет доступных Reels со статусом 'Готов'.")
            return
        video, hook, desc, page_id = extract_reel_info(page)

        # 1) Хук — отдельным сообщением, как раньше
        if hook:
            await update.message.reply_text(hook)

        # 2) Описание — одним сообщением, ЕСЛИ влазит; иначе режем по SAFE_LIMIT
        if desc:
            if len(desc) <= SAFE_LIMIT:
                await update.message.reply_text(desc)
            else:
                for part in split_text(desc, SAFE_LIMIT):
                    await update.message.reply_text(part)

        update_status(page_id)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def get_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /score — количество 'Готов'."""
    try:
        url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
        payload = {"filter": {"property": "Статус", "select": {"equals": "Готов"}}}
        res = requests.post(url, headers=_headers(), json=payload, timeout=30)
        res.raise_for_status()
        data = res.json()
        count = len(data.get("results", []))
        await update.message.reply_text(f"📊 Сейчас {count} Reels со статусом 'Готов'.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт диалога /add: пользователь шлёт одним сообщением хук и описание (через пустую строку)."""
    await update.message.reply_text(
        "Введи хук и описание в одном сообщении. Первый абзац — хук, остальное — описание."
    )
    return TEXT_INPUT

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимаем текст от /add (хук + описание), создаём запись (Видео пустое)."""
    message = (update.message.text or "").strip()
    parts = message.split("\n\n", 1)
    hook = parts[0].strip()
    description = parts[1].strip() if len(parts) > 1 else ""
    try:
        add_to_notion(hook, description, "")
        await update.message.reply_text("✅ Запись добавлена в таблицу.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при добавлении: {e}")
    return ConversationHandler.END


# === РЕГИСТРАЦИЯ ДЛЯ server.py ===
def register_handlers(application: Application):
    # Команды
    application.add_handler(CommandHandler("reel", send_reel))
    application.add_handler(CommandHandler("score", get_score))

    # Диалог /add (одним сообщением)
    conv = ConversationHandler(
        entry_points=[CommandHandler("add", start_add)],
        states={
            TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
        },
        fallbacks=[],
    )
    application.add_handler(conv)

    # Никаких эхо/общих текстовых хэндлеров — чтобы не перехватывали сообщения.
