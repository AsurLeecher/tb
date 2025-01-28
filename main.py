
import os
import telebot
import asyncio
from telethon import TelegramClient
from flask import Flask, jsonify
from threading import Thread
import aiohttp
import nest_asyncio
nest_asyncio.apply()
app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "7542241757:AAFgeHI2tr518Hbh8DOvLIfeCpQj0udfk-Y")
API_ID = int(os.getenv("API_ID", "22469064"))
API_HASH = os.getenv("API_HASH", "c05481978a217fdb11fa6774b15cba32")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002170811388"))
TERABOX_API_URL = os.getenv("TERABOX_API_URL", "https://d-jp01-ntt.terabox.com/file/90149685b31bc3495919880f71066165?bkt=en-2bd419aa17f4904f93f81bb8b56fa895ec5d1f7ea0890404a53873ae9e18cb4db7d0b221d422d410&xcode=325fcd154d2ea80cd7023f75883ff5e1a9e6a80b758cfc3d3dc0c4331d469392d1b1103bd74e3ec01c963a317ee53257b8c79fc932c478ac&fid=4401984238737-250528-808272336452438&time=1737291401&sign=FDTAXUGERLQlBHSKfWon-DCb740ccc5511e5e8fedcff06b081203-c2I9KGGN1uVFj9ds6yhmwPjTY4Y%3D&to=142&size=21779463&sta_dx=21779463&sta_cs=18&sta_ft=mp4&sta_ct=7&sta_mt=3&fm2=MH%2Ctky%2CAnywhere%2C%2CVmlyZ2luaWE%3D%2Cany&region=tky&ctime=1685042010&mtime=1736330232&resv0=-1&resv1=0&resv2=rlim&resv3=5&resv4=21779463&vuk=4401514344005&iv=0&htype=&randtype=&newver=1&newfm=1&secfm=1&flow_ver=3&pkey=en-7031146dabe6c354f3c15bbaba48885f1133840554a683db39c44d35dd2a93fbfb3c3a4cce560cb8&sl=68091977&expires=1737320201&rt=sh&r=803651991&sh=1&vbdid=-&fin=4322+1.mp4&fn=4322+1.mp4&rtype=1&dp-logid=437711359918221153&dp-callid=0.1&hps=1&tsl=2000&csl=2000&fsl=-1&csign=%2Fg7F1AmTtnWd27Rco4go6dDvbdg%3D&so=0&ut=6&uter=4&serv=1&uc=3536201931&ti=e6e2f9d25109af0e59cb43a32ecb704003e147c7f4fed67e&tuse=&raw_appid=0&ogr=0&rregion=XVVi&adg=&reqlabel=250528_f_ea482012bf88ff342a7eef66c56ec6c4_-1_5e2b811d6bad73ccbd2ef032acc00418&ccn=US&by=themis")
bot = telebot.TeleBot(BOT_TOKEN)
telethon_client = TelegramClient("bot_session", API_ID, API_HASH)
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200
@bot.message_handler(commands=["start"])
def start_command(message):
    try:
        bot.send_message(
            message.chat.id,
            "Hello! Send me a valid Terabox link, and I'll process it for you."
        )
    except Exception as e:
        print(f"Error in /start command: {str(e)}")
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
        print(f"Error deleting message: {str(e)}")
    asyncio.create_task(process_file(url, message))
async def process_file(url, message):
    try:
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
        with open(file_path, "rb") as file:
            if filename.endswith(('.mp4', '.mkv', '.avi')):
                bot.send_video(message.chat.id, file, caption=f"Here is your video: {filename}")
            else:
                bot.send_document(message.chat.id, file, caption=f"Here is your file: {filename}")
        asyncio.create_task(upload_to_channel(file_path, filename))
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
async def upload_to_channel(file_path, filename):
    try:
        if not telethon_client.is_connected():
            await telethon_client.connect()
        await telethon_client.send_file(
            CHANNEL_ID,
            file_path,
            caption=f"Uploaded: {filename}"
        )
    except Exception as e:
        print(f"Error uploading file to channel: {str(e)}")
if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=5000)
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    async def main():
        try:
            await telethon_client.start(bot_token=BOT_TOKEN)
            print("Bot is running...")
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            print(f"Error starting bot: {str(e)}")
