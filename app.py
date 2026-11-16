"""
Flask Web Application for Google Play Games Achievement Unlocker & Profile Engine
Optimized for Render.com (ppmod-quest-unlock.onrender.com)
"""

import os
import time
import json
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS

from config import GAMES_API_BASE, SCOPE_GAMES, PLAY_GAMES_PACKAGE, GOOGLE_CLIENT_SIG
from auth import exchange_oauth_token_for_master, perform_google_login, get_games_oauth_token, generate_android_id
from engine import get_player_profile, get_headers, unlock_achievement, set_achievement_steps
from games_db import SUPPORTED_GAMES

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# In-memory session store (backed by client localStorage tokens)
SESSIONS = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "healthy", "service": "ppmod-quest-unlock", "timestamp": time.time()})

@app.route("/api/login/token", methods=["POST"])
def login_with_token():
    """
    Login using an EmbeddedSetup oauth_token (from browser or cookie) or master_token (aas_et/...).
    This 100% bypasses Google bot-detection and 2FA blocks.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    token_str = data.get("oauth_token", "") or data.get("token", "")
    token_str = token_str.strip()

    if not email or not token_str:
        return jsonify({"ok": False, "error": "Email এবং Token উভয়ই প্রয়োজন।"}), 400

    android_id = data.get("android_id", "").strip() or generate_android_id()

    # Check if already a master token
    if token_str.startswith("aas_et/"):
        master_token = token_str
    else:
        # Strip oauth_token= prefix if pasted with cookie name
        clean_tok = token_str.replace("oauth_token=", "").strip()
        ex_res = exchange_oauth_token_for_master(email, clean_tok, android_id)
        if not ex_res.get("ok"):
            return jsonify({"ok": False, "error": f"গুগল টোকেন এক্সচেঞ্জ ব্যর্থ: {ex_res.get('error')}"}), 401
        master_token = ex_res["master_token"]

    # Google Play Games token
    tok_res = get_games_oauth_token(email, master_token, android_id)
    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": f"Play Games টোকেন পাওয়া যায়নি: {tok_res.get('error')}"}), 401

    access_token = tok_res["access_token"]
    profile_res = get_player_profile(access_token)

    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "গুগল প্লে গেমস প্রোফাইল লোড হয়নি।"}), 400

    session_id = f"sess_{android_id}"
    SESSIONS[session_id] = {
        "email": email,
        "master_token": master_token,
        "android_id": android_id,
        "last_active": time.time()
    }

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "email": email,
        "master_token": master_token,
        "android_id": android_id,
        "profile": format_profile(profile_res)
    })

@app.route("/api/login/master", methods=["POST"])
def login_with_master_token():
    return login_with_token()

@app.route("/api/login/password", methods=["POST"])
def login_with_password():
    """
    Direct login with Email and Google App Password (16-character password).
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "error": "Email এবং Password দেওয়া হয়নি।"}), 400

    android_id = generate_android_id()
    login_res = perform_google_login(email, password, android_id)

    if not login_res.get("ok"):
        err_msg = login_res.get("message") or login_res.get("error")
        if "BadAuthentication" in str(err_msg):
            return jsonify({
                "ok": False,
                "error": "BadAuthentication: গুগল এই পাসওয়ার্ড অনুমোদন করেনি। দয়া করে ১৬ অক্ষরের Google App Password ব্যবহার করুন অথবা EmbeddedSetup টোকেন দিয়ে লগইন করুন।"
            }), 401
        return jsonify({"ok": False, "error": f"লগইন ব্যর্থ: {err_msg}"}), 401

    master_token = login_res["master_token"]

    tok_res = get_games_oauth_token(email, master_token, android_id)
    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": f"Play Games টোকেন পাওয়া যায়নি: {tok_res.get('error')}"}), 401

    access_token = tok_res["access_token"]
    profile_res = get_player_profile(access_token)

    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "গুগল প্লে গেমস প্রোফাইল লোড করা যায়নি।"}), 400

    session_id = f"sess_{android_id}"
    SESSIONS[session_id] = {
        "email": email,
        "master_token": master_token,
        "android_id": android_id,
        "last_active": time.time()
    }

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "email": email,
        "master_token": master_token,
        "android_id": android_id,
        "profile": format_profile(profile_res)
    })

