import os
import time
import json
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_GROUP_ID = -1003593388052

WINDOW_SECONDS = 4 * 60 * 60
CLEANUP_SECONDS = 48 * 60 * 60
DATA_FILE = "data.json"

USERS = {}
ATTACHMENT_MAP = {}  # message_id -> uid

GROUP_MAP = {
    "A": "المجموعة أ",
    "B": "المجموعة ب",
    "C": "المجموعة ج",
}

# ================== حفظ / تحميل ==================

def load_data():
    global USERS, ATTACHMENT_MAP
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            USERS = {int(k): v for k, v in raw["users"].items()}
            ATTACHMENT_MAP = {int(k): v for k, v in raw["attachments"].items()}
    except:
        USERS = {}
        ATTACHMENT_MAP = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"users": USERS, "attachments": ATTACHMENT_MAP},
            f,
            ensure_ascii=False,
            indent=2
        )

# ================== أدوات ==================

def now():
    return int(time.time())

def fmt(ts):
    egypt_ts = ts + (2 * 60 * 60)
    return time.strftime("%I:%M %p", time.localtime(egypt_ts))

def cleanup():
    now_ts = now()
    removed = False

    for uid in list(USERS.keys()):
        if now_ts - USERS[uid]["start_time"] > CLEANUP_SECONDS:
            del USERS[uid]
            removed = True

    if removed:
        save_data()

def build_admin_message(uid):
    u = USERS[uid]

    msgs = "\n".join(
        f"{i+1}) [{fmt(t)}] {m}"
        for i, (t, m) in enumerate(u["messages"])
    )

    status = "🟢 #تم_الرد" if u["replied"] else "🟡 #لم_يتم_الرد"

    return (
        "📩 استفسار طالب\n\n"
        f"👤 الاسم: {u['name']}\n"
        f"🔗 @{u['username'] if u['username'] else 'غير متاح'}\n"
        f"🆔 ID: {uid}\n"
        f"👥 {u['group']}\n\n"
        "━━━━━━━━━━━━━━\n"
        "📨 الرسائل:\n"
        f"{msgs}\n"
        "━━━━━━━━━━━━━━\n"
        f"📌 الحالة: {status}\n\n"
        "↩️ للرد: اعمل Reply على الرسالة أو أي مرفق تابع لها"
    )

# ================== الطالب ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    uid = update.message.from_user.id
    ts = now()

    if uid not in USERS or ts - USERS[uid]["start_time"] > WINDOW_SECONDS:
        USERS[uid] = {
            "name": update.message.from_user.full_name,
            "username": update.message.from_user.username,
            "group": None,
            "start_time": ts,
            "messages": [],
            "admin_message_id": None,
            "replied": False,
            "reply_count": 0,
        }
        save_data()

        await update.message.reply_text(
            "أهلاً بيك 👋\n"
            "اختار مجموعتك علشان نقدر نساعدك أسرع 👇"
        )
        await send_group_buttons(update)

async def send_group_buttons(update: Update):
    keyboard = [[
        InlineKeyboardButton("أ", callback_data="group_A"),
        InlineKeyboardButton("ب", callback_data="group_B"),
        InlineKeyboardButton("ج", callback_data="group_C"),
    ]]
    await update.message.reply_text(
        "اختار مجموعتك:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("تم الاختيار ✅")

    uid = query.from_user.id
    ts = now()
    key = query.data.split("_")[1]

    if uid not in USERS:
        return

    USERS[uid]["group"] = GROUP_MAP[key]
    USERS[uid]["start_time"] = ts
    save_data()

    await query.edit_message_text(
        "تمام 👌\n"
        "ابعت استفسارك، ولو في صور أو ملفات ابعتها عادي."
    )

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    cleanup()

    user = update.message.from_user
    uid = user.id
    ts = now()

    if uid not in USERS:
        await start(update, context)
        return

    if ts - USERS[uid]["start_time"] > WINDOW_SECONDS:
        USERS[uid]["group"] = None
        USERS[uid]["messages"] = []
        USERS[uid]["admin_message_id"] = None
        USERS[uid]["replied"] = False
        USERS[uid]["reply_count"] = 0
        USERS[uid]["start_time"] = ts
        save_data()

        await send_group_buttons(update)
        return

    if USERS[uid]["group"] is None:
        return

    msg = update.message

    content = None
    sent_attachment_id = None

    if msg.text:
        content = msg.text

    elif msg.document or msg.photo or msg.voice:
        content = "📎 مرفق"
        sent = await context.bot.copy_message(
            chat_id=ADMIN_GROUP_ID,
            from_chat_id=uid,
            message_id=msg.message_id,
            reply_to_message_id=USERS[uid]["admin_message_id"]
        )
        sent_attachment_id = sent.message_id

    if content:
        USERS[uid]["messages"].append((ts, content))
        USERS[uid]["replied"] = False

        if USERS[uid]["admin_message_id"] is None:
            sent_main = await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=build_admin_message(uid),
            )
            USERS[uid]["admin_message_id"] = sent_main.message_id
        else:
            await context.bot.edit_message_text(
                chat_id=ADMIN_GROUP_ID,
                message_id=USERS[uid]["admin_message_id"],
                text=build_admin_message(uid),
            )

        if sent_attachment_id:
            ATTACHMENT_MAP[sent_attachment_id] = uid

        save_data()

        await update.message.reply_text(
            "✅ تم استلام استفسارك\n"
            "هيوصلك الرد هنا مباشرة."
        )

# ================== الأدمن ==================

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return
    if not update.message.reply_to_message:
        return

    cleanup()

    reply_to_id = update.message.reply_to_message.message_id
    uid = None

    for u_id, u in USERS.items():
        if u["admin_message_id"] == reply_to_id:
            uid = u_id
            break

    if reply_to_id in ATTACHMENT_MAP:
        uid = ATTACHMENT_MAP[reply_to_id]

    if not uid:
        return

    await context.bot.copy_message(
        chat_id=uid,
        from_chat_id=ADMIN_GROUP_ID,
        message_id=update.message.message_id,
    )

    USERS[uid]["reply_count"] += 1
    USERS[uid]["replied"] = True

    if USERS[uid]["reply_count"] % 2 == 0:
        await context.bot.send_message(
            chat_id=uid,
            text="📬 جالك رد بخصوص استفسارك 👆"
        )

    await context.bot.edit_message_text(
        chat_id=ADMIN_GROUP_ID,
        message_id=USERS[uid]["admin_message_id"],
        text=build_admin_message(uid),
    )

    await update.message.reply_text("✅ تم إرسال الرد للطالب")
    save_data()

# ================== داش بورد ==================

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return

    total = len(USERS)
    pending = sum(1 for u in USERS.values() if not u["replied"])
    answered = total - pending

    await update.message.reply_text(
        f"📊 لوحة التحكم – Cafeteria\n\n"
        f"📥 إجمالي الاستفسارات: {total}\n"
        f"🟡 لم يتم الرد: {pending}\n"
        f"🟢 تم الرد: {answered}\n\n"
        f"🔎 استخدم الشباك:\n"
        f"#لم_يتم_الرد\n"
        f"#تم_الرد"
    )

async def admin_dashboard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return

    if update.message.text.strip().lower() in ["start", "ابدا", "ابدأ"]:
        await admin_dashboard(update, context)

# ================== تشغيل ==================

def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", admin_dashboard))
    app.add_handler(CallbackQueryHandler(set_group))
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP & filters.REPLY, handle_admin_reply)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP & filters.TEXT, admin_dashboard_text)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
