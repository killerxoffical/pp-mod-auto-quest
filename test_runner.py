"""
Interactive Test Runner for Google Play Games Achievement Unlocker
Features:
- Instant 0.5s auto-login with saved master token (never prompts for login repeatedly)
- Real Google Play Store Games (Subway Surfers, Hill Climb Racing, Temple Run 2, Angry Birds 2)
- Dynamic Achievement Fetching & Unlocking (Standard + Incremental)
- 100% Verified Live Server XP Verification & Level Up
"""

import sys
import os
import json
import time
import requests
from auth import exchange_oauth_token_for_master, get_games_oauth_token
from engine import get_player_profile, list_player_achievements, unlock_achievement, set_achievement_steps, get_headers
from google_web_login import login_and_get_oauth_token
from games_db import SUPPORTED_GAMES
from config import GAMES_API_BASE

SESSION_CACHE_FILE = os.path.join(os.path.dirname(__file__), "session_cache.json")

def load_cached_session():
    if os.path.exists(SESSION_CACHE_FILE):
        try:
            with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_session(email, master_token, android_id):
    try:
        with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "email": email,
                "master_token": master_token,
                "android_id": android_id,
                "saved_at": time.time()
            }, f, indent=2)
    except Exception as e:
        print(f"⚠️ সেশন সেভ এরর: {e}")

def print_banner():
    print("=" * 68)
    print("  🎮 GOOGLE PLAY GAMES ACHIEVEMENT UNLOCKER (PRO LIVE ENGINE)")
    print("  VAREON Studio • 100% Free Self-Hosted Cloud Engine")
    print("=" * 68)

def unlock_game_achievements(email, master_token, android_id, game_key, max_to_unlock=5):
    game = SUPPORTED_GAMES[game_key]
    print("\n" + "=" * 68)
    print(f"🚀 টার্গেট গেম কানেক্ট করা হচ্ছে: {game['title']}")
    print(f"📦 Package: {game['package']}")
    print("=" * 68)

    # ১. এই গেমের জন্য অফিসিয়াল OAuth টোকেন জেনারেট করা
    print("⏳ গেমটির জন্য অফিসিয়াল গুগল অথেনটিকেশন টোকেন প্রস্তুত করা হচ্ছে...")
    tok_res = get_games_oauth_token(
        email=email,
        master_token=master_token,
        android_id=android_id,
        app_package=game["package"],
        client_sig=game["client_sig"]
    )

    if not tok_res.get("ok"):
        print(f"❌ টোকেন এরর: {tok_res.get('error')}")
        return 0

    game_token = tok_res["access_token"]
    print("✅ সফলভাবে গেমের অফিসিয়াল API সেশন কানেক্ট হয়েছে!")

    # ২. গেমের সব এচিভমেন্টের তালিকা আনা
    print("⏳ গুগলের সার্ভার থেকে গেমটির সকল এচিভমেন্টের তালিকা আনা হচ্ছে...")
    try:
        defs_res = requests.get(f"{GAMES_API_BASE}/achievements", headers=get_headers(game_token), timeout=10)
        if defs_res.status_code != 200:
            print(f"❌ এচিভমেন্ট ডেটা পাওয়া যায়নি ({defs_res.status_code})")
            return 0
        all_defs = defs_res.json().get("items", [])
    except Exception as e:
        print(f"❌ এরর: {e}")
        return 0

    print(f"📋 মোট {len(all_defs)}টি এচিভমেন্ট গুগলের ডাটাবেজে পাওয়া গেছে।")

    # ৩. প্লেয়ারের বর্তমান অগ্রগতি চেক করা (কোনগুলো আনলক আছে, কোনগুলো লক আছে)
    print("⏳ আপনার অ্যাকাউন্টের অগ্রগতি চেক করা হচ্ছে...")
    try:
        player_achs_res = requests.get(f"{GAMES_API_BASE}/players/me/achievements", headers=get_headers(game_token), timeout=10)
        player_achs = player_achs_res.json().get("items", []) if player_achs_res.status_code == 200 else []
    except Exception:
        player_achs = []

    already_unlocked_ids = {a.get("id") for a in player_achs if a.get("achievementState") == "UNLOCKED"}

    # ৪. এখনো আনলক হয়নি এমন এচিভমেন্ট সিলেক্ট করা
    targets = []
    for d in all_defs:
        if d.get("id") not in already_unlocked_ids:
            targets.append(d)
            if len(targets) >= max_to_unlock:
                break

    if not targets:
        print("🎉 অভিনন্দন! এই গেমের সব এচিভমেন্ট আপনার অ্যাকাউন্টে আগেই আনলক করা আছে!")
        return 0

    print(f"🎯 আপনার জন্য {len(targets)}টি ফ্রেশ (Locked) এচিভমেন্ট সিলেক্ট করা হয়েছে।\n")

    # ৫. লাইভ আনলক এক্সিকিউশন
    newly_count = 0
    for idx, ach in enumerate(targets):
        ach_id = ach.get("id")
        ach_name = ach.get("name", "Achievement")
        ach_type = ach.get("achievementType", "STANDARD")
        total_steps = ach.get("totalSteps", 1)
        ach_xp = ach.get("experiencePoints", 500)

        print(f"⏳ [{idx + 1}/{len(targets)}] আনলক রিকোয়েস্ট পাঠানো হচ্ছে...")
        print(f"   🏆 Name: {ach_name} (XP: +{ach_xp})")

        if ach_type == "INCREMENTAL" and total_steps:
            res = set_achievement_steps(game_token, ach_id, total_steps)
        else:
            res = unlock_achievement(game_token, ach_id)

        if res.get("ok"):
            newly = res.get("newly_unlocked", False)
            if newly:
                print(f"   🎉 SUCCESS! Google Play Games কনফার্ম করেছে: UNLOCKED ✓ (নতুন আনলক!)")
                newly_count += 1
            else:
                print(f"   ✨ Status: UNLOCKED ✓")
        else:
            print(f"   ❌ এরর ({res.get('status_code')}): {res.get('error')}")

        time.sleep(1)

    print("\n" + "-" * 68)
    print(f"✅ {game['title']} থেকে মোট {newly_count}টি নতুন এচিভমেন্ট সফলভাবে আনলক হয়েছে!")
    print("-" * 68)
    return newly_count

