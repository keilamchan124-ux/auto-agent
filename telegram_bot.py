# -*- coding: utf-8 -*-
import telebot
import os
import sys
from dotenv import load_dotenv

load_dotenv(".env", override=True)

# 確保在專案根目錄可以找到 core
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from core.config import Config
except ImportError:
    print("⚠️ 找不到 core.config，請確保你在 Agent V7.2 專案根目錄執行此腳本。")
    sys.exit(1)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))

if not TOKEN:
    print("⚠️ TELEGRAM_BOT_TOKEN 未設定，請在 .env 加入此變數。")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id != ALLOWED_USER_ID:
        bot.reply_to(message, "⛔ 你沒有權限使用此 Bot。")
        return
    
    welcome_text = (
        "👋 歡迎使用 Agent V7.2 控制台！\n"
        "直接輸入任務內容，我就會交給 Agent 執行。\n\n"
        "可用指令：\n"
        "/status - 查看 Agent 狀態\n"
        "/report - 查看最新執行報告\n"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['status'])
def check_status(message):
    if message.from_user.id != ALLOWED_USER_ID:
        return
    
    if Config.TODO_FILE.exists() and Config.TODO_FILE.read_text("utf-8").strip():
        bot.reply_to(message, "⏳ Agent 正在執行任務中...")
    else:
        bot.reply_to(message, "✅ Agent 目前閒置中，可以接受新任務。")

@bot.message_handler(commands=['report'])
def send_report(message):
    if message.from_user.id != ALLOWED_USER_ID:
        return
    
    report_path = Config.WORKSPACE_DIR / "artifacts" / "agent_execution_report.md"
    if report_path.exists():
        content = report_path.read_text("utf-8")
        if len(content) > 4000:
            content = content[:4000] + "\n... (報告太長，已截斷)"
        bot.reply_to(message, content)
    else:
        bot.reply_to(message, "📭 目前沒有任何執行報告。")

@bot.message_handler(func=lambda message: True)
def handle_task(message):
    if message.from_user.id != ALLOWED_USER_ID:
        return
    
    task = message.text.strip()
    try:
        # 寫入 todo.txt 讓 main.py 輪詢讀取
        Config.TODO_FILE.write_text(task, encoding="utf-8")
        bot.reply_to(message, f"📥 任務已送出！Agent 準備執行：\n{task[:100]}{'...' if len(task) > 100 else ''}")
    except Exception as e:
        bot.reply_to(message, f"❌ 任務送出失敗：{e}")

if __name__ == "__main__":
    print("Starting Agent V7.2 Telegram Bot...")
    try:
        print("Bot is active! Send /start in Telegram to begin.")
        bot.infinity_polling()
    except Exception as e:
        print(f"Bot error: {e}")

