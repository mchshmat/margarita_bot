import os
from dotenv import load_dotenv

load_dotenv()

print("NOTION_TOKEN:", os.getenv("NOTION_TOKEN"))
print("DATABASE_ID:", os.getenv("DATABASE_ID"))
print("TELEGRAM_BOT_TOKEN:", os.getenv("TELEGRAM_BOT_TOKEN"))
