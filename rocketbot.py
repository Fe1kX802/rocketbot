import asyncio
import random
import time
import json
import secrets
from datetime import datetime
import os
from dotenv import load_dotenv
import sys
from joker import get_random_joke
import asyncio



import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

# ------------------- TOKEN -------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "messages.db"
LOG_FILE = "bot_log.json"
TTL_SECONDS = 7 * 24 * 60 * 60  # 7 дней
PRIME_ADMIN_ID = 1192179740
ADMIN_IDS = []

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(TOKEN)
dp = Dispatcher()

# ------------------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ -------------------
pending_clear = {}        # chat_id -> password для /clearbd
pending_stop = {}         # chat_id -> password для /stop
spam_enabled = False      
pending_toggle_spam = {}  # chat_id -> password
started_chats = set()     # чаты, где бот уже поздоровался

# ------------------- ЛОГИ -------------------
def log_event(event_type: str, data: dict):
    BOLD = "\033[1m"
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[93m"
    BLUE = "\033[34m"

    record = {
        "ts": datetime.utcnow().isoformat(),
        "event": event_type,
        "data": data
    }

    ts_colored = f"{BOLD}{GREEN}{record['ts']}{RESET}"
    event_colored = f"{BOLD}{YELLOW}{record['event']}{RESET}"
    data_colored = f"{BOLD}{BLUE}{json.dumps(record['data'], ensure_ascii=False)}{RESET}"

    print(f"{ts_colored} | {event_colored} | {data_colored}")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")



# ------------------- БАЗА ДАННЫХ -------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                type TEXT,
                content TEXT,
                ts INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                frequency INTEGER DEFAULT 50,
                counter INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS greetings (
                chat_id INTEGER PRIMARY KEY,
                text TEXT
            )
        """)
        await db.commit()


async def cleanup_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE ts < ?",
            (int(time.time()) - TTL_SECONDS,)
        )
        await db.commit()


# ------------------- УТИЛИТЫ -------------------
async def get_settings(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT frequency, counter FROM settings WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO settings (chat_id, frequency, counter) VALUES (?, ?, ?)",
                (chat_id, 50, 0)
            )
            await db.commit()
            return 50, 0
        return row[0], row[1]


async def update_counter(chat_id: int, counter: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE settings SET counter = ? WHERE chat_id = ?",
            (counter, chat_id)
        )
        await db.commit()


async def set_frequency(chat_id: int, freq: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO settings (chat_id, frequency, counter)
            VALUES (?, ?, 0)
            ON CONFLICT(chat_id) DO UPDATE SET frequency = ?, counter = 0
        """, (chat_id, freq, freq))
        await db.commit()


async def save_message(chat_id: int, msg_type: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, type, content, ts) VALUES (?, ?, ?, ?)",
            (chat_id, msg_type, content, int(time.time()))
        )
        await db.commit()


async def weighted_choice(chat_id: int, msg_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT content, COUNT(*) as c
            FROM messages
            WHERE chat_id = ? AND type = ?
            GROUP BY content
        """, (chat_id, msg_type))
        rows = await cur.fetchall()

    if not rows:
        return None

    population = []
    for content, count in rows:
        population.extend([content] * count)

    return random.choice(population)


# ------------------- ПРИВЕТСТВИЕ -------------------
async def set_hello(chat_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO greetings (chat_id, text)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET text = ?
        """, (chat_id, text, text))
        await db.commit()


