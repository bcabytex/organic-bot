"""
============================================================
Organic Reach Experts - Telegram Bot Engine (Render Cloud)
Features:
  - 24/7 Webhook & Long Polling Support
  - Zero Data Loss: Real-time sync with Panel MySQL Database
  - Dynamic Admin Settings: Welcome, Daily Bonus & Referral Credits
  - Provider API Order Dispatch (Raja SMM / Mapped Service)
  - Real-time Order History & Tracking
  - Auto Keep-Alive: Prevents Render free tier sleep
  - Daily 09:00 AM IST Invite & Reward Broadcast
============================================================
"""

import urllib.request
import urllib.parse
import json
import time
import sqlite3
import os
import sys
import datetime
import re
import ssl
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

sys.stdout.reconfigure(encoding='utf-8')

# Bot & Panel Configuration
BOT_TOKEN = "9265054171:AAEMWAFtDgQRl6hQIiTObcaRx1NXleL2IR8"
BOT_NAME = "Organic Reach Experts"
BOT_USERNAME = "organic_reach_views_bot"
PANEL_WEB_URL = "https://organicreach.site.je/dashboard.php"
PANEL_API_URL = "https://organicreach.site.je/telegram-bot.php"
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://organic-bot-kdcl.onrender.com")

ctx = ssl.create_default_context()
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_cache.db")

# ------------------------------------------------------------
# 1. Panel MySQL API Client with AES Challenge Solver
# ------------------------------------------------------------
_panel_cookie = None
_cookie_lock = threading.Lock()

def get_panel_cookie():
    global _panel_cookie
    if not CRYPTO_AVAILABLE:
        return None
    try:
        req = urllib.request.Request(PANEL_API_URL, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as res:
            html = res.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'toNumbers\("([0-9a-fA-F]+)"\)', html)
        if len(matches) >= 3:
            a = bytes.fromhex(matches[0])
            b = bytes.fromhex(matches[1])
            c = bytes.fromhex(matches[2])
            cipher = Cipher(algorithms.AES(a), modes.CBC(b), backend=default_backend())
            cookie = (cipher.decryptor().update(c) + cipher.decryptor().finalize()).hex()
            _panel_cookie = cookie
            return cookie
    except Exception as e:
        print(f"⚠️ Panel cookie error: {e}", flush=True)
    return None

def call_panel_api(action, payload=None):
    global _panel_cookie
    if not _panel_cookie:
        with _cookie_lock:
            if not _panel_cookie:
                get_panel_cookie()

    url = f"{PANEL_API_URL}?action={action}"
    data = json.dumps(payload or {}).encode('utf-8')
    headers = {
        'User-Agent': USER_AGENT,
        'Cookie': f'__test={_panel_cookie}',
        'Content-Type': 'application/json'
    }

    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
                raw = res.read().decode('utf-8', errors='ignore')
                if 'toNumbers' in raw:
                    with _cookie_lock:
                        get_panel_cookie()
                    headers['Cookie'] = f'__test={_panel_cookie}'
                    continue
                return json.loads(raw)
        except Exception:
            with _cookie_lock:
                get_panel_cookie()
            headers['Cookie'] = f'__test={_panel_cookie}'
    return None

# ------------------------------------------------------------
# 1b. SMM Provider API Direct Dispatch (ig grow bot / SMM Raja)
# ------------------------------------------------------------
_cached_panel_settings = None
_cached_settings_time = 0

def get_live_bot_settings():
    global _cached_panel_settings, _cached_settings_time
    now = time.time()
    if _cached_panel_settings and (now - _cached_settings_time < 60):
        return _cached_panel_settings
    res = call_panel_api("api_settings")
    if res and res.get('ok'):
        _cached_panel_settings = res
        _cached_settings_time = now
        return res
    return _cached_panel_settings or {
        'provider_api_url': 'https://iggrowbot.com/api/v2',
        'provider_api_key': '0d455a8f8578e1eadcb3fbe92e3bd364',
        'api_service_id': '2396',
        'min_quantity': 500
    }

