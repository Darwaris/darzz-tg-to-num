import os
import asyncio
import re
import time
import random
from threading import Thread
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded
from queue import Queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Telegram config (multiple accounts for rotation) ---
ACCOUNTS = [
    {
        "api_id": os.getenv("API_ID_1", "29969433"),
        "api_hash": os.getenv("API_HASH_1", "884f9ffa4e8ece099cccccade82effac"),
        "phone_number": os.getenv("PHONE_1", "+919214045762"),
        "session_name": "session_1"
    },
    # Add more accounts here in the same format for rotation
]

TARGET_BOT = "@telebrecheddb_bot"

# --- Queue for request handling ---
request_queue = Queue()
clients = []
current_client_index = 0
lock = asyncio.Lock()

# --- Initialize all Telegram clients ---
async def init_clients():
    for acc in ACCOUNTS:
        client = Client(
            acc["session_name"],
            api_id=acc["api_id"],
            api_hash=acc["api_hash"],
            phone_number=acc["phone_number"],
            no_updates=True
        )
        try:
            await client.start()
            clients.append(client)
            print(f"✅ Client {acc['phone_number']} started")
        except SessionPasswordNeeded:
            print(f"❌ 2FA required for {acc['phone_number']}")
        except Exception as e:
            print(f"❌ Failed to start {acc['phone_number']}: {e}")
    if not clients:
        raise Exception("No Telegram clients available")

# --- Rotate clients to avoid flood limits ---
async def get_client():
    global current_client_index
    async with lock:
        client = clients[current_client_index]
        current_client_index = (current_client_index + 1) % len(clients)
        return client

# --- Parser for bot text ---
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

    username_match = re.search(r"t\.me/([A-Za-z0-9_]+)", text)
    if username_match:
        data["username"] = username_match.group(1)

    id_match = re.search(r"ID[:： ]+(\d+)", text)
    if id_match:
        data["id"] = id_match.group(1)

    phone_match = re.search(r"Phone[:： ]+(\d+)", text)
    if phone_match:
        data["phone"] = phone_match.group(1)

    viewed_match = re.search(r"Viewed by[:： ]*(\d+)", text)
    if viewed_match:
        data["viewed_by"] = int(viewed_match.group(1))

    history_match = re.findall(r"(\d{2}\.\d{2}\.\d{4}) → @([\w\d_]+),\s*([\w\d, ]+)", text)
    for d, u, i in history_match:
        ids = re.findall(r"\d+", i)
        data["name_history"].append({
            "date": d,
            "username": u,
            "id": ids[0] if ids else None
        })

    return data

# --- Main send + receive logic with retry and rotation ---
async def send_and_wait(username: str, max_retries=3) -> dict:
    username = username.strip()
    if username.startswith("@"):
        username = username[1:]
    message_to_send = f"t.me/{username}"

    for attempt in range(max_retries):
        try:
            client = await get_client()
            sent = await client.send_message(TARGET_BOT, message_to_send)
            reply_text = None
            start_time = time.time()

            while time.time() - start_time < 60:
                async for msg in client.get_chat_history(TARGET_BOT, limit=10):
                    if msg.id > sent.id and not msg.outgoing and msg.text:
                        reply_text = msg.text
                        break
                if reply_text:
                    break
                await asyncio.sleep(2)

            if not reply_text:
                continue  # Retry with another client

            return parse_bot_response(reply_text)

        except FloodWait as e:
            wait_time = e.value + random.randint(5, 15)
            print(f"⚠️ Flood wait {wait_time}s, rotating client")
            await asyncio.sleep(wait_time)
            continue
        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(3)

    return {"success": False, "error": "Max retries exceeded"}

# --- Flask setup ---
app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

@app.route("/check")
def check():
    username = request.args.get("username")
    if not username:
        return jsonify({"success": False, "error": "Missing 'username' parameter"}), 400

    try:
        # Run the async function in the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_and_wait(username))
        loop.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok", "clients": len(clients)})

# --- Main runner ---
async def main():
    await init_clients()
    if not clients:
        print("❌ No active clients. Exiting.")
        return

    port = int(os.getenv("PORT", 8000))
    print(f"✅ {len(clients)} Telegram clients active")
    print(f"🌐 API running at: http://0.0.0.0:{port}/check?username=@example")

    def run_flask():
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Keep the asyncio loop running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
