"""
Telegram Bot Engine for DEV PORTAL VS (@devportalvs_bot)
Provides 1-click web app launcher, token assistance, and Google App Password generator guidance.
"""

import threading
import time
import telebot
from telebot import types

BOT_TOKEN = "9159043195:AAGBFFbn76xqIrn1ynbfI1z6srhVO0BgNjI"
WEB_APP_URL = "https://pp-mod-auto-quest.onrender.com"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    user_name = message.from_user.first_name or "Gamer"
    text = (
        f"👋 <b>স্বাগতম {user_name}!</b>\n\n"
        f"🎮 <b>PlayQuest Unlocker Engine</b> (@devportalvs_bot)\n"
        f"১০০% ফ্রি Google Play Games এচিভমেন্ট ও লেভেল আনলকার!\n\n"
        f"✨ <b>ওয়েবসাইটে ৩টি উপায়ে সহজ লগইন করতে পারেন:</b>\n"
        f"১️⃣ <b>Google App Password:</b> কোনো নোটিফিকেশন ছাড়াই মাত্র ০.৫ সেকেন্ডে ফাস্ট লগইন!\n"
        f"২️⃣ <b>Master Token:</b> আপনার মাস্টার টোকেন পেস্ট করে সরাসরি আসল ডেটা লোড!\n"
        f"৩️⃣ <b>1-Click Google Sign-In:</b> ব্রাউজার দিয়ে ১-ক্লিকে সরাসরি লগইন!\n\n"
        f"🌐 <b>আমাদের ওয়েব অ্যাপে যেতে নিচের বাটনে চাপুন:</b>"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_web = types.InlineKeyboardButton("🚀 ওপেন প্লেকুয়েস্ট ওয়েবসাইট", url=WEB_APP_URL)
    btn_app_pass = types.InlineKeyboardButton("🔑 ১৬ অক্ষরের App Password তৈরি করুন", url="https://myaccount.google.com/apppasswords")
    btn_guide = types.InlineKeyboardButton("📖 এচিভমেন্ট আনলকের নিয়মাবলী", callback_data="show_guide")

    markup.add(btn_web, btn_app_pass, btn_guide)
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_guide")
def show_guide(call):
    guide_text = (
        f"📖 <b>সহজ নিয়মাবলী:</b>\n\n"
        f"১. <a href='https://myaccount.google.com/apppasswords'>এখানে ক্লিক করে</a> আপনার জিমেইল অ্যাকাউন্টে একটি ১৬ অক্ষরের 'App Password' তৈরি করুন।\n"
        f"২. <a href='{WEB_APP_URL}'>ওয়েবসাইটে যান</a> এবং আপনার জিমেইল ও ১৬ অক্ষরের পাসওয়ার্ডটি দিয়ে লগইন করুন।\n"
        f"৩. লগইন হওয়ার সাথে সাথে আপনার আসল গেমার প্রোফাইল ও XP লোড হয়ে যাবে।\n"
        f"৪. এরপর পছন্দের গেমের পাশে '⚡ আনলক' বাটনে ক্লিক করলেই গুগল সার্ভারে এচিভমেন্ট আনলক হবে এবং আপনার লেভেল বাড়বে!\n\n"
        f"সবকিছু ১০০% ফ্রি ও নিরাপদ! ✨"
    )
    bot.edit_message_text(guide_text, call.message.chat.id, call.message.message_id, parse_mode="HTML")

def run_bot_polling():
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e:
            time.sleep(5)

def start_bot_thread():
    t = threading.Thread(target=run_bot_polling, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    print("[+] DEV PORTAL VS Telegram Bot Started...")
    bot.infinity_polling()
