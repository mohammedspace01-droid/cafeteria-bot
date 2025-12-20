import os
import time
import json
from datetime import datetime, timedelta, timezone
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

# ================== الإعدادات ==================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_GROUP_ID = -1003593388052

SESSION_SECONDS = 4 * 60 * 60        # 4 ساعات
MEMORY_SECONDS = 48 * 60 * 60         # 48 ساعة
DATA_FILE = "data.json"

TZ_EGYPT = timezone(timedelta(hours=2))

GROUP_MAP = {
    "A": "المجموعة أ",
    "B": "المجموعة ب",
    "C": "المجموعة ج",
}

USERS = {}

# ================== حفظ / تحميل ==================

def load_data():
    global USERS
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            USERS = {int(k): v for k, v in raw.items()}
    except:
        USERS = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USERS, f, ensure_ascii=False, indent=2)

# ================== أدوات ==================

def now():
    return int(time.time())

def fmt(ts):
    return datetime.fromtimestamp(ts, TZ_EGYPT).strftime("%I:%M %p")

def cleanup():
    t = now()
    removed = False
    for uid in list(USERS.keys()):
        if t - USERS[uid]["start_time"] > MEMORY_SECONDS:
            del USERS[uid]
            removed = True
    if removed:
        save_data()

def build_admin_message(uid):
    u = USERS[uid]

    messages = "\n".join(
        f"{i+1}) [{fmt(t)}] {txt}"
        for i, (t, txt) in enumerate(u["messages"])
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
        f"{messages}\n"
        "━━━━━━━━━━━━━━\n"
        f"📌 الحالة: {status}\n\n"
        "↩️ الرد يكون Reply على الرسالة"
    )

# ================== الطالب ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    uid = update.message.from_user.id
    t = now()

    USERS[uid] = {
        "name": update.message.from_user.full_name,
        "username": update.message.from_user.username,
        "group": None,
        "start_time": t,
        "messages": [],
        "admin_message_id": None,
        "replied": False,
        "reply_count": 0,
    }
    save_data()

    await update.message.reply_text("أهلاً بيك 👋\nاختار مجموعتك 👇")
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
    await query.answer()

    uid = query.from_user.id
    key = query.data.split("_")[1]

    if uid not in USERS:
        return

    USERS[uid]["group"] = GROUP_MAP[key]
    USERS[uid]["start_time"] = now()
    save_data()

    await query.edit_message_text(
        "تمام 👌\nابعت استفسارك، ولو في صور أو ملفات ابعتها عادي."
    )

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    cleanup()

    uid = update.message.from_user.id
    t = now()

    if uid not in USERS:
        await start(update, context)
        return

    # انتهاء جلسة 4 ساعات
    if t - USERS[uid]["start_time"] > SESSION_SECONDS:
        USERS[uid]["group"] = None
        USERS[uid]["messages"] = []
        USERS[uid]["admin_message_id"] = None
        USERS[uid]["replied"] = False
        USERS[uid]["reply_count"] = 0
        USERS[uid]["start_time"] = t
        save_data()
        await send_group_buttons(update)
        return

    if USERS[uid]["group"] is None:
        await send_group_buttons(update)
        return

    msg = update.message

    if msg.text:
        content = msg.text
    elif msg.photo:
        content = "🖼️ صورة"
    elif msg.document:
        content = f"📎 ملف: {msg.document.file_name}"
    elif msg.voice:
        content = "🎤 رسالة صوتية"
    else:
        content = "📩 مرفق"

    USERS[uid]["messages"].append((t, content))
    USERS[uid]["replied"] = False
    save_data()

    if USERS[uid]["admin_message_id"] is None:
        sent = await context.bot.send_message(
            ADMIN_GROUP_ID,
            build_admin_message(uid)
        )
        USERS[uid]["admin_message_id"] = sent.message_id
        save_data()
    else:
        await context.bot.edit_message_text(
            ADMIN_GROUP_ID,
            USERS[uid]["admin_message_id"],
            build_admin_message(uid)
        )

# ================== الأدمن ==================

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return
    if not update.message.reply_to_message:
        return

    cleanup()

    text = update.message.reply_to_message.text
    if not text or "🆔 ID:" not in text:
        return

    try:
        uid = int(text.split("🆔 ID:")[1].split("\n")[0].strip())
    except:
        return

    if uid not in USERS:
        return

    u = USERS[uid]

    await context.bot.copy_message(
        chat_id=uid,
        from_chat_id=ADMIN_GROUP_ID,
        message_id=update.message.message_id,
    )

    u["reply_count"] += 1
    u["replied"] = True
    save_data()

    if u["reply_count"] % 2 == 0:
        await context.bot.send_message(
            uid, "📬 جالك رد بخصوص استفسارك 👆"
        )

    if u["admin_message_id"]:
        await context.bot.edit_message_text(
            ADMIN_GROUP_ID,
            u["admin_message_id"],
            build_admin_message(uid)
        )

    await update.message.reply_text("✅ تم إرسال الرد للطالب")

# ================== تشغيل ==================

def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_group))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private))
    app.add_handler(MessageHandler(filters.ChatType.SUPERGROUP & filters.REPLY, handle_admin_reply))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