async def get_hello(chat_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT text FROM greetings WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cur.fetchone()
        if row:
            return row[0]
    return "Привет всем!"


# ------------------- КОМАНДЫ -------------------
@dp.message(Command("setfrequency"))
async def cmd_setfrequency(message: Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return
    freq = int(parts[1])
    if freq <= 0:
        return
    await set_frequency(message.chat.id, freq)
    await message.answer(f'Задана частота ответов бота: {freq}')


@dp.message(Command("spam"))
async def cmd_spam(message: Message):
    if not spam_enabled:
        await message.answer("Функция отключена")
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return

    count = int(parts[1])

    for _ in range(count):
        choice = random.choice(["text", "text", "text", "text", "sticker"])
        if choice == "text":
            text = await weighted_choice(message.chat.id, "text")
            if text:
                await message.answer(text)
        else:
            sticker = await weighted_choice(message.chat.id, "sticker")
            if sticker:
                await message.answer_sticker(sticker)


@dp.message(Command("toggle_spam"))
async def cmd_toggle_spam(message: Message):
    chat_id = message.chat.id
    password = "".join(str(secrets.randbelow(10)) for _ in range(4))
    pending_toggle_spam[chat_id] = password

    await bot.send_message(
        PRIME_ADMIN_ID,
        f"[TOGGLESPAM] chat_id={chat_id} password={password}"
    )

    await message.answer(
        "Одноразовый пароль отправлен администратору. "
        "Ответь на это сообщение паролем для переключения spam."
    )



@dp.message(Command("joke"))
async def cmd_joke(message: Message):
    loop = asyncio.get_running_loop()
    joke = await loop.run_in_executor(None, get_random_joke)

    if not joke:
        await message.answer("Не удалось получить шутку(")
        return

    await message.answer(joke)


@dp.message(Command("help"))
async def cmd_sendtext(message: Message):
    text = 'Список команд:\n' \
    '/sendtext - отправляет сообщение\n' \
    '/sendsticker - отправляет стикер\n' \
    '/setfrequency n - управляет частотой ответов бота\n' \
    '/sethello [ТЕКСТ] - задает приветственное сообщение с новым текстом\n' \
    '/spam n - бот отправит n рандомных сообщений\n' \
    '/joke - бот отправит рандомную шутку\n' \
    '\n' \
    'Админские команды (под паролем):\n' \
    '/cleardb - стирает базу данных\n' \
    '/stop - останавливает работу бота \n' \
    '/toggle_spam - переключение функции spam (активна/отключена)\n' \
    '/getlog - отправляет полный файл логов в лс админу'
    if text:
        await message.answer(text)
        log_event("manual_send_text", {
            "chat_id": message.chat.id,
            "content": text
        })


@dp.message(Command("sendtext"))
async def cmd_sendtext(message: Message):
    text = await weighted_choice(message.chat.id, "text")
    if text:
        await message.answer(text)
        log_event("manual_send_text", {
            "chat_id": message.chat.id,
            "content": text
        })


@dp.message(Command("sendsticker"))
async def cmd_sendsticker(message: Message):
    sticker = await weighted_choice(message.chat.id, "sticker")
    if sticker:
        await message.answer_sticker(sticker)
        log_event("manual_send_sticker", {
            "chat_id": message.chat.id,
            "file_id": sticker
        })


@dp.message(Command("getlog"))
async def cmd_getlog(message: Message):
    await bot.send_document(
        chat_id=message.from_user.id,
        document=FSInputFile("bot_log.json")
    )
    log_event("send_logs", {
        "chat_id": message.chat.id,
        "content": "bot_log.json"
    })


@dp.message(Command("cleardb"))
async def cmd_cleardb(message: Message):
    chat_id = message.chat.id

    password = "".join(str(secrets.randbelow(10)) for _ in range(8))
    pending_clear[chat_id] = password

    print(f"[CLEARDATABASE] chat_id={chat_id} password={password}")

    await bot.send_message(
        chat_id=PRIME_ADMIN_ID,
        text=f"[CLEARDATABASE] chat_id={chat_id} password={password}"
    )

    await message.answer(
        "Для очистки базы данных ответьте на это сообщение восьмизначным паролем."
    )


@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    chat_id = message.chat.id

    password = "".join(str(secrets.randbelow(10)) for _ in range(4))
    pending_stop[chat_id] = password

    print(f"[STOPBOT] chat_id={chat_id} password={password}")

    await bot.send_message(
        chat_id=PRIME_ADMIN_ID,
        text=f"[STOPBOT] chat_id={chat_id} password={password}"
    )

    await message.answer(
        "Для остановки бота в этом чате ответьте на это сообщение четырёхзначным паролем."
    )


@dp.message(F.reply_to_message)
async def handle_clear_stop_toggle_spam_reply(message: Message):
    chat_id = message.chat.id
    if not message.text:
        return

    text = message.text.strip()

    # ---------- очистка базы ----------
    if chat_id in pending_clear:
        expected = pending_clear[chat_id]
        del pending_clear[chat_id]

        if text == expected:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM messages")
                await db.execute("DELETE FROM settings")
                await db.commit()

            log_event("database_cleared", {"chat_id": chat_id})
            await message.answer("База данных очищена.")
        return

    # ---------- остановка бота ----------
    if chat_id in pending_stop:
        expected = pending_stop[chat_id]
        del pending_stop[chat_id]

        if text == expected:
            if chat_id in started_chats:
                started_chats.remove(chat_id)

            log_event("bot_stopped_in_chat", {"chat_id": chat_id})
            await message.answer("Бот остановлен в этом чате.")
            sys.exit(0)
        return

    # ---------- toggle_spam ----------
    if chat_id in pending_toggle_spam:
        expected = pending_toggle_spam[chat_id]
        del pending_toggle_spam[chat_id]

        if text == expected:
            global spam_enabled
            spam_enabled = not spam_enabled

            state = "включена" if spam_enabled else "отключена"

            log_event("toggle_spam", {
                "chat_id": chat_id,
                "enabled": spam_enabled
            })

            await message.answer(f"Функция spam теперь {state}")
        return



@dp.message(Command("sethello"))
async def cmd_sethello(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    text = parts[1].strip()
    if not text:
        return
    await set_hello(message.chat.id, text)
    await message.answer(f"Hello message updated to:\n{text}")


# ------------------- ОБРАБОТКА СООБЩЕНИЙ -------------------
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_messages(message: Message):
    if message.from_user and message.from_user.is_bot:
        return

    chat_id = message.chat.id

    if chat_id not in started_chats:
        started_chats.add(chat_id)
        hello_text = await get_hello(chat_id)
        await message.answer(hello_text)
        log_event("bot_started_in_chat", {
            "chat_id": chat_id,
            "chat_title": message.chat.title,
            "hello_text": hello_text
        })

    await cleanup_db()

    freq, counter = await get_settings(chat_id)
    counter += 1

    if message.text:
        await save_message(chat_id, "text", message.text)

    if message.sticker:
        await save_message(chat_id, "sticker", message.sticker.file_id)

    if counter >= freq:
        counter = 0

        choice_type = random.choice(["text", "text", "text", "text", "sticker"])
        content = await weighted_choice(chat_id, choice_type)

        if content:
            if choice_type == "text":
                await message.answer(content)
            else:
                await message.answer_sticker(content)

            log_event("auto_send", {
                "chat_id": chat_id,
                "type": choice_type,
                "content": content
            })

    await update_counter(chat_id, counter)


# ------------------- ЗАПУСК -------------------
async def main():
    log_event("bot_process_started", {"status": "ok"})
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
