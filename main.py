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



# ================== إعدادات ==================



BOT_TOKEN = os.environ.get("BOT_TOKEN")

ADMIN_GROUP_ID = -1003593388052



WINDOW_SECONDS = 4 * 60 * 60

CLEANUP_SECONDS = 48 * 60 * 60

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



# ================== أدوات ==================



def now():

    return int(time.time())



def fmt(ts):

    return time.strftime("%I:%M %p", time.localtime(ts))



def cleanup_old_users():

    ts = now()

    changed = False

    for uid in list(USERS.keys()):

        if ts - USERS[uid]["start_time"] > CLEANUP_SECONDS:

            del USERS[uid]

            changed = True

    if changed:

        save_data()



def build_admin_message(uid):

    u = USERS[uid]



    msgs = "\n".join(

        f"{i+1}) [{fmt(t)}] {m}"

        for i, (t, m) in enumerate(u["messages"])

    )



    if u.get("closed"):

        status = "🔴 #مغلق"

    else:

        status = "🟢 #تم_الرد" if u["replied"] else "🟡 #لم_يتم_الرد"



    keyboard = InlineKeyboardMarkup([[

        InlineKeyboardButton("🔒 قفل الاستفسار", callback_data=f"close_{uid}")

    ]])



    return {

        "text": (

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

            "↩️ للرد: اعمل Reply على نفس الاستفسار"

        ),

        "reply_markup": keyboard

    }



# ================== الطالب ==================



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.chat.type != "private":

        return



    uid = update.message.from_user.id

    ts = now()



    USERS[uid] = {

        "name": update.message.from_user.full_name,

        "username": update.message.from_user.username,

        "group": None,

        "start_time": ts,

        "messages": [],

        "admin_message_id": None,

        "replied": False,

        "reply_count": 0,

        "calm_sent": False,

        "closed": False,

    }

    save_data()



    await update.message.reply_text("اختار مجموعتك 👇")

    await send_group_buttons(update)



async def send_group_buttons(update):

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

    USERS[uid]["group"] = GROUP_MAP[query.data.split("_")[1]]

    save_data()



    await query.edit_message_text(

        "تمام 👌\n"

        "ابعت استفسارك."

    )



async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.chat.type != "private":

        return



    cleanup_old_users()



    uid = update.message.from_user.id

    ts = now()



    if uid not in USERS:

        await start(update, context)

        return



    u = USERS[uid]



    if ts - u["start_time"] > WINDOW_SECONDS:

        await start(update, context)

        return



    if u["group"] is None:

        await send_group_buttons(update)

        return



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



    u["messages"].append((ts, content))

    u["replied"] = False



    if not u["calm_sent"] and len(u["messages"]) >= 3:

        await update.message.reply_text(

            "تمام 👍 وصلنا استفسارك، أول ما ييجي رد هيوصلك هنا."

        )

        u["calm_sent"] = True



    save_data()



    payload = build_admin_message(uid)



    if u["admin_message_id"] is None:

        sent = await context.bot.send_message(

            chat_id=ADMIN_GROUP_ID,

            text=payload["text"],

            reply_markup=payload["reply_markup"]

        )

        u["admin_message_id"] = sent.message_id

        save_data()

    else:

        await context.bot.edit_message_text(

            chat_id=ADMIN_GROUP_ID,

            message_id=u["admin_message_id"],

            text=payload["text"],

            reply_markup=payload["reply_markup"]

        )



# ================== الأدمن ==================



async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message.chat.id != ADMIN_GROUP_ID:

        return

    if not update.message.reply_to_message:

        return



    replied_to = update.message.reply_to_message.message_id



    for uid, u in USERS.items():

        if u["admin_message_id"] == replied_to:

            await context.bot.copy_message(

                chat_id=uid,

                from_chat_id=ADMIN_GROUP_ID,

                message_id=update.message.message_id,

            )



            u["reply_count"] += 1

            u["replied"] = True

            save_data()



            await update.message.reply_text("✅ تم إرسال الرد للطالب")

            break



async def close_case(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    uid = int(query.data.split("_")[1])



    if uid in USERS:

        USERS[uid]["closed"] = True

        save_data()



        payload = build_admin_message(uid)

        await query.edit_message_text(

            text=payload["text"],

            reply_markup=payload["reply_markup"]

        )

        await query.answer("تم قفل الاستفسار 🔒")



# ================== تشغيل ==================



def main():

    load_data()

    app = ApplicationBuilder().token(BOT_TOKEN).build()



    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(set_group, pattern="^group_"))

    app.add_handler(CallbackQueryHandler(close_case, pattern="^close_"))

    app.add_handler(

        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private)

    )

    app.add_handler(

        MessageHandler(filters.ChatType.SUPERGROUP & filters.REPLY, handle_admin_reply)

    )



    app.run_polling()



if __name__ == "__main__":

    main()