@app.route("/api/session/restore", methods=["POST"])
def restore_session():
    """
    Restores session from client's stored master_token & android_id.
    Guarantees user stays logged in until explicit Sign Out!
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    android_id = data.get("android_id", "").strip()

    if not email or not master_token or not android_id:
        return jsonify({"ok": False, "error": "সেশন ডেটা অসম্পূর্ণ।"}), 400

    tok_res = get_games_oauth_token(email, master_token, android_id)
    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": "সেশন এক্সপায়ার হয়েছে। অনুগ্রহ করে পুনরায় লগইন করুন。"}), 401

    access_token = tok_res["access_token"]
    profile_res = get_player_profile(access_token)

    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "প্রোফাইল লোড করা যায়নি।"}), 400

    session_id = f"sess_{android_id}"
    SESSIONS[session_id] = {
        "email": email,
        "master_token": master_token,
        "android_id": android_id,
        "last_active": time.time()
    }

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "email": email,
        "profile": format_profile(profile_res)
    })

@app.route("/api/profile", methods=["POST"])
def get_live_profile():
    """Fetch live player profile & fresh XP from Google"""
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    android_id = data.get("android_id", "").strip()

    tok_res = get_games_oauth_token(email, master_token, android_id)
    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": "টোকেন এরর"}), 401

    profile_res = get_player_profile(tok_res["access_token"])
    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "প্রোফাইল পাওয়া যায়নি"}), 400

    return jsonify({"ok": True, "profile": format_profile(profile_res)})

@app.route("/api/games", methods=["GET"])
def get_games_list():
    """Return catalog of supported games"""
    games = []
    for k, v in SUPPORTED_GAMES.items():
        games.append({
            "id": k,
            "title": v["title"],
            "package": v["package"],
            "desc": v["desc"]
        })
    return jsonify({"ok": True, "games": games})

@app.route("/api/unlock", methods=["POST"])
def unlock_game():
    """
    Unlock achievements for a specific game on behalf of the player.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    android_id = data.get("android_id", "").strip()
    game_id = str(data.get("game_id", "1")).strip()
    count_requested = int(data.get("count", 5))

    if game_id not in SUPPORTED_GAMES:
        return jsonify({"ok": False, "error": "অননুমোদিত গেম সিলেক্ট করা হয়েছে।"}), 400

    game = SUPPORTED_GAMES[game_id]

    # Get game-specific OAuth token
    tok_res = get_games_oauth_token(
        email=email,
        master_token=master_token,
        android_id=android_id,
        app_package=game["package"],
        client_sig=game["client_sig"]
    )

    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": f"গেম অথেনটিকেশন ব্যর্থ: {tok_res.get('error')}"}), 401

    game_token = tok_res["access_token"]

    # Fetch game achievement definitions
    try:
        defs_res = requests.get(f"{GAMES_API_BASE}/achievements", headers=get_headers(game_token), timeout=10)
        if defs_res.status_code != 200:
            return jsonify({"ok": False, "error": "গেমটির এচিভমেন্ট ডেটা পাওয়া যায়নি।"}), 400
        all_defs = defs_res.json().get("items", [])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    # Fetch player's current achievements to find locked ones
    try:
        p_res = requests.get(f"{GAMES_API_BASE}/players/me/achievements", headers=get_headers(game_token), timeout=10)
        p_items = p_res.json().get("items", []) if p_res.status_code == 200 else []
    except Exception:
        p_items = []

    already_unlocked = {a.get("id") for a in p_items if a.get("achievementState") == "UNLOCKED"}

    targets = []
    for d in all_defs:
        if d.get("id") not in already_unlocked:
            targets.append(d)
            if len(targets) >= count_requested:
                break

    if not targets:
        return jsonify({
            "ok": True,
            "message": "এই গেমের সকল এচিভমেন্ট আপনার অ্যাকাউন্টে আগেই আনলক করা হয়েছে!",
            "newly_unlocked_count": 0,
            "earned_xp": 0
        })

    # Execute Unlocks
    newly_count = 0
    earned_xp = 0
    unlocked_list = []

    for ach in targets:
        ach_id = ach.get("id")
        ach_name = ach.get("name", "Achievement")
        ach_type = ach.get("achievementType", "STANDARD")
        total_steps = ach.get("totalSteps", 1)
        xp = int(ach.get("experiencePoints", 500) or 500)

        if ach_type == "INCREMENTAL" and total_steps:
            res = set_achievement_steps(game_token, ach_id, total_steps)
        else:
            res = unlock_achievement(game_token, ach_id)

        if res.get("ok"):
            newly = res.get("newly_unlocked", False)
            if newly:
                newly_count += 1
                earned_xp += xp
                unlocked_list.append({"id": ach_id, "name": ach_name, "xp": xp})
        time.sleep(0.5)

    # Fetch fresh updated profile
    base_tok = get_games_oauth_token(email, master_token, android_id)
    fresh_profile = None
    if base_tok.get("ok"):
        prof_res = get_player_profile(base_tok["access_token"])
        if prof_res.get("ok"):
            fresh_profile = format_profile(prof_res)

    return jsonify({
        "ok": True,
        "game_title": game["title"],
        "newly_unlocked_count": newly_count,
        "earned_xp": earned_xp,
        "unlocked_items": unlocked_list,
        "profile": fresh_profile
    })

def format_profile(raw_profile: dict) -> dict:
    """Format Google Play Games profile into clean frontend structure"""
    exp = raw_profile.get("experience", {})
    cur_xp = int(exp.get("currentExperiencePoints", 0) or 0)
    cur_lvl_info = exp.get("currentLevel", {})
    next_lvl_info = exp.get("nextLevel", {})

    cur_level = cur_lvl_info.get("level", 1)
    min_xp = int(cur_lvl_info.get("minExperiencePoints", 0) or 0)
    max_xp = int(cur_lvl_info.get("maxExperiencePoints", cur_xp + 10000) or (cur_xp + 10000))

    # Calculate level progress percentage
    span = max_xp - min_xp
    progress_pct = 0
    if span > 0:
        progress_pct = min(100, max(0, round(((cur_xp - min_xp) / span) * 100)))

    return {
        "player_id": raw_profile.get("player_id"),
        "display_name": raw_profile.get("display_name"),
        "avatar_url": raw_profile.get("avatar_url") or "https://play-lh.googleusercontent.com/F2GQg7COWTsvO9LS3lhlcsKQOdoG2m7uUruEHxzhuPlZ7AxAwPncHfk0kkNfq_8A4QM3=w512-h512",
        "current_level": cur_level,
        "current_xp": cur_xp,
        "min_xp": min_xp,
        "max_xp": max_xp,
        "next_level": next_lvl_info.get("level", cur_level + 1),
        "progress_pct": progress_pct
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 VAREON Play Quest Unlocker Server running on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
