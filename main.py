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

# --- Telegram config ---
ACCOUNTS = [
    {
        "api_id": os.getenv("API_ID_1"),
        "api_hash": os.getenv("API_HASH_1"),
        "phone_number": os.getenv("PHONE_1"),
        "session_name": "session_1"
    },
]

TARGET_BOT = "@telebrecheddb_bot"

# Global variables
clients = []
current_client_index = 0
lock = asyncio.Lock()

# --- Initialize Telegram client ---
async def init_clients():
    for acc in ACCOUNTS:
        client = Client(
            acc["session_name"],
            api_id=int(acc["api_id"]),
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
        print("⚠️ No Telegram clients available - Running in mock mode")

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

# --- Send message logic ---
async def send_and_wait(username: str, max_retries=2) -> dict:
    if not clients:
        return {"success": False, "error": "No Telegram clients initialized"}
    
    username = username.strip()
    if username.startswith("@"):
        username = username[1:]
    message_to_send = f"t.me/{username}"

    for attempt in range(max_retries):
        try:
            async with lock:
                client = clients[current_client_index]
            
            sent = await client.send_message(TARGET_BOT, message_to_send)
            reply_text = None
            start_time = time.time()

            while time.time() - start_time < 30:  # Reduced timeout for Render
                async for msg in client.get_chat_history(TARGET_BOT, limit=10):
                    if msg.id > sent.id and not msg.outgoing and msg.text:
                        reply_text = msg.text
                        break
                if reply_text:
                    break
                await asyncio.sleep(1)

            if reply_text:
                return parse_bot_response(reply_text)
                
        except FloodWait as e:
            print(f"⚠️ Flood wait {e.value}s")
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)

    return {"success": False, "error": "Max retries exceeded"}

# --- Flask setup ---
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <h1>Telegram Phone Finder API</h1>
    <p>Use: /check?username=@username</p>
    <p>Example: <a href="/check?username=@RiteshYadav8650">/check?username=@RiteshYadav8650</a></p>
    <p>Active Clients: {}</p>
    """.format(len(clients))

@app.route('/check')
def check():
    username = request.args.get('username')
    if not username:
        return jsonify({"success": False, "error": "Missing username parameter"}), 400
    
    try:
        # Create new event loop for each request (Render compatible)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_and_wait(username))
        loop.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "clients": len(clients)})

# --- Start everything ---
def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_clients())

# Start Telegram client in background thread
Thread(target=start_bot, daemon=True).start()

# For Render - Simple run
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"Starting server on port {port}")
    print(f"Active Telegram clients: {len(clients)}")
    app.run(host='0.0.0.0', port=port, debug=False)