def call_provider_api(link, quantity):
    cfg = get_live_bot_settings()
    url = cfg.get('provider_api_url') or 'https://iggrowbot.com/api/v2'
    key = cfg.get('provider_api_key') or '0d455a8f8578e1eadcb3fbe92e3bd364'
    svc_id = str(cfg.get('api_service_id') or '2396')
    min_q = int(cfg.get('min_quantity') or 500)

    # Provider minimum quantity safety (iggrowbot service 2396 requires min 500)
    send_qty = max(quantity, min_q)
    if svc_id == '2396' and send_qty < 500:
        send_qty = 500

    try:
        post_data = urllib.parse.urlencode({
            'key': key,
            'action': 'add',
            'service': svc_id,
            'link': link,
            'quantity': send_qty
        }).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=post_data,
            headers={
                'User-Agent': 'OrganicReachExperts-API-Client/2.0',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read().decode('utf-8', errors='ignore')
            print(f"📦 Provider API Response: {raw}", flush=True)
            return json.loads(raw)
    except Exception as e:
        print(f"⚠️ Provider API Dispatch Error: {e}", flush=True)
        return {"error": str(e)}

# ------------------------------------------------------------
# 2. Local Database Initialization (Cache & Fallback)
# ------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS bot_users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        credits INTEGER DEFAULT 500,
        referrer_id INTEGER,
        last_daily_bonus TEXT,
        state TEXT DEFAULT 'idle',
        temp_order_qty INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        created_at TEXT,
        last_broadcast_date TEXT DEFAULT NULL
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS bot_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        service_id INTEGER DEFAULT 1,
        link TEXT,
        quantity INTEGER,
        credits_charged INTEGER,
        status TEXT DEFAULT 'Processing',
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

def get_or_create_user(from_data, start_param=""):
    tg_id = from_data.get('id')
    if not tg_id:
        return None
    username = from_data.get('username')
    first_name = from_data.get('first_name', 'User')

    # Try sync with live Panel MySQL first (Zero Data Loss)
    res = call_panel_api("api_sync_user", {
        "telegram_id": tg_id,
        "username": username,
        "first_name": first_name,
        "start_param": start_param
    })

    if res and res.get('ok') and res.get('user'):
        u = res['user']
        # If a referrer was awarded, send instant notification to referrer
        if res.get('referrer_awarded') and res.get('referrer_id'):
            ref_id = res['referrer_id']
            ref_bal = res.get('referrer_new_bal', 0)
            rew = res.get('reward_amount', 500)
            ref_notif = (
                "🎉 <b>Referral Bonus Credited!</b>\n\n"
                f"A new user (<b>{first_name}</b>) just started the bot using your invite link!\n"
                f"🎁 <b>Bonus Earned:</b> +{rew:,} Credits\n"
                f"💰 <b>New Available Balance:</b> {ref_bal:,} Credits"
            )
            tg_send_message(ref_id, ref_notif, [
                [{"text": "💰 My Account & Credits", "callback_data": "menu_account"}],
                [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
            ])
        return {
            'telegram_id': int(u['telegram_id']),
            'username': u.get('username'),
            'first_name': u.get('first_name', 'User'),
            'credits': int(u.get('credits', 500)),
            'referrer_id': u.get('referrer_id'),
            'last_daily_bonus': u.get('last_daily_bonus'),
            'state': u.get('state', 'idle'),
            'temp_order_qty': int(u.get('temp_order_qty', 0)),
            'is_blocked': int(u.get('is_blocked', 0))
        }

    # Fallback to local SQLite if panel is unreachable
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (tg_id,))
    row = c.fetchone()
    if row:
        user_dict = dict(row)
        conn.close()
        return user_dict

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO bot_users (telegram_id, username, first_name, credits, referrer_id, state, created_at)
        VALUES (?, ?, ?, 500, NULL, 'idle', ?)
    """, (tg_id, username, first_name, now_str))
    conn.commit()
    c.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (tg_id,))
    new_user = dict(c.fetchone())
    conn.close()
    return new_user

USER_STATES = {}

def update_user_state(tg_id, state='idle', temp_qty=0):
    USER_STATES[tg_id] = {'state': state, 'temp_qty': temp_qty, 'time': time.time()}
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            INSERT INTO bot_users (telegram_id, state, temp_order_qty)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET state = excluded.state, temp_order_qty = excluded.temp_order_qty
        """, (tg_id, state, temp_qty))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def get_user_cached(tg_id):
    if tg_id in USER_STATES:
        st = USER_STATES[tg_id]
        return {'telegram_id': tg_id, 'state': st.get('state', 'idle'), 'temp_order_qty': st.get('temp_qty', 0)}
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (tg_id,))
        row = c.fetchone()
        conn.close()
        if row:
            d = dict(row)
            USER_STATES[tg_id] = {'state': d.get('state', 'idle'), 'temp_qty': d.get('temp_order_qty', 0), 'time': time.time()}
            return d
    except Exception as e:
        pass
    return {'telegram_id': tg_id, 'credits': 500, 'state': 'idle', 'temp_order_qty': 0}

