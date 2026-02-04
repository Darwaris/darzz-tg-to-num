import asyncio
import re
import time
import os
from threading import Thread
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.errors import FloodWait

# ================== CONFIG ==================
TARGET_BOT = "@telebrecheddb_bot"

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# ================== TELEGRAM CLIENT ==================
tg_client = Client(
    name="session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    no_updates=True
)

# ================== PARSER ==================
def parse_bot_response(text: str) -> dict:
    text = text.replace("Телефон", "Phone") \
               .replace("История изменения имени", "Name change history") \
               .replace("Интересовались этим", "Viewed by")

    data = {
        "success": True,
        "username": None,
        "id": None,
        "phone": None,
        "viewed_by": None,
        "name_history": []
    }

    u = re.search(r"t\.me/([A-Za-z0-9_]+)", text)
    if u:
        data["username"] = u.group(1)

    i = re.search(r"ID[: ]+(\d+)", text)
    if i:
        data["id"] = i.group(1)

    p = re.search(r"Phone[: ]+(\d+)", text)
    if p:
        data["phone"] = p.group(1)

    v = re.search(r"Viewed by[: ]*(\d+)", text)
    if v:
        data["viewed_by"] = int(v.group(1))

    history = re.findall(r"(\d{2}\.\d{2}\.\d{4}) → @([\w_]+),\s*([\d, ]+)", text)
    for d, u, ids in history:
        data["name_history"].append({
            "date": d,
            "username": u,
            "id": re.findall(r"\d+", ids)[0]
        })

    return data

# ================== TELEGRAM INTERACTION ==================
async def send_and_wait(username: str):
    if username.startswith("@"):
        username = username[1:]

    sent = await tg_client.send_message(TARGET_BOT, f"t.me/{username}")

    start = time.time()
    while time.time() - start < 60:
        async for msg in tg_client.get_chat_history(TARGET_BOT, limit=5):
            if msg.id > sent.id and msg.text:
                return parse_bot_response(msg.text)
        await asyncio.sleep(2)

    return {"success": False, "error": "No reply from bot"}

# ================== FLASK ==================
app = Flask(__name__)

@app.route("/check")
def check():
    username = request.args.get("username")
    if not username:
        return jsonify({"success": False, "error": "username missing"}), 400

    future = asyncio.run_coroutine_threadsafe(
        send_and_wait(username),
        tg_loop
    )

    try:
        return jsonify(future.result(timeout=70))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ================== RUNNER ==================
async def main():
    global tg_loop
    tg_loop = asyncio.get_event_loop()

    await tg_client.start()
    print("✅ Telegram client started")

    def run_flask():
        port = int(os.environ.get("PORT", 8000))
        app.run(host="0.0.0.0", port=port)

    Thread(target=run_flask).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
