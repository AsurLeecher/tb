import os
import telebot
import asyncio
from telethon import TelegramClient
from flask import Flask, jsonify
from threading import Thread
import aiohttp
import logging
import nest_asyncio
from dotenv import load_dotenv
import aiofiles

# Load environment variables
load_dotenv()

nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
TERABOX_API_URL = os.getenv("TERABOX_API_URL")

bot = telebot.AsyncTeleBot(BOT_TOKEN)
telethon_client = TelegramClient("bot_session", API_ID, API_HASH)

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

@bot.message_handler(commands=["start"])
async def start_command(message):
    try:
        await bot.send_message(message.chat.id, "Hello! Send me a valid Terabox link, and I'll process it for you.")
    except Exception as e:
        logging.error(f"Error in /start command: {str(e)}")

@bot.message_handler(func=lambda message: True)
async def handle_message(message):
    url = message.text.strip()
    if not url.startswith("http"):
        await bot.reply_to(message, "Please send a valid URL.")
        return
    
    try:
        processing_msg = await bot.send_message(message.chat.id, "Processing your request...")
        await asyncio.sleep(1.5)
        await bot.delete_message(message.chat.id, processing_msg.message_id)
    except Exception as e:
        logging.error(f"Error handling message: {str(e)}")
    
    asyncio.create_task(process_file(url, message))

async def process_file(url, message):
    file_path = None
    try:
        async with aiohttp.ClientSession() as session:
            # Get file metadata
            async with session.get(f"{TERABOX_API_URL}?url={url}") as resp:
                if resp.status != 200:
                    await bot.reply_to(message, "❌ Failed to fetch file details")
                    return
                data = await resp.json()
        
        if not data.get("ok"):
            await bot.reply_to(message, "❌ Invalid or unavailable link")
            return

        filename = data["filename"]
        download_url = data["downloadLink"]
        file_size = data["size"]

        # Validate file size
        try:
            file_size_mb = float(file_size.replace("MB", "").strip())
        except ValueError:
            await bot.reply_to(message, "❌ Could not determine file size")
            return

        if file_size_mb > 2000:  # Telegram's 2GB limit
            await bot.reply_to(message, f"❌ File too large ({file_size})")
            return

        # Download the file
        os.makedirs("./downloads", exist_ok=True)
        file_path = os.path.join("./downloads", f"{message.chat.id}_{filename}")
        
        await bot.reply_to(message, f"⏬ Downloading: {filename} ({file_size})")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    await bot.reply_to(message, "❌ Download failed")
                    return
                
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):  # 1MB chunks
                        await f.write(chunk)

        # Send to user
        async with aiofiles.open(file_path, "rb") as f:
            file_data = await f.read()
            if filename.endswith(('.mp4', '.mkv', '.avi')):
                await bot.send_video(message.chat.id, file_data, caption=f"🎥 {filename}")
            else:
                await bot.send_document(message.chat.id, file_data, caption=f"📄 {filename}")

        # Upload to channel
        await upload_to_channel(file_path, filename)

    except Exception as e:
        await bot.reply_to(message, f"❌ Error: {str(e)}")
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

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

async def main():
    try:
        await telethon_client.start(bot_token=BOT_TOKEN)
        logging.info("Telethon client started")
        await bot.infinity_polling()
    except Exception as e:
        logging.error(f"Bot startup error: {str(e)}")
    finally:
        await telethon_client.disconnect()

if __name__ == "__main__":
    # Run Flask in a separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Create and run the asyncio event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
