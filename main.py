import asyncio
import re
import time
from threading import Thread
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.errors import FloodWait

# --- Telegram config ---
API_ID = 29969433
API_HASH = "884f9ffa4e8ece099cccccade82effac"
PHONE_NUMBER = "+919214045762"
TARGET_BOT = "@telebrecheddb_bot"

# --- Client setup ---
tg_client = Client(
    "temp_session",
    api_id= os.getenv("API_ID") ,
    api_hash= os.getenv("API_HASH"),
    phone_number= os.getenv("PHONE_NUMBER"),
    no_updates=True
)

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


# --- Main send + receive logic ---
async def send_and_wait(username: str) -> dict:
    username = username.strip()
    if username.startswith("@"):
        username = username[1:]
    message_to_send = f"t.me/{username}"

    try:
        sent = await tg_client.send_message(TARGET_BOT, message_to_send)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        sent = await tg_client.send_message(TARGET_BOT, message_to_send)
    except Exception as e:
        return {"success": False, "error": f"Error contacting bot: {e}"}

    reply_text = None
    start_time = time.time()

    while time.time() - start_time < 60:
        async for msg in tg_client.get_chat_history(TARGET_BOT, limit=10):
            if msg.id > sent.id and not msg.outgoing and msg.text:
                reply_text = msg.text
                break
        if reply_text:
            break
        await asyncio.sleep(2)

    if not reply_text:
        return {"success": False, "error": "No reply received from bot after 60s."}

    return parse_bot_response(reply_text)


# --- Flask setup ---
app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True


@app.route("/check")
def check():
    username = request.args.get("username")
    if not username:
        return jsonify({"success": False, "error": "Missing 'username' parameter"}), 400

    try:
        future = asyncio.run_coroutine_threadsafe(send_and_wait(username), tg_loop)
        result = future.result(timeout=70)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_free_port(default=8000):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("", default))
        port = s.getsockname()[1]
    except OSError:
        s.bind(("", 0))
        port = s.getsockname()[1]
    finally:
        s.close()
    return port


# --- Main runner ---
async def main():
    global tg_loop
    tg_loop = asyncio.get_event_loop()
    await tg_client.start()
    print("✅ Telegram client started successfully")

    port = get_free_port(8000)
    print(f"🌐 API running at: http://127.0.0.1:{port}/check?username=@RiteshYadav8650")

    def run_flask():
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    Thread(target=run_flask, daemon=True).start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
