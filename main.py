"""
============================================================
Organic Reach Experts - Telegram Bot Runner for Render.com
Runs 24/7 on Render Free Web Service with HTTP health check
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

sys.stdout.reconfigure(encoding='utf-8')

# Bot Configuration
BOT_TOKEN = "9265054171:AAEMWAFtDgQRl6hQIiTObcaRx1NXleL2IR8"
BOT_NAME = "Organic Reach Experts"
BOT_USERNAME = "organic_reach_views_bot"
PANEL_URL = "https://organicreach.site.je/dashboard.php"
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")

ctx = ssl.create_default_context()
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ------------------------------------------------------------
# 1. Render HTTP Health Check Server
# ------------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        html = f"""
        <html>
        <head><title>{BOT_NAME} Bot Status</title></head>
        <body style="font-family:sans-serif;text-align:center;padding:50px;background:#0f172a;color:#f8fafc;">
            <h1 style="color:#38bdf8;">🤖 {BOT_NAME} Telegram Bot is Live!</h1>
            <p>Status: <strong>Running 24/7 on Render Cloud</strong></p>
            <p>Bot: <a href="https://t.me/{BOT_USERNAME}" style="color:#4ade80;">@{BOT_USERNAME}</a></p>
            <p style="color:#94a3b8;font-size:0.9rem;">Auto Daily Broadcast: Scheduled 09:00 AM IST</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        pass # Silence HTTP logs

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"🌐 Health server listening on 0.0.0.0:{port} (Render compatible)", flush=True)
    server.serve_forever()

# ------------------------------------------------------------
# 2. Local Database Initialization (SQLite)
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
        created_at TEXT,
        last_broadcast_date TEXT DEFAULT NULL
    )
    """)
    try:
        c.execute("ALTER TABLE bot_users ADD COLUMN last_broadcast_date TEXT DEFAULT NULL")
    except:
        pass

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

# ------------------------------------------------------------
# 3. Database Helpers
# ------------------------------------------------------------
def get_or_create_user(from_data, start_param=""):
    tg_id = from_data.get('id')
    if not tg_id:
        return None
    username = from_data.get('username')
    first_name = from_data.get('first_name', 'User')

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (tg_id,))
    row = c.fetchone()

    if row:
        if row['username'] != username or row['first_name'] != first_name:
            c.execute("UPDATE bot_users SET username = ?, first_name = ? WHERE telegram_id = ?", (username, first_name, tg_id))
            conn.commit()
        user_dict = dict(row)
        user_dict['username'] = username
        user_dict['first_name'] = first_name
        conn.close()
        return user_dict

    referrer_id = None
    if start_param:
        clean = start_param.lower().replace('ref', '').strip()
        try:
            r_id = int(clean)
            if r_id != tg_id:
                c.execute("SELECT telegram_id, credits, first_name FROM bot_users WHERE telegram_id = ?", (r_id,))
                ref_user = c.fetchone()
                if ref_user:
                    referrer_id = r_id
        except:
            pass

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    welcome_credits = 500
    c.execute("""
        INSERT INTO bot_users (telegram_id, username, first_name, credits, referrer_id, state, created_at)
        VALUES (?, ?, ?, ?, ?, 'idle', ?)
    """, (tg_id, username, first_name, welcome_credits, referrer_id, now_str))
    conn.commit()

    if referrer_id:
        reward = 500
        c.execute("UPDATE bot_users SET credits = credits + ? WHERE telegram_id = ?", (reward, referrer_id))
        conn.commit()

        c.execute("SELECT credits FROM bot_users WHERE telegram_id = ?", (referrer_id,))
        ref_new_bal = c.fetchone()[0]

        ref_notif = (
            "🎉 <b>Referral Bonus Credited!</b>\n\n"
            f"A new user (<b>{first_name}</b>) just started the bot using your invite link!\n"
            f"🎁 <b>Bonus Earned:</b> +500 Credits\n"
            f"💰 <b>New Available Balance:</b> {ref_new_bal:,} Credits"
        )
        tg_send_message(referrer_id, ref_notif, [
            [{"text": "💰 My Account & Credits", "callback_data": "menu_account"}],
            [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
        ])

    c.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (tg_id,))
    new_user = dict(c.fetchone())
    conn.close()
    return new_user

def update_user(tg_id, **kwargs):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [tg_id]
    c.execute(f"UPDATE bot_users SET {set_clause} WHERE telegram_id = ?", values)
    conn.commit()
    conn.close()

def get_user(tg_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bot_users WHERE telegram_id = ?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def record_order(tg_id, qty, link):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO bot_orders (telegram_id, service_id, link, quantity, credits_charged, status, created_at)
        VALUES (?, 1, ?, ?, ?, 'Processing', ?)
    """, (tg_id, link, qty, qty, now_str))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_user_orders(tg_id, limit=5):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bot_orders WHERE telegram_id = ? ORDER BY id DESC LIMIT ?", (tg_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