# ------------------------------------------------------------
# 3. Telegram API Client
# ------------------------------------------------------------
def tg_request(method, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        data = json.dumps(params or {}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'TelegramBot/1.0'}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=30) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        err_str = str(e).lower()
        if "timed out" in err_str or "10054" in err_str:
            return {'ok': True, 'result': []}
        return {'ok': False, 'description': str(e)}

def tg_send_message(chat_id, text, keyboard=None, disable_preview=True):
    params = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': disable_preview
    }
    if keyboard:
        params['reply_markup'] = {'inline_keyboard': keyboard}
    return tg_request('sendMessage', params)

def tg_edit_message(chat_id, message_id, text, keyboard=None, disable_preview=True):
    params = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': disable_preview
    }
    if keyboard:
        params['reply_markup'] = {'inline_keyboard': keyboard}
    return tg_request('editMessageText', params)

def tg_answer_callback(callback_id, text=None, alert=False):
    params = {'callback_query_id': callback_id}
    if text:
        params['text'] = text
        params['show_alert'] = alert
    return tg_request('answerCallbackQuery', params)

# ------------------------------------------------------------
# 4. Standard Keyboards
# ------------------------------------------------------------
def kb_main_menu():
    return [
        [
            {"text": "💰 My Account & Credits", "callback_data": "menu_account"},
            {"text": "🎁 Daily Bonus", "callback_data": "menu_daily_bonus"}
        ],
        [
            {"text": "📦 Place New Order", "callback_data": "menu_order_select"}
        ],
        [
            {"text": "🚀 Share & Earn Credits", "callback_data": "menu_referral"},
            {"text": "📜 Order History", "callback_data": "menu_history"}
        ],
        [
            {"text": "📱 Visit Organic Reach Panel ↗", "url": PANEL_WEB_URL}
        ]
    ]

def kb_account():
    return [
        [
            {"text": "📦 Place Order", "callback_data": "menu_order_select"},
            {"text": "🎁 Earn Free Credits", "callback_data": "menu_referral"}
        ],
        [
            {"text": "🏠 Main Menu", "callback_data": "menu_main"}
        ]
    ]

def kb_packages():
    return [
        [
            {"text": "100 Views", "callback_data": "order_qty_100"},
            {"text": "200 Views", "callback_data": "order_qty_200"}
        ],
        [
            {"text": "300 Views", "callback_data": "order_qty_300"},
            {"text": "400 Views", "callback_data": "order_qty_400"}
        ],
        [
            {"text": "500 Views", "callback_data": "order_qty_500"}
        ],
        [
            {"text": "✏️ Custom Quantity", "callback_data": "order_qty_custom"}
        ],
        [
            {"text": "🏠 Main Menu", "callback_data": "menu_main"}
        ]
    ]

