import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from groq import Groq
import yt_dlp
from aiohttp import web

# ==========================================
# 1. НАСТРОЙКА И КОНФИГУРАЦИЯ
# ==========================================

BOT_TOKEN = 9005836465:AAG9UDgflEjuxs9PiMI8gBQutb-8kFCAx_U
GROQ_API_KEY = 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

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==========================================
# 2. МИКРО ВЕБ-СЕРВЕР ДЛЯ RENDER
# ==========================================

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {port}")

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def transcribe_audio_file(file_path: str) -> str:
    try:
        with open(file_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(os.path.basename(file_path), file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        return str(transcription).strip()
    except Exception as e:
        logging.error(f"Ошибка при расшифровке через Groq API: {e}")
        return ""

def download_media_from_url(url: str, output_path: str) -> bool:
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        logging.error(f"Ошибка при скачивании по ссылке {url}: {e}")
        return False

# ==========================================
# 4. ОБРАБОТЧИКИ СООБЩЕНИЙ
# ==========================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = (
        "👋 **Привет! Я твой бесплатный бот-расшифровщик!**\n\n"
        "Я могу перевести в текст:\n"
        "🎙 Голосовые сообщения\n"
        "📹 Видеосообщения (кружочки)\n"
        "📁 Аудио и видео файлы\n"
        "🔗 Ссылки на видео/аудио (YouTube, VK, TikTok и др.)\n\n"
        "Просто отправь мне файл, голосовое или ссылку!"
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(F.voice | F.video_note | F.audio | F.video | F.document)
async def handle_media_messages(message: Message):
    status_msg = await message.answer("⏳ Скачиваю файл...")
    
    if message.voice:
        file_id = message.voice.file_id
        ext = "ogg"
    elif message.video_note:
        file_id = message.video_note.file_id
        ext = "mp4"
    elif message.audio:
        file_id = message.audio.file_id
        ext = message.audio.file_name.split('.')[-1] if message.audio.file_name else "mp3"
    elif message.video:
        file_id = message.video.file_id
        ext = "mp4"
    elif message.document:
        file_id = message.document.file_id
        ext = message.document.file_name.split('.')[-1] if message.document.file_name else "file"
    else:
        await status_msg.edit_text("❌ Неподдерживаемый тип файла.")
        return

    local_path = os.path.join(DOWNLOAD_DIR, f"{message.from_user.id}_{message.message_id}.{ext}")

    try:
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, destination=local_path)

        await status_msg.edit_text("⚡️ Расшифровываю речь... Пожалуйста, подождите.")

        text = await asyncio.to_thread(transcribe_audio_file, local_path)

        if text:
            if len(text) > 4000:
                for i in range(0, len(text), 4000):
                    await message.answer(text[i:i+4000])
                await status_msg.delete()
            else:
                await status_msg.edit_text(f"📝 **Результат расшифровки:**\n\n{text}", parse_mode="Markdown")
        else:
            await status_msg.edit_text("⚠️ Не удалось распознать речь или аудио оказалось пустым.")

    except Exception as e:
        logging.error(f"Ошибка обработки: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обработке файла.")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

@dp.message(F.text.startswith("http://") | F.text.startswith("https://"))
async def handle_url_message(message: Message):
    url = message.text.strip()
    status_msg = await message.answer("🔗 Загружаю медиа по ссылке...")

    base_path = os.path.join(DOWNLOAD_DIR, f"url_{message.from_user.id}_{message.message_id}")
    expected_mp3 = f"{base_path}.mp3"

    try:
        # Устанавливаем жесткий таймаут 60 секунд на скачивание
        success = await asyncio.wait_for(
            asyncio.to_thread(download_media_from_url, url, base_path),
            timeout=60.0
        )

        if not success or not os.path.exists(expected_mp3):
            await status_msg.edit_text("❌ Не удалось скачать аудио по этой ссылке. Убедитесь, что видео публично доступно.")
            return

        await status_msg.edit_text("⚡️ Расшифровываю аудио... Пожалуйста, подождите.")

        text = await asyncio.to_thread(transcribe_audio_file, expected_mp3)

        if text:
            if len(text) > 4000:
                for i in range(0, len(text), 4000):
                    await message.answer(text[i:i+4000])
                await status_msg.delete()
            else:
                await status_msg.edit_text(f"📝 **Результат расшифровки по ссылке:**\n\n{text}", parse_mode="Markdown")
        else:
            await status_msg.edit_text("⚠️ Не удалось распознать речь в этом медиа.")

    except asyncio.TimeoutError:
        logging.error("Таймаут скачивания видео по ссылке")
        await status_msg.edit_text("⏱ Скачивание заняло слишком много времени и было прервано.")
    except Exception as e:
        logging.error(f"Ошибка обработки ссылки: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обработке ссылки.")
    finally:
        if os.path.exists(expected_mp3):
            os.remove(expected_mp3)

# ==========================================
# 5. ЗАПУСК БОТА И ВЕБ-СЕРВЕРА
# ==========================================

async def main():
    await start_web_server()
    print("Бот и веб-сервер успешно запущены!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
