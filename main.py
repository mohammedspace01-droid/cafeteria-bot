import os
import time
import json
from datetime import datetime, timezone, timedelta
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

SESSION_SECONDS = 4 * 60 * 60          # 4 ساعات استفسار
USER_LIFETIME = 48 * 60 * 60           # 48 ساعة تخزين
DATA_FILE = "data.json"

EGY_TZ = timezone(timedelta(hours=2))

GROUP_MAP = {
    "A": "المجموعة أ",
    "B": "المجموعة ب",
    "C": "المجموعة ج",
}

USERS = {}

# ================== أدوات الوقت ==================

def now():
    return int(time.time())

def fmt(ts):
    return datetime.fromtimestamp(ts, EGY_TZ).strftime("%I:%M %p")

# ================== التخزين ==================

def load_data():
    global USERS
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            USERS = {int(k): v for k, v in json.load(f).items()}
    except:
        USERS = {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USERS, f, ensure_ascii=False, indent=2)

def cleanup():
    now_ts = now()
    changed = False
    for uid in list(USERS.keys()):
        if now_ts - USERS[uid]["created_at"] > USER_LIFETIME:
            del USERS[uid]
            changed = True
    if changed:
        save_data()

# ================== رسالة الأدمن ==================

def build_admin_message(uid):
    u = USERS[uid]

    msgs = "\n".join(
        f"{i+1}) [{fmt(t)}] {m}"
        for i, (t, m) in enumerate(u["messages"])
    ) or "—"

    status = "🟢 #تم_الرد" if u["replied"] else "🟡 #لم_يتم_الرد"

    return (
        "📩 استفسار طالب\n\n"
        f"👤 الاسم: {u['name']}\n"
        f"🔗 @{u['username'] or 'غير متاح'}\n"
        f"🆔 ID: {uid}\n"
        f"👥 {u['group']}\n\n"
        "━━━━━━━━━━━━━━\n"
        "📨 الرسائل:\n"
        f"{msgs}\n"
        "━━━━━━━━━━━━━━\n"
        f"📌 الحالة: {status}\n\n"
        "↩️ الرد يكون Reply على أي رسالة داخل الاستفسار"
    )

# ================== الطالب ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    uid = update.message.from_user.id
    ts = now()

    if uid not in USERS or ts - USERS[uid]["session_start"] > SESSION_SECONDS:
        USERS[uid] = {
            "name": update.message.from_user.full_name,
            "username": update.message.from_user.username,
            "group": None,
            "messages": [],
            "admin_root": None,
            "replied": False,
            "reply_count": 0,
            "session_start": ts,
            "created_at": ts,
        }
        save_data()

        await update.message.reply_text("اختار مجموعتك 👇")
        await send_group_buttons(update)
    else:
        await update.message.reply_text("ابعت استفسارك مباشرة 👇")

async def send_group_buttons(update):
    kb = [[
        InlineKeyboardButton("أ", callback_data="group_A"),
        InlineKeyboardButton("ب", callback_data="group_B"),
        InlineKeyboardButton("ج", callback_data="group_C"),
    ]]
    await update.message.reply_text(
        "اختار مجموعتك:",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    key = query.data.split("_")[1]

    if uid not in USERS:
        return

    USERS[uid]["group"] = GROUP_MAP[key]
    USERS[uid]["session_start"] = now()
    save_data()

    await query.edit_message_text("تمام 👌 ابعت استفسارك.")

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    cleanup()

    uid = update.message.from_user.id
    ts = now()

    if uid not in USERS:
        await start(update, context)
        return

    if ts - USERS[uid]["session_start"] > SESSION_SECONDS:
        USERS[uid]["group"] = None
        USERS[uid]["messages"] = []
        USERS[uid]["admin_root"] = None
        USERS[uid]["replied"] = False
        USERS[uid]["reply_count"] = 0
        USERS[uid]["session_start"] = ts
        save_data()

        await send_group_buttons(update)
        return

    if USERS[uid]["group"] is None:
        await send_group_buttons(update)
        return

    msg = update.message
    label = "📩 مرفق"

    if msg.text:
        label = msg.text
    elif msg.photo:
        label = "🖼️ صورة"
    elif msg.document:
        label = f"📎 {msg.document.file_name}"
    elif msg.voice:
        label = "🎤 رسالة صوتية"

    USERS[uid]["messages"].append((ts, label))
    USERS[uid]["replied"] = False
    save_data()

    if USERS[uid]["admin_root"] is None:
        root = await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=build_admin_message(uid),
        )
        USERS[uid]["admin_root"] = root.message_id
        save_data()

    reply_to = USERS[uid]["admin_root"]

    # ====== إرسال المحتوى (مُحسّن) ======
    if msg.text:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"📝 رسالة من الطالب:\n\n{msg.text}",
            reply_to_message_id=reply_to,
        )
    elif msg.photo:
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=msg.photo[-1].file_id,
            caption="🖼️ صورة من الطالب",
            reply_to_message_id=reply_to,
        )
    elif msg.document:
        await context.bot.send_document(
            chat_id=ADMIN_GROUP_ID,
            document=msg.document.file_id,
            caption=f"📎 ملف من الطالب: {msg.document.file_name}",
            reply_to_message_id=reply_to,
        )
    elif msg.voice:
        await context.bot.send_voice(
            chat_id=ADMIN_GROUP_ID,
            voice=msg.voice.file_id,
            caption="🎤 رسالة صوتية من الطالب",
            reply_to_message_id=reply_to,
        )

    await context.bot.edit_message_text(
        chat_id=ADMIN_GROUP_ID,
        message_id=reply_to,
        text=build_admin_message(uid),
    )

# ================== رد الأدمن ==================

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return
    if not update.message.reply_to_message:
        return

    cleanup()

    replied_id = update.message.reply_to_message.message_id

    for uid, u in USERS.items():
        if u["admin_root"] == replied_id or replied_id > u["admin_root"]:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=ADMIN_GROUP_ID,
                message_id=update.message.message_id,
            )

            u["reply_count"] += 1
            u["replied"] = True
            save_data()

            await context.bot.edit_message_text(
                chat_id=ADMIN_GROUP_ID,
                message_id=u["admin_root"],
                text=build_admin_message(uid),
            )

            await update.message.reply_text("✅ تم إرسال الرد للطالب")
            break

# ================== داش بورد ==================

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return

    total = len(USERS)
    done = sum(1 for u in USERS.values() if u["replied"])
    pending = total - done

    await update.message.reply_text(
        "📊 داش بورد\n\n"
        f"📨 إجمالي الاستفسارات: {total}\n"
        f"🟢 تم الرد: {done}\n"
        f"🟡 لم يتم الرد: {pending}"
    )

async def dashboard_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.id != ADMIN_GROUP_ID:
        return

    text = update.message.text.strip().lower()
    if text in ["start", "ابدا", "ابدأ", "dashboard", "داش بورد"]:
        await dashboard(update, context)

# ================== تشغيل ==================

def main():
    load_data()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CallbackQueryHandler(set_group))

    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP & filters.TEXT & ~filters.COMMAND, dashboard_trigger)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP & filters.REPLY, handle_admin_reply)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