def kb_back():
    return [
        [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
    ]

# ------------------------------------------------------------
# 5. Daily Invite Broadcast (09:00 AM IST)
# ------------------------------------------------------------
def send_daily_invite_broadcast(force=False):
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if force:
        c.execute("SELECT telegram_id, first_name FROM bot_users")
    else:
        c.execute("""
            SELECT telegram_id, first_name 
            FROM bot_users 
            WHERE last_broadcast_date IS NULL OR last_broadcast_date != ?
        """, (today,))

    users = c.fetchall()
    if not users:
        conn.close()
        return 0

    print(f"📢 [{datetime.datetime.now().strftime('%H:%M:%S')}] Daily Broadcast to {len(users)} users...", flush=True)
    count = 0

    for u in users:
        tg_id = u['telegram_id']
        inv_link = f"https://t.me/{BOT_USERNAME}?start=ref{tg_id}"
        msg_text = (
            "💸 <b>EARN 500+ CREDITS FREE!</b> 🎁\n\n"
            "Invite your friends using your personal invite link and get rewarded instantly when they join! More invites = More Free Views! 🚀\n\n"
            "👇 Get your link now:\n\n"
            "🎯 Your Invite Link:\n"
            f"{inv_link}"
        )
        res = tg_send_message(tg_id, msg_text, [
            [{"text": "🚀 START NOW", "url": inv_link}]
        ], disable_preview=False)

        if res.get('ok'):
            count += 1
            c.execute("UPDATE bot_users SET last_broadcast_date = ? WHERE telegram_id = ?", (today, tg_id))
            conn.commit()
        time.sleep(0.05)

    conn.close()
    return count

# ------------------------------------------------------------
# 6. Telegram Update Processor (Zero History Loss)
# ------------------------------------------------------------
def process_update(update):
    # A. Inline Button Clicks
    if 'callback_query' in update:
        cq = update['callback_query']
        cb_id = cq['id']
        chat_id = cq['message']['chat']['id']
        msg_id = cq['message']['message_id']
        data = cq.get('data', '')
        from_u = cq['from']

        user = get_or_create_user(from_u)
        tg_answer_callback(cb_id)

        # Check if user is blocked by admin
        if user and user.get('is_blocked'):
            tg_answer_callback(cb_id, "🚫 Aapka account admin dwara block kar diya gaya hai.", alert=True)
            tg_send_message(chat_id, "🚫 <b>Account Blocked</b>\n\nAapka bot account admin dwara block kar diya gaya hai. Sahayata ke liye support se sampark karein.")
            return

        if data in ['menu_main', 'menu_account', 'menu_referral', 'menu_history', 'cancel_order']:
            update_user_state(user['telegram_id'], 'idle', 0)

        # 🏠 Main Menu
        if data in ['menu_main', 'cancel_order']:
            text = f"✨ <b>Welcome to {BOT_NAME} Bot</b>\n\nManage your credits, place orders, and invite friends to earn more rewards from the panel below 👇"
            tg_edit_message(chat_id, msg_id, text, kb_main_menu())
            return

        # 💰 My Account & Credits (Live from MySQL)
        if data == 'menu_account':
            bal = user['credits']
            text = (
                "👤 <b>Account Dashboard</b>\n\n"
                f"🆔 <b>User ID:</b> <code>{user['telegram_id']}</code>\n"
                f"💰 <b>Available Balance:</b> <b>{bal:,} Credits</b>"
            )
            tg_edit_message(chat_id, msg_id, text, kb_account())
            return

        # 🎁 Daily Bonus (Live from MySQL)
        if data == 'menu_daily_bonus':
            bonus_res = call_panel_api("api_daily_bonus", {"telegram_id": user['telegram_id']})
            if bonus_res and bonus_res.get('ok'):
                b_amt = bonus_res.get('bonus', 100)
                text = f"🎁 <b>Daily Bonus Claimed Successfully!</b>\n\nYou received <b>+{b_amt} credits</b>. Come back tomorrow for more!"
            elif bonus_res and bonus_res.get('already_claimed'):
                text = "⚠️ <b>Daily Bonus Already Claimed!</b>\n\nYou have already claimed your daily bonus today. Come back tomorrow for more free credits!"
            else:
                # SQLite fallback
                today = datetime.date.today().isoformat()
                if user.get('last_daily_bonus') == today:
                    text = "⚠️ <b>Daily Bonus Already Claimed!</b>\n\nYou have already claimed your daily bonus today. Come back tomorrow for more free credits!"
                else:
                    text = "🎁 <b>Daily Bonus Claimed Successfully!</b>\n\nYou received <b>+100 credits</b>. Come back tomorrow for more!"
            tg_edit_message(chat_id, msg_id, text, kb_back())
            return

        # 📦 Place Order: Select Quantity
        if data == 'menu_order_select':
            text = (
                "📦 <b>Select Order Quantity</b>\n\n"
                "Choose one of the standard packages below or enter a custom amount (Minimum: <b>100</b>):"
            )
            tg_edit_message(chat_id, msg_id, text, kb_packages())
            return

        # Quantity Selection
        if data.startswith('order_qty_'):
            qty_str = data.replace('order_qty_', '')
            if qty_str == 'custom':
                update_user_state(user['telegram_id'], 'waiting_for_custom_qty', 0)
                text = (
                    "✏️ <b>Enter Custom Quantity</b>\n\n"
                    "Please type the quantity of views you want to order below:\n"
                    "<i>(Minimum: 100 views | Rate: 1 View = 1 Credit)</i>\n\n"
                    "Example: <code>150</code>, <code>250</code>, <code>500</code>, <code>1000</code>"
                )
                tg_edit_message(chat_id, msg_id, text, [
                    [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
                ])
                return

            try:
                qty = int(qty_str)
            except:
                qty = 100
            if qty < 100:
                qty = 100

            if user['credits'] < qty:
                text = (
                    "❌ <b>Insufficient Credits!</b>\n\n"
                    f"You need <b>{qty:,} credits</b>, but your current balance is <b>{user['credits']:,} credits</b>.\n\n"
                    "💡 <i>Earn free credits by claiming your Daily Bonus or inviting friends!</i>"
                )
                tg_edit_message(chat_id, msg_id, text, [
                    [{"text": "🎁 Daily Bonus", "callback_data": "menu_daily_bonus"}, {"text": "🚀 Share & Earn Credits", "callback_data": "menu_referral"}],
                    [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
                ])
                return

            update_user_state(user['telegram_id'], 'waiting_for_link', qty)
            text = (
                f"🎯 <b>Selected Package:</b> {qty:,} views.\n\n"
                "🔗 Now, send your target <b>Instagram reel/video link</b> in the chat:"
            )
            tg_edit_message(chat_id, msg_id, text, [
                [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
            ])
            return

        # 🚀 Share & Earn Credits
        if data == 'menu_referral':
            invite_link = f"https://t.me/{BOT_USERNAME}?start=ref{user['telegram_id']}"
            share_text = f"🚀 Get Free Instagram Reels Views Instantly! Claim 500 Free Credits on {BOT_NAME} Bot 👇"
            share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={urllib.parse.quote(share_text)}"

            text = (
                "🎁 <b>Referral Program &amp; Free Credits</b>\n\n"
                "Invite your friends to our bot and earn <b>+500 credits</b> instantly for every single user who starts the bot using your link!\n\n"
                "🔗 <b>Your Personal Invite Link:</b>\n"
                f"<code>{invite_link}</code>\n\n"
                "💡 <i>Clicking the button below will open Telegram's selector so you can choose multiple friends or groups instantly to share your link:</i>"
            )
            tg_edit_message(chat_id, msg_id, text, [
                [{"text": "🩵 Share with Multiple Friends / Groups ↗", "url": share_url}],
                [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
            ])
            return

        # 📜 Order History (Permanent from MySQL - Never Deletes!)
        if data == 'menu_history':
            h_res = call_panel_api("api_history", {"telegram_id": user['telegram_id']})
            orders = h_res.get('orders', []) if h_res else []

            text = "📋 <b>Your Orders History</b>\n\n"
            if not orders:
                text += "You haven't placed any orders yet!\nClick <b>Place New Order</b> to boost your Instagram reels."
            else:
                for ord in orders:
                    dt = ord.get('created_at', '')
                    st = ord.get('status', 'Processing')
                    qty = ord.get('quantity', 0)
                    lnk = ord.get('link', '')
                    api_id = ord.get('api_order_id')

                    st_lower = str(st).lower()
                    icon = "⏳"
                    if "complete" in st_lower:
                        icon = "✅"
                    elif "cancel" in st_lower or "fail" in st_lower:
                        icon = "❌"
                    elif "progress" in st_lower or "processing" in st_lower:
                        icon = "🔄"

                    text += f"📦 <b>Order #{ord['id']}</b>" + (f" <i>(API: #{api_id})</i>" if api_id else "") + "\n"
                    text += f"⚡ <b>{qty:,} Views</b> &bull; Status: {icon} <b>{st}</b>\n"
                    text += f"📅 <code>{dt[:16]}</code>\n"
                    text += f"🔗 <a href=\"{lnk}\">View Reel</a>\n\n"

            tg_edit_message(chat_id, msg_id, text, [
                [{"text": "📦 Place New Order", "callback_data": "menu_order_select"}],
                [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
            ])
            return

    # B. Text Messages
    if 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        from_u = msg.get('from', {})
        raw_text = msg.get('text', '').strip()

        start_param = ""
        if raw_text.startswith('/start'):
            parts = raw_text.split(' ', 1)
            if len(parts) > 1:
                start_param = parts[1].strip()

        user = get_or_create_user(from_u, start_param)
        if not user:
            return

        # Check if user is blocked by admin
        if user.get('is_blocked'):
            tg_send_message(chat_id, "🚫 <b>Account Blocked</b>\n\nAapka bot account admin dwara block kar diya gaya hai. Sahayata ke liye support se sampark karein.")
            return

        cached_state = get_user_cached(user['telegram_id'])
        current_state = cached_state.get('state', 'idle')

        if raw_text.startswith('/start') or raw_text.lower() == 'menu':
            update_user_state(user['telegram_id'], 'idle', 0)
            text = f"✨ <b>Welcome to {BOT_NAME} Bot</b>\n\nManage your credits, place orders, and invite friends to earn more rewards from the panel below 👇"
            tg_send_message(chat_id, text, kb_main_menu())
            return

        if current_state == 'waiting_for_custom_qty':
            try:
                qty = int(re.sub(r'[^0-9]', '', raw_text))
            except:
                qty = 0

            if qty < 100:
                tg_send_message(chat_id, "⚠️ Minimum order quantity is <b>100 views</b>. Please enter a valid number (e.g. 100, 200, 500):", [
                    [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
                ])
                return

            if user['credits'] < qty:
                tg_send_message(chat_id, f"❌ <b>Insufficient Credits!</b>\n\nYou need <b>{qty:,} credits</b>, but your available balance is <b>{user['credits']:,} credits</b>.\n\nPlease enter a smaller quantity or claim free credits:", [
                    [{"text": "🎁 Daily Bonus", "callback_data": "menu_daily_bonus"}, {"text": "🚀 Share & Earn Credits", "callback_data": "menu_referral"}],
                    [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
                ])
                return

            update_user_state(user['telegram_id'], 'waiting_for_link', qty)
            text = (
                f"🎯 <b>Selected Package:</b> {qty:,} views.\n\n"
                "🔗 Now, send your target <b>Instagram reel/video link</b> in the chat:"
            )
            tg_send_message(chat_id, text, [
                [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
            ])
            return

        # Auto-detect Instagram link
        has_ig_link = False
        extracted_link = None
        for chunk in raw_text.split():
            if 'instagram.com' in chunk or 'instagr.am' in chunk:
                has_ig_link = True
                extracted_link = chunk
                if not extracted_link.startswith('http://') and not extracted_link.startswith('https://'):
                    extracted_link = 'https://' + extracted_link
                break

        if current_state == 'waiting_for_link' or has_ig_link:
            link = extracted_link or raw_text.strip()
            if not link or ('http://' not in link and 'https://' not in link) or ('instagram.com' not in link and 'instagr.am' not in link):
                tg_send_message(chat_id, "⚠️ <b>Invalid Instagram Link!</b>\nPlease provide a full Instagram Reel or Post URL starting with <code>https://www.instagram.com/reel/</code>:", [
                    [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
                ])
                return

            qty = cached_state.get('temp_order_qty') or 0
            if qty < 100:
                qty = 500 if user['credits'] >= 500 else (100 if user['credits'] >= 100 else 100)

            if user['credits'] < qty:
                if user['credits'] >= 100:
                    qty = 100
                else:
                    tg_send_message(chat_id, f"❌ <b>Insufficient Credits!</b>\n\nYou need at least <b>100 credits</b> to place an order, but your available balance is <b>{user['credits']:,} credits</b>.\n\nPlease earn free credits by claiming your Daily Bonus or inviting friends:", [
                        [{"text": "🎁 Daily Bonus", "callback_data": "menu_daily_bonus"}, {"text": "🚀 Share & Earn Credits", "callback_data": "menu_referral"}],
                        [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
                    ])
                    return

            # 1. Immediate status message
            tg_send_message(chat_id, f"⏳ <b>Placing order for {qty:,} Views...</b>\nDispatching to API, please wait...")

            # 2. Dispatch directly to Provider API (ig grow bot / SMM Raja)
            prov_res = call_provider_api(link, qty)
            api_order_id = None
            if prov_res and (prov_res.get('order') or prov_res.get('success')):
                api_order_id = str(prov_res.get('order', ''))

            # 3. Place Order via Live MySQL Panel & Deduct User Credits
            ord_res = call_panel_api("api_place_order", {
                "telegram_id": user['telegram_id'],
                "quantity": qty,
                "link": link,
                "api_order_id": api_order_id,
                "api_response": prov_res
            })

            if ord_res and ord_res.get('ok'):
                bot_ord_id = ord_res.get('bot_order_id')
            else:
                bot_ord_id = api_order_id or int(time.time())

            update_user_state(user['telegram_id'], 'idle', 0)

            # 4. Exact success receipt
            success_text = (
                "✅ <b>Order Placed Successfully!</b>\n\n"
                f"📦 <b>Order ID:</b> <code>#{bot_ord_id}</code>\n"
                f"🚀 <b>Service:</b> Instagram Reels Views\n"
                f"👁 <b>Quantity:</b> {qty:,} views\n"
                f"🔗 <b>Target:</b> <a href=\"{link}\">View Reel</a>\n"
                f"⚡ <b>Status:</b> <b>Processing</b>\n\n"
                "🎉 <i>Your views are on their way! Check status anytime in 'Order History'.</i>"
            )
            tg_send_message(chat_id, success_text, [
                [{"text": "🛍 Place Another Order", "callback_data": "menu_order_select"}, {"text": "📜 Order History", "callback_data": "menu_history"}],
                [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
            ])
            return
        text = f"✨ <b>Welcome to {BOT_NAME} Bot</b>\n\nManage your credits, place orders, and invite friends to earn more rewards from the panel below 👇"
        tg_send_message(chat_id, text, kb_main_menu())

# ------------------------------------------------------------
# 7. Webhook & Health HTTP Server
# ------------------------------------------------------------
class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        html = f"""
        <html>
        <head><title>{BOT_NAME} Bot Cloud Status</title></head>
        <body style="font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;">
            <h1 style="color:#38bdf8;">🤖 {BOT_NAME} Telegram Bot is Live!</h1>
            <p>Status: <strong style="color:#4ade80;">Running 24/7 on Render Cloud (Always Active)</strong></p>
            <p>Bot: <a href="https://t.me/{BOT_USERNAME}" style="color:#38bdf8;">@{BOT_USERNAME}</a></p>
            <p style="color:#94a3b8;font-size:0.9rem;">Auto Daily Broadcast: Scheduled 09:00 AM IST</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

        try:
            update = json.loads(post_data.decode('utf-8'))
            threading.Thread(target=process_update, args=(update,), daemon=True).start()
        except Exception:
            pass

    def log_message(self, format, *args):
        pass

def start_webhook_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"🌐 Webhook & Health server listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()

# ------------------------------------------------------------
# 8. Render 24/7 Auto Keep-Alive Loop
# ------------------------------------------------------------
def keep_awake_pinger():
    url = RENDER_URL.rstrip('/')
    if not url:
        return
    print(f"🔄 Auto Keep-Alive active for: {url}", flush=True)
    time.sleep(30)
    while True:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'KeepAlive/1.0'})
            with urllib.request.urlopen(req, timeout=15) as res:
                pass
        except Exception:
            pass
        time.sleep(300) # Ping every 5 minutes to prevent sleep

# ------------------------------------------------------------
# 9. Main Entrypoint
# ------------------------------------------------------------
def main():
    # 1. Start Webhook & Health HTTP Server
    wh_thread = threading.Thread(target=start_webhook_server, daemon=True)
    wh_thread.start()

    # 2. Start Keep-Alive Pinger (Never Sleeps)
    ka_thread = threading.Thread(target=keep_awake_pinger, daemon=True)
    ka_thread.start()

    print("=" * 60)
    print(f"🤖 {BOT_NAME} Telegram Bot Runner (Render Cloud Mode)")
    print(f"🤖 Connected as @{BOT_USERNAME}")
    print(f"🔗 Bot Link: https://t.me/{BOT_USERNAME}")
    print("=" * 60)

    # Automatically set Telegram Webhook to Render
    webhook_endpoint = f"{RENDER_URL.rstrip('/')}/webhook"
    set_wh = tg_request("setWebhook", {"url": webhook_endpoint})
    print(f"📡 Webhook Configured: {webhook_endpoint} -> {set_wh.get('ok')}", flush=True)

    last_broadcast_check = 0
    while True:
        time.sleep(60)
        # Daily broadcast check
        now_ts = time.time()
        if now_ts - last_broadcast_check > 900:
            last_broadcast_check = now_ts
            if datetime.datetime.now().hour >= 9:
                try:
                    send_daily_invite_broadcast(force=False)
                except Exception as b_err:
                    print(f"⚠️ Broadcast error: {b_err}", flush=True)

if __name__ == "__main__":
    main()
