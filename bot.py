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

# Load environment variables
load_dotenv()

nest_asyncio.apply()  # Allow nested asyncio event loops (useful for Flask & asyncio integration)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Flask application
app = Flask(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
TERABOX_API_URL = os.getenv("TERABOX_API_URL")

# Telegram bot (telebot) and Telethon client initialization
bot = telebot.TeleBot(BOT_TOKEN)
telethon_client = TelegramClient("bot_session", API_ID, API_HASH)

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

@bot.message_handler(commands=["start"])
def start_command(message):
    try:
        bot.send_message(message.chat.id, "Hello! Send me a valid Terabox link, and I'll process it for you.")
    except Exception as e:
        logging.error(f"Error in /start command: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    if not url.startswith("http"):
        bot.reply_to(message, "Please send a valid URL.")
        return
    try:
        msg = bot.send_message(message.chat.id, "Processing your request...")
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        logging.error(f"Error deleting message: {str(e)}")
    # Call the async function for file processing
    asyncio.create_task(process_file(url, message))

async def process_file(url, message):
    file_path = None
    try:
        # Step 1: Fetch the file details from Terabox API
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TERABOX_API_URL}?url={url}") as resp:
                if resp.status != 200:
                    bot.reply_to(message, "Failed to fetch file details. Please check the link.")
                    return
                data = await resp.json()
        
        if not data.get("ok"):
            bot.reply_to(message, "Failed to fetch file details. Please check the link.")
            return
        
        filename = data["filename"]
        download_url = data["downloadLink"]
        file_size = data["size"]

        # Step 2: Check if the file size exceeds Telegram's 2GB limit
        try:
            file_size_mb = float(file_size.replace("MB", "").strip())
        except ValueError:
            bot.reply_to(message, "Could not determine file size. Please try another link.")
            return
        
        max_size_mb = 2000
        if file_size_mb > max_size_mb:
            bot.reply_to(message, f"File size exceeds Telegram's 2GB limit: {file_size}.")
            return

        bot.reply_to(message, f"Downloading: {filename} ({file_size})")

        # Step 3: Download the file
        os.makedirs("./downloads", exist_ok=True)
        file_path = os.path.join("./downloads", f"{message.chat.id}_{filename}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    bot.reply_to(message, "Failed to download the file.")
                    return
                with open(file_path, "wb") as file:
                    while chunk := await resp.content.read(1024 * 1024):
                        file.write(chunk)

        bot.reply_to(message, f"Download complete: {filename}")
        
        # Step 4: Send the file to the user
        with open(file_path, "rb") as file:
            if filename.endswith(('.mp4', '.mkv', '.avi')):
                bot.send_video(message.chat.id, file, caption=f"Here is your video: {filename}")
            else:
                bot.send_document(message.chat.id, file, caption=f"Here is your file: {filename}")
        
        # Step 5: Upload the file to the channel using Telethon
        await upload_to_channel(file_path, filename)

    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")
        logging.error(f"Error processing file: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)  # Clean up the file after processing

async def upload_to_channel(file_path, filename):
    try:
        if not telethon_client.is_connected():
            await telethon_client.connect()
        await telethon_client.send_file(CHANNEL_ID, file_path, caption=f"Uploaded: {filename}")
    except Exception as e:
        logging.error(f"Error uploading file to channel: {str(e)}")

def start_polling():
    bot.polling(none_stop=True, interval=1, timeout=60)

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

if __name__ == "__main__":
    # Start Flask server in a separate thread
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Start bot polling in a separate thread (non-blocking)
    polling_thread = Thread(target=start_polling)
    polling_thread.start()

    # Run the Telethon client in the main event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(telethon_client.start(bot_token=BOT_TOKEN))
        logging.info("Bot and Telethon are running...")

    except Exception as e:
        logging.error(f"Error starting bot: {str(e)}")