def run_test():
    print_banner()

    cached = load_cached_session()
    email = None
    master_token = None
    android_id = None

    if cached and cached.get("master_token") and cached.get("email"):
        email = cached["email"]
        master_token = cached["master_token"]
        android_id = cached["android_id"]
        print(f"\n⚡ অটো-লগইন সক্রিয়: সেভ করা গুগল সেশন পাওয়া গেছে!")
        print(f"   📧 অ্যাকাউন্ট: {email}")
        print("   (০.৫ সেকেন্ডে স্বয়ংক্রিয়ভাবে ক্লাউডে কানেক্ট হচ্ছে...)\n")
    else:
        print("\n💡 তথ্য: নতুন ডিভাইস বা সেশন শুরু করার জন্য গুগল লগইন প্রয়োজন।\n")
        email = input("📧 আপনার Gmail Address লিখুন: ").strip()
        if not email:
            print("❌ কোনো ইমেইল দেওয়া হয়নি। বাতিল।")
            return

        login_res = login_and_get_oauth_token(email=email, headless=False, timeout_sec=180)
        if not login_res.get("ok"):
            print(f"❌ লগইন ব্যর্থ: {login_res.get('message')}")
            return

        ex_res = exchange_oauth_token_for_master(email, login_res["oauth_token"])
        if not ex_res.get("ok"):
            print(f"❌ মাস্টার টোকেন ব্যর্থ: {ex_res.get('error')}")
            return

        master_token = ex_res["master_token"]
        android_id = ex_res["android_id"]
        save_session(email, master_token, android_id)
        print("✅ সেশন সফলভাবে লোকাল ক্যাশে সেভ করা হয়েছে (পরের বার আর পাসওয়ার্ড লাগবে না)!\n")

    # লাইভ প্রোফাইল অডিট
    base_tok_res = get_games_oauth_token(email, master_token, android_id)
    if not base_tok_res.get("ok"):
        print(f"❌ গুগল প্লে গেমস কানেক্ট এরর: {base_tok_res.get('error')}")
        print("💡 সেভ করা সেশন মুছে নতুন করে লগইন করতে চাইলে session_cache.json ফাইলটি মুছে ফেলুন।")
        return

    base_token = base_tok_res["access_token"]
    profile_before = get_player_profile(base_token)

    if profile_before.get("ok"):
        xp_before = int(profile_before.get("experience", {}).get("currentExperiencePoints", 0) or 0)
        current_level = profile_before.get("experience", {}).get("currentLevel", {}).get("level", 1)
        print("★" * 68)
        print("👤 গুগল প্লে গেমস লাইভ প্রোফাইল স্ট্যাটাস:")
        print(f"   🎮 Gamer Tag : {profile_before.get('display_name')}")
        print(f"   🆔 Player ID  : {profile_before.get('player_id')}")
        print(f"   🔰 Play Level : Level {current_level}")
        print(f"   ⭐ Current XP : {xp_before:,} XP (১০০% গুগলের লাইভ সার্ভার ডেটা)")
        print("★" * 68)
    else:
        xp_before = 0
        current_level = 1

    # মেনু
    print("\n" + "=" * 68)
    print("🎮 কোন গেমের এচিভমেন্ট ও XP আনলক করবেন বেছে নিন:")
    print("=" * 68)
    for k, v in SUPPORTED_GAMES.items():
        print(f" [{k}] {v['title']} • {v['desc']}")
    print(" [5] ⚡ ALL-IN-ONE Super Booster (সবগুলো গেম থেকে একসাথে মোট ১৫টি এচিভমেন্ট)")
    print(" [0] 🔄 লগআউট / অন্য অ্যাকাউন্টে সুইচ করুন")

    choice = input("\n👉 আপনার পছন্দ (1-5, সরাসরি Enter চাপলে [1] Subway Surfers হবে): ").strip() or "1"

    if choice == "0":
        if os.path.exists(SESSION_CACHE_FILE):
            os.remove(SESSION_CACHE_FILE)
        print("✅ বর্তমান সেশন মুছে ফেলা হয়েছে। পুনরায় স্ক্রিপ্টটি চালু করে নতুন অ্যাকাউন্টে লগইন করুন।")
        return

    total_newly = 0
    if choice in SUPPORTED_GAMES:
        count_input = input("কয়টি এচিভমেন্ট আনলক করবেন? (Enter দিলে ডিফল্ট 5টি হবে): ").strip()
        count = int(count_input) if count_input.isdigit() else 5
        total_newly += unlock_game_achievements(email, master_token, android_id, choice, max_to_unlock=count)
    elif choice == "5":
        print("\n🚀 ALL-IN-ONE Super Booster শুরু হচ্ছে...")
        for gk in ["1", "2", "3", "4"]:
            total_newly += unlock_game_achievements(email, master_token, android_id, gk, max_to_unlock=4)
    else:
        total_newly += unlock_game_achievements(email, master_token, android_id, "1", max_to_unlock=5)

    # রেজাল্ট অডিট
    print("\n⏳ গুগলের সার্ভার থেকে নতুন প্রোফাইল ও অর্জিত XP হিসাব করা হচ্ছে...")
    time.sleep(2)
    profile_after = get_player_profile(base_token)
    if profile_after.get("ok"):
        xp_after = int(profile_after.get("experience", {}).get("currentExperiencePoints", 0) or 0)
        new_level = profile_after.get("experience", {}).get("currentLevel", {}).get("level", 1)
        print("\n" + "★" * 68)
        print("📊 ফাইনাল রেজাল্ট অডিট:")
        print(f"   ⭐ পূর্বের XP  : {xp_before:,} XP")
        print(f"   ⭐ বর্তমান নতুন XP: {xp_after:,} XP")
        if xp_after > xp_before:
            gain = xp_after - xp_before
            print(f"   🚀 সর্বমোট বৃদ্ধি পেয়েছে: +{gain:,} XP সরাসরি গুগল ক্লাউডে যোগ হয়েছে! 🎉")
            if new_level > current_level:
                print(f"   🏆 অভিনন্দন! আপনি নতুন লেভেলে উত্তীর্ণ হয়েছেন: Level {new_level}!")
        else:
            print("   ℹ️ কোনো নতুন XP বাড়েনি (সম্ভবত এই এচিভমেন্টগুলো আগে থেকেই আনলক ছিল)।")
        print("★" * 68)

    print("\n💡 আপনার ফোনের Google Play Games অ্যাপে দেখতে:")
    print("   ১. ফোন থেকে Google Play Games অ্যাপটি Recent Apps থেকে সম্পূর্ণ বন্ধ (Close) করুন।")
    print("   ২. অ্যাপটি ওপেন করে প্রোফাইল স্ক্রিনে গিয়ে ওপর থেকে নিচে রিফ্রেশ (Pull down) করুন।")
    print("   ৩. সাথে সাথে নতুন গেমের আইকন ও আনলক করা এচিভমেন্ট দেখতে পাবেন!\n")

if __name__ == "__main__":
    run_test()
