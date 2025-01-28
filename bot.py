from aiogram import Bot, Dispatcher, types
from aiogram import types
from aiogram.utils import executor
import logging
import os
from dotenv import load_dotenv
from telethon import TelegramClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
TERABOX_API_URL = os.getenv("TERABOX_API_URL")

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

telethon_client = TelegramClient("bot_session", API_ID, API_HASH)

@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    await message.reply("Hello! Send me a valid Terabox link, and I'll process it for you.")

@dp.message_handler(lambda message: True)
async def handle_message(message: types.Message):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.reply("Please send a valid URL.")
        return
    
    await message.reply("Processing your request...")

    # Start async processing in a non-blocking way
    await process_file(url, message)

async def process_file(url, message):
    file_path = None
    try:
        # Your existing async processing logic here
        pass
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        logging.error(f"Processing error: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

async def upload_to_channel(file_path, filename):
    try:
        if not telethon_client.is_connected():
            await telethon_client.connect()
        
        await telethon_client.send_file(
            CHANNEL_ID,
            file_path,
            caption=f"📁 {filename}",
            supports_streaming=True
        )
    except Exception as e:
        logging.error(f"Channel upload error: {str(e)}")

async def on_startup():
    await telethon_client.start(bot_token=BOT_TOKEN)

if __name__ == "__main__":
    # Start the bot
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
