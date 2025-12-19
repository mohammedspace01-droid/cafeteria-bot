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

WINDOW_SECONDS = 4 * 60 * 60          # 4 ساعات سيشن
CLEANUP_SECONDS = 48 * 60 * 60        # حذف بعد 48 ساعة
DATA_FILE = "data.json"

USERS = {}

GROUP_MAP = {
    "A": "المجموعة أ",
    "B": "المجموعة ب",
    "C": "المجموعة ج",
}

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

# ================== تنظيف ==================

def cleanup_old_users():
    now_ts = int(time.time())
    removed = False

    for uid in list(USERS.keys()):
        if now_ts - USERS[uid]["start_time"] > CLEANUP_SECONDS:
            del USERS[uid]
            removed = True

    if removed:
        save_data()

# ================== أدوات ==================

def now():
    return int(time.time())

def fmt(ts):
    return time.strftime("%I:%M %p", time.localtime(ts))

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
        "↩️ للرد: اعمل Reply على الرسالة"
    )

# ================== الطالب ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    cleanup_old_users()

    user = update.message.from_user
    uid = user.id
    ts = now()

    # لو مفيش سيشن أو السيشن انتهت → نبدأ واحدة جديدة
    if uid not in USERS or ts - USERS[uid]["start_time"] > WINDOW_SECONDS:
        USERS[uid] = {
            "name": user.full_name,
            "username": user.username,
            "group": None,
            "start_time": ts,
            "messages": [],
            "admin_message_id": None,
            "replied": False,
            "reply_count": 0,
        }
        save_data()

        await update.message.reply_text(
            "خلّينا نبدأ استفسار جديد 👌\n"
            "اختار مجموعتك علشان نقدر نساعدك أسرع 👇"
        )
    else:
        await update.message.reply_text(
            "أهلاً بيك 👋\n"
            "نكمّل على نفس الاستفسار، اختار مجموعتك 👇"
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
    await query.answer()

    uid = query.from_user.id
    key = query.data.split("_")[1]

    USERS[uid]["group"] = GROUP_MAP[key]
    save_data()

    await query.edit_message_text(
        "تمام 👌\n"
        "ابعت استفسارك، ولو في صور أو ملفات ابعتها عادي."
    )

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    cleanup_old_users()

    user = update.message.from_user
    uid = user.id
    ts = now()

    # لو السيشن انتهت → نبدأ واحدة جديدة ونطلب المجموعة
    if uid not in USERS or ts - USERS[uid]["start_time"] > WINDOW_SECONDS:
        USERS[uid] = {
            "name": user.full_name,
            "username": user.username,
            "group": None,          # ⬅️ لازم يختارها تاني
            "start_time": ts,
            "messages": [],
            "admin_message_id": None,
            "replied": False,
            "reply_count": 0,
        }
        save_data()

        await update.message.reply_text(
            "خلّينا نبدأ استفسار جديد 👌\n"
            "اختار مجموعتك الأول 👇"
        )
        await send_group_buttons(update)
        return

    # لسه مختارش مجموعة
    if USERS[uid]["group"] is None:
        return

    # تسجيل الرسالة
    msg = update.message
    if msg.text:
        content = msg.text
    elif msg.document:
        content = f"📎 ملف: {msg.document.file_name}"
    elif msg.photo:
        content = "🖼️ صورة"
    elif msg.voice:
        content = "🎤 رسالة صوتية"
    else:
        content = "📩 مرفق"

    USERS[uid]["messages"].append((ts, content))
    USERS[uid]["replied"] = False
    save_data()

    # إرسال / تحديث رسالة الأدمن
    if USERS[uid]["admin_message_id"] is None:
        sent = await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=build_admin_message(uid),
        )
        USERS[uid]["admin_message_id"] = sent.message_id
        save_data()
    else:
        await context.bot.edit_message_text(
            chat_id=ADMIN_GROUP_ID,
            message_id=USERS[uid]["admin_message_id"],
            text=build_admin_message(uid),
        )

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

    cleanup_old_users()

    replied_to_id = update.message.reply_to_message.message_id

    for uid, u in USERS.items():
        if u["admin_message_id"] == replied_to_id:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=ADMIN_GROUP_ID,
                message_id=update.message.message_id,
            )

            u["reply_count"] += 1
            u["replied"] = True
            save_data()

            # إشعار كل ردين
            if u["reply_count"] % 2 == 0:
                await context.bot.send_message(
                    chat_id=uid,
                    text="📬 جالك رد بخصوص استفسارك 👆"
                )

            await context.bot.edit_message_text(
                chat_id=ADMIN_GROUP_ID,
                message_id=replied_to_id,
                text=build_admin_message(uid),
            )

            await update.message.reply_text("✅ تم إرسال الرد للطالب")
            break

# ================== تشغيل ==================

def main():
    load_data()
    print("Bot is running...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_group))
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.SUPERGROUP & filters.REPLY, handle_admin_reply)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
