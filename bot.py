import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import Message
from groq import Groq
import yt_dlp

# ==========================================
# 1. НАСТРОЙКА И КОНФИГУРАЦИЯ
# ==========================================

# Вставьте сюда ваш токен от @BotFather
BOT_TOKEN = "9005836465:AAG9UDgflEjuxs9PiMI8gBQutb-8kFCAx_U"

# Вставьте сюда ваш бесплатный API ключ от Groq (начинается с gsk_...)
GROQ_API_KEY = "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"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и клиента Groq
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = Groq(api_key=GROQ_API_KEY)

# Папка для временных аудио- и видеофайлов
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def transcribe_audio_file(file_path: str) -> str:
    """
    Отправляет аудио в бесплатный API Groq (модель whisper-large-v3).
    Работает мгновенно и не загружает память сервера.
    """
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
    """
    Скачивает аудио из ссылки (YouTube, VK, TikTok и т.д.) с помощью yt-dlp.
    """
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
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        logging.error(f"Ошибка при скачивании по ссылке: {e}")
        return False


# ==========================================
# 3. ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ
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
        success = await asyncio.to_thread(download_media_from_url, url, base_path)

        if not success or not os.path.exists(expected_mp3):
            await status_msg.edit_text("❌ Не удалось скачать аудио по этой ссылке.")
            return

        await status_msg.edit_text("⚡️ Расшифровываю аудио с видео... Пожалуйста, подождите.")

        text = await asyncio.to_thread(transcribe_audio_file, expected_mp3)

        if text:
            if len(text) > 4000:
                for i in range(0, len(text), 4000):
                    await message.answer(text[i:i+4000])
                await status_msg.delete()
            else:
                await status_msg.edit_text(f"📝 **Результат расшифровки по ссылке:**\n\n{text}", parse_mode="Markdown")
        else:
            await status_msg.edit_text("⚠️ Не удалось распознать речь в этом видео.")

    except Exception as e:
        logging.error(f"Ошибка обработки ссылки: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обработке ссылки.")
    finally:
        if os.path.exists(expected_mp3):
            os.remove(expected_mp3)


# ==========================================
# 4. ЗАПУСК БОТА
# ==========================================

async def main():
    print("Бот успешно запущен через Groq API!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")