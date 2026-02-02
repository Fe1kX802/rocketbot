# Telegram Weighted Random Message Bot (aiogram)

This is a Telegram group bot written in **Python** using **aiogram 3**.  
The bot observes messages in group chats and periodically sends a random message or sticker based on real user activity frequency.

The more often users send the same message or sticker, the higher the probability that the bot will send it.

---

## Features

- Works in **groups and supergroups**
- Reads all user messages (text and stickers)
- Sends a message automatically every **N user messages**
- **Weighted random selection**:
- Messages that appear more often have higher probability
- Can send either **text messages or stickers**
- Stores data **no longer than 7 days** (automatic cleanup)
- Per-chat configuration
- Full **JSON logging** (terminal + file)
- Secure database wipe with one-time password confirmation

---

## How It Works

1. Users communicate normally in a group.
2. The bot stores:
   - Text messages
   - Sticker `file_id`s
3. After every `N` messages (configurable), the bot:
   - Randomly chooses between text or sticker
   - Sends one item using weighted probability
4. Old messages (older than 7 days) are automatically removed.
5. On first activity after restart, the bot sends a greeting message.

---

## Requirements
- Python 3.10+
- aiogram 3
- aiosqlite
- python-dotenv (if using .env for token)

---

## Notes
- The bot must be an admin in the group to read messages.
- SQLite is sufficient for small and medium chats.
- For high-load usage, PostgreSQL is recommended.
- Token should be stored in environment variables and excluded from Git.

---

## Commands

- /setfrequency n sets the number of user messages after which the bot will automatically send a message or sticker, allowing per-chat configuration
- /sendtext forces the bot to immediately send a text message using weighted random selection from stored messages
- /sendsticker forces the bot to immediately send a sticker from the stored stickers
- /cleardb completely clears the bot database, requiring a one-time 8-digit password printed to the host terminal, which the user must reply with to confirm the deletion.