# ------------------------------------------------------------
# 4. Telegram API Client
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
        if "timed out" in err_str or "10054" in err_str or "temporarily unavailable" in err_str:
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

def tg_edit_message(chat_id, message_id, text, keyboard=None):
    params = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
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
# 5. Keyboards
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
            {"text": "📱 Visit Organic Reach Panel ↗", "url": PANEL_URL}
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
# 6. Daily Invite Broadcast Function
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

    print(f"📢 [{datetime.datetime.now().strftime('%H:%M:%S')}] Starting Daily Broadcast for {len(users)} users...", flush=True)
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
    print(f"✅ Daily Broadcast delivered to {count} users.", flush=True)
    return count

# ------------------------------------------------------------
# 7. Update Processor
# ------------------------------------------------------------
def process_update(update):
    if 'callback_query' in update:
        cq = update['callback_query']
        cb_id = cq['id']
        chat_id = cq['message']['chat']['id']
        msg_id = cq['message']['message_id']
        data = cq.get('data', '')
        from_u = cq['from']

        user = get_or_create_user(from_u)
        tg_answer_callback(cb_id)

        if data in ['menu_main', 'menu_account', 'menu_referral', 'menu_history', 'cancel_order']:
            update_user(user['telegram_id'], state='idle', temp_order_qty=0)
            user = get_user(user['telegram_id'])

        if data in ['menu_main', 'cancel_order']:
            text = f"✨ <b>Welcome to {BOT_NAME} Bot</b>\n\nManage your credits, place orders, and invite friends to earn more rewards from the panel below 👇"
            tg_edit_message(chat_id, msg_id, text, kb_main_menu())
            return

        if data == 'menu_account':
            bal = user['credits']
            text = (
                "👤 <b>Account Dashboard</b>\n\n"
                f"🆔 <b>User ID:</b> <code>{user['telegram_id']}</code>\n"
                f"💰 <b>Available Balance:</b> <b>{bal:,} Credits</b>"
            )
            tg_edit_message(chat_id, msg_id, text, kb_account())
            return

        if data == 'menu_daily_bonus':
            today = datetime.date.today().isoformat()
            if user.get('last_daily_bonus') == today:
                text = "⚠️ <b>Daily Bonus Already Claimed!</b>\n\nYou have already claimed your daily bonus today. Come back tomorrow for more free credits!"
            else:
                bonus = 100
                new_bal = user['credits'] + bonus
                update_user(user['telegram_id'], credits=new_bal, last_daily_bonus=today)
                text = "🎁 <b>Daily Bonus Claimed Successfully!</b>\n\nYou received <b>+100 credits</b>. Come back tomorrow for more!"
            tg_edit_message(chat_id, msg_id, text, kb_back())
            return

        if data == 'menu_order_select':
            text = (
                "📦 <b>Select Order Quantity</b>\n\n"
                "Choose one of the standard packages below or enter a custom amount (Minimum: <b>100</b>):"
            )
            tg_edit_message(chat_id, msg_id, text, kb_packages())
            return

        if data.startswith('order_qty_'):
            qty_str = data.replace('order_qty_', '')
            if qty_str == 'custom':
                update_user(user['telegram_id'], state='waiting_for_custom_qty')
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

            update_user(user['telegram_id'], state='waiting_for_link', temp_order_qty=qty)
            text = (
                "🔗 <b>Send Your Instagram Link</b>\n\n"
                f"Selected Quantity: <b>{qty:,} Reels Views</b>\n"
                f"Credits Required: <b>{qty:,} Credits</b>\n\n"
                "Please send your public Instagram Reel or Video link now 👇\n"
                "<i>Example: https://www.instagram.com/reel/C3abc123/</i>"
            )
            tg_edit_message(chat_id, msg_id, text, [
                [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
            ])
            return

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

        if data == 'menu_history':
            orders = get_user_orders(user['telegram_id'], limit=5)
            text = "📜 <b>Order History</b>\n\n"
            if not orders:
                text += "You haven't placed any orders yet!\nClick <b>Place New Order</b> to boost your Instagram reels."
            else:
                for ord in orders:
                    text += f"📦 <b>#{ord['id']}</b> | <b>{ord['quantity']:,} Views</b>\n"
                    text += f"Status: <b>{ord['status']}</b> | Date: <code>{ord['created_at']}</code>\n"
                    text += f"Link: <a href=\"{ord['link']}\">View Link</a>\n\n"
            tg_edit_message(chat_id, msg_id, text, kb_back())
            return

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

        if raw_text.startswith('/start') or raw_text.lower() == 'menu':
            update_user(user['telegram_id'], state='idle', temp_order_qty=0)
            text = f"✨ <b>Welcome to {BOT_NAME} Bot</b>\n\nManage your credits, place orders, and invite friends to earn more rewards from the panel below 👇"
            tg_send_message(chat_id, text, kb_main_menu())
            return

        if user['state'] == 'waiting_for_custom_qty':
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

            update_user(user['telegram_id'], state='waiting_for_link', temp_order_qty=qty)
            text = (
                "🔗 <b>Send Your Instagram Link</b>\n\n"
                f"Selected Quantity: <b>{qty:,} Reels Views</b>\n"
                f"Credits Required: <b>{qty:,} Credits</b>\n\n"
                "Please send your public Instagram Reel or Video link now 👇\n"
                "<i>Example: https://www.instagram.com/reel/C3abc123/</i>"
            )
            tg_send_message(chat_id, text, [
                [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
            ])
            return

        if user['state'] == 'waiting_for_link':
            link = raw_text
            if not link or ('http://' not in link and 'https://' not in link) or 'instagram.com' not in link:
                tg_send_message(chat_id, "⚠️ <b>Invalid Instagram Link!</b>\nPlease provide a full Instagram Reel or Post URL starting with <code>https://www.instagram.com/reel/</code>:", [
                    [{"text": "❌ Cancel", "callback_data": "cancel_order"}]
                ])
                return

            qty = user['temp_order_qty'] or 100
            if qty < 100:
                qty = 100

            if user['credits'] < qty:
                tg_send_message(chat_id, "❌ <b>Insufficient Credits!</b> You do not have enough credits to complete this order.", [
                    [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
                ])
                update_user(user['telegram_id'], state='idle', temp_order_qty=0)
                return

            new_bal = user['credits'] - qty
            update_user(user['telegram_id'], credits=new_bal, state='idle', temp_order_qty=0)

            order_id = record_order(user['telegram_id'], qty, link)

            success_text = (
                "✅ <b>Order Placed Successfully!</b>\n\n"
                f"📦 <b>Order ID:</b> #{order_id}\n"
                "⚡ <b>Service:</b> Instagram Reels Views\n"
                f"🔢 <b>Quantity:</b> {qty:,} Views\n"
                f"💰 <b>Credits Deducted:</b> {qty:,}\n"
                f"💳 <b>Remaining Balance:</b> {new_bal:,} Credits\n"
                f"🔗 <b>Target:</b> {link}\n\n"
                "🚀 <i>Your views delivery has started and will be delivered shortly!</i>"
            )
            tg_send_message(chat_id, success_text, [
                [{"text": "📦 Place Another Order", "callback_data": "menu_order_select"}],
                [{"text": "📜 Order History", "callback_data": "menu_history"}],
                [{"text": "🏠 Main Menu", "callback_data": "menu_main"}]
            ])
            return

        text = f"✨ <b>Welcome to {BOT_NAME} Bot</b>\n\nManage your credits, place orders, and invite friends to earn more rewards from the panel below 👇"
        tg_send_message(chat_id, text, kb_main_menu())

# ------------------------------------------------------------
# 8. Main Entrypoint
# ------------------------------------------------------------
def main():
    # 1. Start HTTP health server in background thread for Render
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    print("=" * 60)
    print(f"🤖 {BOT_NAME} Telegram Bot Runner (Render Cloud Mode)")
    print(f"🤖 Connected as @{BOT_USERNAME}")
    print(f"🔗 Bot Link: https://t.me/{BOT_USERNAME}")
    print(f"⏰ Daily Invite Broadcast: Scheduled 09:00 AM IST")
    print("=" * 60)

    tg_request("deleteWebhook")

    offset = 0
    last_broadcast_check = 0
    print("📡 Listening for updates in cloud... (Active)", flush=True)

    while True:
        now_ts = time.time()
        if now_ts - last_broadcast_check > 900:
            last_broadcast_check = now_ts
            if datetime.datetime.now().hour >= 9:
                try:
                    send_daily_invite_broadcast(force=False)
                except Exception as b_err:
                    print(f"⚠️ Broadcast error: {b_err}", flush=True)

        try:
            res = tg_request("getUpdates", {"offset": offset, "timeout": 15, "limit": 50})
            if res.get('ok') and res.get('result'):
                for upd in res['result']:
                    offset = upd['update_id'] + 1
                    try:
                        process_update(upd)
                    except Exception as err:
                        print(f"⚠️ Process update error: {err}", flush=True)
            time.sleep(0.2)
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    main()
