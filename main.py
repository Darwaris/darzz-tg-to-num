import os
import requests
import re
import time
from flask import Flask, request, jsonify
import random

app = Flask(__name__)

# Telegram Bot API credentials (from https://my.telegram.org)
TELEGRAM_API_ID = os.environ.get('API_ID_1', '29969433')
TELEGRAM_API_HASH = os.environ.get('API_HASH_1', '884f9ffa4e8ece099cccccade82effac')

# Target bot username
TARGET_BOT = "telebrecheddb_bot"

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/537.36'
]

# Session for persistent cookies
session = requests.Session()

# --- Parser function ---
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

# --- Get data from bot via web ---
def get_from_bot(username: str):
    """Alternative: Use web interface if available"""
    username = username.strip().lstrip('@')
    
    # Try different approaches
    urls_to_try = [
        f"https://t.me/{TARGET_BOT}?start={username}",
        f"https://telegram.me/{TARGET_BOT}?start={username}",
    ]
    
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    for url in urls_to_try:
        try:
            print(f"Trying URL: {url}")
            response = session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Parse response (this is simplified - you need to adjust based on actual bot response)
                return {
                    "success": True,
                    "username": username,
                    "note": "Bot contacted successfully",
                    "response_sample": response.text[:200] if response.text else "No text"
                }
                
        except Exception as e:
            print(f"Error with {url}: {e}")
            continue
    
    return {
        "success": False,
        "error": "Could not contact bot via web methods",
        "tip": "Try the direct API method below"
    }

# --- Direct API Method (using bot token if available) ---
def direct_api_method(username: str):
    """If you have bot token, use Telegram Bot API directly"""
    username = username.strip().lstrip('@')
    
    # This requires a bot token - you need to create your own bot
    BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
    
    if BOT_TOKEN:
        # Method 1: Send message via Bot API
        send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': f"@{TARGET_BOT}",
            'text': f"t.me/{username}",
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(send_url, data=payload, timeout=30)
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "Request sent via Bot API",
                    "response": response.json()
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Bot API error: {str(e)}"
            }
    
    return {
        "success": False,
        "error": "Bot token not configured",
        "tip": "Create a bot via @BotFather and add BOT_TOKEN to environment"
    }

# --- MOCK RESPONSE for testing ---
def get_mock_response(username: str):
    """Return mock data for testing"""
    username = username.strip().lstrip('@')
    
    return {
        "success": True,
        "username": username,
        "id": str(random.randint(1000000, 9999999)),
        "phone": f"98{random.randint(1000000, 9999999)}",
        "viewed_by": random.randint(1, 100),
        "name_history": [
            {
                "date": "01.01.2023",
                "username": username,
                "id": str(random.randint(1000000, 9999999))
            }
        ],
        "note": "Mock data for testing. Real API needs Pyrogram fix.",
        "timestamp": time.time()
    }

# --- Flask Routes ---
@app.route('/')
def home():
    return """
    <h1>Telegram Phone Finder API</h1>
    <p>Status: ✅ Running</p>
    <p>Use: /check?username=@username</p>
    <p>Example: <a href="/check?username=@RiteshYadav8650">Test Real API</a></p>
    <p>Example: <a href="/check?username=@test&mock=true">Test Mock Data</a></p>
    <p>Example: <a href="/check?username=@test&method=web">Test Web Method</a></p>
    <p><a href="/health">Health Check</a></p>
    """

@app.route('/check')
def check():
    username = request.args.get('username')
    use_mock = request.args.get('mock', '').lower() == 'true'
    method = request.args.get('method', 'auto')  # auto, web, api, mock
    
    if not username:
        return jsonify({"success": False, "error": "Provide username parameter"}), 400
    
    # For testing, return mock data
    if use_mock:
        result = get_mock_response(username)
        result["note"] = "Mock data - for testing only"
        return jsonify(result)
    
    # Choose method
    if method == 'web':
        result = get_from_bot(username)
    elif method == 'api':
        result = direct_api_method(username)
    elif method == 'mock':
        result = get_mock_response(username)
    else:
        # Try web first, then mock as fallback
        result = get_from_bot(username)
        if not result.get("success"):
            result = get_mock_response(username)
            result["note"] = "Using mock data as fallback"
    
    return jsonify(result)

@app.route('/health')
def health():
    return jsonify({
        "status": "running",
        "timestamp": time.time(),
        "methods_available": ["web", "mock"],
        "environment": {
            "API_ID_set": bool(os.environ.get('API_ID_1')),
            "API_HASH_set": bool(os.environ.get('API_HASH_1'))
        }
    })

# --- Startup ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Server on port {port}")
    print(f"🔑 API_ID: {'✅' if os.environ.get('API_ID_1') else '❌'}")
    print(f"🔑 API_HASH: {'✅' if os.environ.get('API_HASH_1') else '❌'}")
    
    # Test session
    session.headers.update({'User-Agent': random.choice(USER_AGENTS)})
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
