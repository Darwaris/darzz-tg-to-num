import os
import asyncio
import re
import time
import sys
from threading import Thread
from flask import Flask, request, jsonify
from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded

app = Flask(__name__)

# Global Telegram client
tg_client = None
client_ready = False

# --- Parser function (same as before) ---
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

# --- Initialize Telegram Client ---
async def init_telegram():
    global tg_client, client_ready
    
    try:
        print("🔄 Initializing Telegram Client...")
        
        # Get credentials from environment
        api_id = os.environ.get('API_ID_1', '29969433')
        api_hash = os.environ.get('API_HASH_1', '884f9ffa4e8ece099cccccade82effac')
        phone = os.environ.get('PHONE_1', '+919214045762')
        
        print(f"📱 Using phone: {phone}")
        
        # Create client
        tg_client = Client(
            "render_session",
            api_id=int(api_id),
            api_hash=api_hash,
            phone_number=phone,
            no_updates=True
        )
        
        # Start client
        await tg_client.start()
        print("✅ Telegram Client Started Successfully!")
        client_ready = True
        
        # Keep client alive
        while True:
            await asyncio.sleep(3600)  # Keep alive loop
        
    except SessionPasswordNeeded:
        print("❌ 2FA Password Required! Please check your phone.")
        client_ready = False
    except FloodWait as e:
        print(f"⏳ FloodWait: Need to wait {e.value} seconds")
        client_ready = False
    except Exception as e:
        print(f"❌ Telegram Init Error: {type(e).__name__}: {e}")
        client_ready = False

# --- Start Telegram in background ---
def start_telegram_background():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(init_telegram())
    except KeyboardInterrupt:
        pass
    finally:
        if tg_client and tg_client.is_connected:
            loop.run_until_complete(tg_client.stop())
        loop.close()

# --- API Endpoint with retry ---
async def process_request(username: str):
    if not client_ready or not tg_client:
        return {"success": False, "error": "Telegram client not ready. Please wait 30 seconds and retry."}
    
    TARGET_BOT = "@telebrecheddb_bot"
    username = username.strip().lstrip('@')
    message_to_send = f"t.me/{username}"
    
    try:
        # Send message
        sent = await tg_client.send_message(TARGET_BOT, message_to_send)
        
        # Wait for response
        reply_text = None
        start_time = time.time()
        
        while time.time() - start_time < 45:  # 45 seconds timeout
            async for msg in tg_client.get_chat_history(TARGET_BOT, limit=15):
                if msg.id > sent.id and not msg.outgoing and msg.text:
                    reply_text = msg.text
                    break
            
            if reply_text:
                break
            await asyncio.sleep(2)
        
        if not reply_text:
            return {"success": False, "error": "Bot didn't reply within 45 seconds"}
        
        return parse_bot_response(reply_text)
        
    except FloodWait as e:
        return {"success": False, "error": f"Flood wait: Please try again after {e.value} seconds"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

# --- Flask Routes ---
@app.route('/')
def home():
    status = "✅ Ready" if client_ready else "⏳ Initializing..."
    return f"""
    <h1>Telegram Phone Finder API</h1>
    <p>Status: {status}</p>
    <p>Use: /check?username=@username</p>
    <p>Example: <a href="/check?username=@RiteshYadav8650">Test</a></p>
    <p><a href="/health">Health Check</a></p>
    """

@app.route('/check')
def check():
    username = request.args.get('username')
    if not username:
        return jsonify({"success": False, "error": "Provide username parameter"}), 400
    
    try:
        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(process_request(username))
        loop.close()
        
        if not result.get("success") and "not ready" in result.get("error", "").lower():
            # If client not ready, show waiting message
            return jsonify({
                "success": False, 
                "error": "Service is waking up. Please wait 30 seconds and try again.",
                "tip": "The first request after sleep takes time. Keep trying!"
            })
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500

@app.route('/health')
def health():
    return jsonify({
        "status": "ok" if client_ready else "starting",
        "client_ready": client_ready,
        "timestamp": time.time()
    })

@app.route('/logs')
def show_logs():
    """Debug endpoint to see client status"""
    return jsonify({
        "client_ready": client_ready,
        "python_version": sys.version,
        "env_vars_available": {
            "API_ID_1": bool(os.environ.get('API_ID_1')),
            "API_HASH_1": bool(os.environ.get('API_HASH_1')),
            "PHONE_1": bool(os.environ.get('PHONE_1'))
        }
    })

# --- Startup ---
if __name__ == '__main__':
    # Start Telegram client in background thread
    print("🚀 Starting Telegram Bot API...")
    
    # Check environment variables
    print("🔍 Checking environment...")
    print(f"API_ID_1: {'✅ Set' if os.environ.get('API_ID_1') else '❌ Missing'}")
    print(f"API_HASH_1: {'✅ Set' if os.environ.get('API_HASH_1') else '❌ Missing'}")
    print(f"PHONE_1: {'✅ Set' if os.environ.get('PHONE_1') else '❌ Missing'}")
    
    # Start Telegram in background
    telegram_thread = Thread(target=start_telegram_background, daemon=True)
    telegram_thread.start()
    
    # Give Telegram client time to initialize
    print("⏳ Waiting for Telegram client to initialize (20 seconds)...")
    time.sleep(20)
    
    # Start Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Starting Flask on port {port}")
    print(f"📞 Client Ready: {client_ready}")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
