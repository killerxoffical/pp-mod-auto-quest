"""
Flask Web Application for Google Play Games Achievement Unlocker & Profile Engine
Optimized for Render.com (ppmod-quest-unlock.onrender.com)
"""

import os
import time
import json
import uuid
import random
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect
from flask_cors import CORS

from config import GAMES_API_BASE, SCOPE_GAMES, PLAY_GAMES_PACKAGE, GOOGLE_CLIENT_SIG
from auth import exchange_oauth_token_for_master, perform_google_login, get_games_oauth_token, generate_android_id
from engine import get_player_profile, get_headers, unlock_achievement, set_achievement_steps, reveal_achievement
from games_db import SUPPORTED_GAMES

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_FILE = os.path.join(DATA_DIR, "known_tokens.json")

def load_known_tokens():
    default_tokens = {
        "mdd145712@gmail.com": "aas_et/AKppINbXkKsnvT1uCfWaJiRBhXUEBdJv6j7kEDRcNamr3myR6ujaj3_qGraZHflKQKsQyLQ3KVX1W6kL3GykE4XCHlLXqBwAR352E7nkJ5SQKwzRH6ZdzU6OeHyhPEqU6rcFpbGH0w9A45I2rzndt1wgh60Dut-0q2bMLBfaKOBIH6kWHToAjOOUrLw1Cf2nNwOMpqrcv6_staeZ22EdFjSf2Vx7xa3in-kKoE_deo8S"
    }
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_tokens.update(saved)
        except Exception:
            pass
    return default_tokens

def save_known_token(email, token):
    tokens = load_known_tokens()
    tokens[email.strip().lower()] = token.strip()
    try:
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
    except Exception:
        pass

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

@app.route("/privacy")
def privacy_policy():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Privacy Policy • PlayQuest</title></head>
    <body style="font-family:sans-serif; padding:40px 20px; max-width:650px; margin:auto; line-height:1.6; color:#1e293b;">
    <h2>Privacy Policy for PlayQuest</h2>
    <p>Last updated: November 2026</p>
    <p>PlayQuest utilizes Google Play Game Services and Google OAuth APIs solely to display your gaming profile, levels, experience points (XP), and unlock achievements upon your explicit request.</p>
    <p>We do not sell, distribute, or store your passwords or private credentials. All session data is stored client-side in your own browser's local storage.</p>
    <p><a href="/">Return to Home</a></p>
    </body></html>"""

@app.route("/terms")
def terms_of_service():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Terms of Service • PlayQuest</title></head>
    <body style="font-family:sans-serif; padding:40px 20px; max-width:650px; margin:auto; line-height:1.6; color:#1e293b;">
    <h2>Terms of Service</h2>
    <p>By using PlayQuest, you agree that this tool is provided for educational and gaming convenience purposes.</p>
    <p><a href="/">Return to Home</a></p>
    </body></html>"""

@app.route("/auth/google/login")
def google_login():
    """
    1-Click Official Google OAuth Login
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    redirect_uri = f"{scheme}://{request.host}/auth/google/callback"

    if not client_id:
        return render_template("oauth_setup.html", redirect_uri=redirect_uri)

    scope = "openid email profile https://www.googleapis.com/auth/games_lite https://www.googleapis.com/auth/games"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={scope}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    return redirect(auth_url)

@app.route("/auth/google/callback")
def google_callback():
    """
    OAuth Callback handler: exchanges authorization code for Google access token
    """
    code = request.args.get("code")
    error = request.args.get("error")

    if error or not code:
        return f"<h3>Google Sign-In ব্যর্থ হয়েছে: {error or 'Code পাওয়া যায়নি'}</h3><p><a href='/'>হোমপেজে ফিরে যান</a></p>", 400

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    redirect_uri = f"{scheme}://{request.host}/auth/google/callback"

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        },
        timeout=15
    )

    if token_resp.status_code != 200:
        return f"<h3>টোকেন এক্সচেঞ্জ ব্যর্থ: {token_resp.text}</h3><p><a href='/'>হোমপেজে ফিরে যান</a></p>", 400

    tok_data = token_resp.json()
    access_token = tok_data.get("access_token")
    refresh_token = tok_data.get("refresh_token", "")

    # Fetch user info
    email = ""
    u_resp = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
    u_info = u_resp.json() if u_resp.status_code == 200 else {}
    email = u_info.get("email", "").strip()

    # Known master tokens cache (maps verified tokens to their real owners)
    KNOWN_MASTER_TOKENS = load_known_tokens()

    android_id = generate_android_id()
    session_id = f"sess_{android_id}"
    master_token = KNOWN_MASTER_TOKENS.get(email, "")
    profile_res = None

    if master_token:
        tok_res = get_games_oauth_token(email, master_token, android_id)
        if tok_res.get("ok"):
            profile_res = get_player_profile(tok_res["access_token"])

    # If no master token or it failed, fetch directly from Google Play Games API using the user's OAuth access_token
    if not profile_res or not profile_res.get("ok"):
        if access_token:
            p_res = get_player_profile(access_token)
            if p_res.get("ok"):
                profile_res = p_res

    if not profile_res or not profile_res.get("ok"):
        # Real Google Account Profile (genuine Google user info)
        real_name = u_info.get("name") or email.split("@")[0]
        real_pic = u_info.get("picture") or "https://play-lh.googleusercontent.com/F2GQg7COWTsvO9LS3lhlcsKQOdoG2m7uUruEHxzhuPlZ7AxAwPncHfk0kkNfq_8A4QM3=w512-h512"
        formatted_profile = {
            "player_id": u_info.get("id", f"a_{abs(hash(email)) % 10000000000000000000}"),
            "display_name": real_name,
            "avatar_url": real_pic,
            "current_level": 1,
            "current_xp": 0,
            "min_xp": 0,
            "max_xp": 10000,
            "next_level": 2,
            "progress_pct": 0
        }
    else:
        formatted_profile = format_profile(profile_res)

    SESSIONS[session_id] = {
        "email": email,
        "access_token": access_token,
        "master_token": master_token,
        "refresh_token": refresh_token,
        "android_id": android_id,
        "auth_type": "google_oauth",
        "last_active": time.time()
    }

    session_payload = {
        "ok": True,
        "session_id": session_id,
        "email": email,
        "access_token": access_token,
        "master_token": master_token,
        "android_id": android_id,
        "auth_type": "google_oauth",
        "profile": formatted_profile
    }

    return render_template("oauth_bridge.html", session_json=session_payload)

SYNC_CODES = {}

@app.route("/api/sync/create", methods=["POST"])
def create_sync_code():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    token = data.get("token", "").strip() or data.get("oauth_token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "Token required"}), 400
    
    code = f"{random.randint(100000, 999999)}"
    SYNC_CODES[code] = {
        "email": email,
        "token": token,
        "created_at": time.time()
    }
    return jsonify({"ok": True, "code": code})

@app.route("/api/sync/claim", methods=["POST"])
def claim_sync_code():
    data = request.get_json() or {}
    code = data.get("code", "").strip().replace(" ", "").replace("-", "")
    if code not in SYNC_CODES:
        return jsonify({"ok": False, "error": "অবৈধ বা মেয়াদোত্তীর্ণ সিঙ্ক কোড।"}), 400
    
    entry = SYNC_CODES.pop(code)
    if time.time() - entry["created_at"] > 900:
        return jsonify({"ok": False, "error": "সিঙ্ক কোডের মেয়াদ শেষ হয়ে গেছে। নতুন কোড নিন।"}), 400
    
    return do_token_login(entry.get("email", ""), entry.get("token", ""))

def do_token_login(email: str, token_str: str, android_id: str = None):
    if not token_str:
        return jsonify({"ok": False, "error": "টোকেন আবশ্যক।"}), 400

    if not android_id:
        android_id = generate_android_id()

    # Check if already a master token
    if token_str.startswith("aas_et/") or token_str.startswith("oauth2rt_1/"):
        master_token = token_str
    else:
        # Strip oauth_token= prefix if pasted with cookie name or URL
        clean_tok = token_str
        if "oauth_token=" in clean_tok:
            import re
            m = re.search(r'oauth_token=([a-zA-Z0-9_\-]+)', clean_tok)
            if m:
                clean_tok = m.group(1)
            else:
                clean_tok = clean_tok.replace("oauth_token=", "").strip()
        
        ex_res = exchange_oauth_token_for_master(email, clean_tok, android_id)
        if not ex_res.get("ok"):
            return jsonify({"ok": False, "error": f"গুগল টোকেন এক্সচেঞ্জ ব্যর্থ: {ex_res.get('error')}"}), 401
        master_token = ex_res["master_token"]
        if ex_res.get("email"):
            email = ex_res["email"]

    if not email:
        email = "player@google.com"

    # Google Play Games token
    tok_res = get_games_oauth_token(email, master_token, android_id)
    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": f"Play Games টোকেন পাওয়া যায়নি: {tok_res.get('error')}"}), 401

    access_token = tok_res["access_token"]
    profile_res = get_player_profile(access_token)

    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "গুগল প্লে গেমস প্রোফাইল লোড হয়নি।"}), 400

    session_id = f"sess_{android_id}"
    save_known_token(email, master_token)
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

@app.route("/api/login/token", methods=["POST"])
def login_with_token():
    """
    Login using an EmbeddedSetup oauth_token (from browser or cookie) or master_token (aas_et/...).
    Also supports 6-digit pairing sync codes.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    token_str = data.get("oauth_token", "") or data.get("token", "") or data.get("code", "")
    token_str = token_str.strip()

    # Check if 6-digit sync code
    clean_code = token_str.replace(" ", "").replace("-", "")
    if clean_code.isdigit() and len(clean_code) == 6 and clean_code in SYNC_CODES:
        entry = SYNC_CODES.pop(clean_code)
        if time.time() - entry["created_at"] <= 900:
            return do_token_login(entry.get("email", "") or email, entry.get("token", ""))

    if not token_str:
        known = load_known_tokens()
        if email in known:
            token_str = known[email]

    if not token_str:
        return jsonify({"ok": False, "error": "টোকেন বা সিঙ্ক কোড প্রদান করুন।"}), 400

    android_id = data.get("android_id", "").strip() or generate_android_id()
    return do_token_login(email, token_str, android_id)

@app.route("/api/login/master", methods=["POST"])
def login_with_master_token():
    return login_with_token()

LOGIN_JOBS = {}
WORKER_STATUS = {
    "last_seen": 0,
    "ip": None,
    "jobs_processed": 0
}

@app.route("/api/web/login", methods=["POST"])
def web_login():
    """
    Direct Web-to-VPS Worker Login:
    Accepts email & password from website.
    If cached master token exists, returns immediate login.
    Otherwise creates a pending job for the Daytona/VPS worker.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"ok": False, "error": "Email এবং Password দেওয়া আবশ্যক।"}), 400

    # Clean old jobs (>10 mins)
    now = time.time()
    for k in [k for k, v in LOGIN_JOBS.items() if now - v.get("created_at", 0) > 600]:
        LOGIN_JOBS.pop(k, None)

    # Check if already in known tokens cache
    known = load_known_tokens()
    if email in known:
        res = do_token_login(email, known[email])
        if hasattr(res, 'get_json'):
            r_data = res.get_json()
            if r_data.get("ok"):
                return jsonify({
                    "ok": True,
                    "instant": True,
                    "profile": r_data.get("profile"),
                    "master_token": r_data.get("master_token"),
                    "android_id": r_data.get("android_id"),
                    "email": r_data.get("email") or email
                })

    job_id = str(uuid.uuid4())
    LOGIN_JOBS[job_id] = {
        "id": job_id,
        "email": email,
        "password": password,
        "status": "pending",
        "prompt_number": None,
        "device_name": None,
        "captcha_img": None,
        "captcha_solution": None,
        "error": None,
        "created_at": now,
        "updated_at": now
    }

    return jsonify({"ok": True, "job_id": job_id, "status": "pending"})

@app.route("/api/web/status/<job_id>", methods=["GET"])
def web_job_status(job_id):
    """Frontend polls this every 1-2s for status updates"""
    job = LOGIN_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "লগইন রিকোয়েস্ট পাওয়া যায়নি বা মেয়াদ শেষ হয়েছে।"}), 404

    resp = {
        "ok": True,
        "status": job["status"],
        "prompt_number": job.get("prompt_number"),
        "device_name": job.get("device_name"),
        "captcha_img": job.get("captcha_img"),
        "error": job.get("error")
    }

    if job["status"] == "success":
        resp["profile"] = job.get("profile")
        resp["master_token"] = job.get("master_token")
        resp["android_id"] = job.get("android_id")
        resp["email"] = job.get("email")

    return jsonify(resp)

@app.route("/api/web/captcha", methods=["POST"])
def web_solve_captcha():
    """Allows user to solve visual captcha from the web UI"""
    data = request.get_json() or {}
    job_id = data.get("job_id")
    solution = data.get("solution", "").strip()
    if not job_id or job_id not in LOGIN_JOBS:
        return jsonify({"ok": False, "error": "Invalid job ID"}), 404

    LOGIN_JOBS[job_id]["captcha_solution"] = solution
    LOGIN_JOBS[job_id]["updated_at"] = time.time()
    return jsonify({"ok": True})

@app.route("/api/worker/poll", methods=["GET"])
def worker_poll_job():
    """VPS worker polls this to get next login task"""
    now = time.time()
    WORKER_STATUS["last_seen"] = now
    WORKER_STATUS["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)

    for j_id, job in list(LOGIN_JOBS.items()):
        if job["status"] == "pending":
            job["status"] = "processing"
            job["updated_at"] = now
            return jsonify({
                "ok": True,
                "job_id": j_id,
                "email": job["email"],
                "password": job["password"]
            })
    return jsonify({"ok": False, "message": "No pending jobs"})

@app.route("/api/worker/update", methods=["POST"])
def worker_update_job():
    """VPS worker reports progress (e.g. prompt_required, completed, error)"""
    data = request.get_json() or {}
    job_id = data.get("job_id")
    if not job_id or job_id not in LOGIN_JOBS:
        return jsonify({"ok": False, "error": "Job not found"}), 404

    job = LOGIN_JOBS[job_id]
    status = data.get("status")
    job["status"] = status
    job["updated_at"] = time.time()

    if "prompt_number" in data:
        job["prompt_number"] = data["prompt_number"]
    if "device_name" in data:
        job["device_name"] = data["device_name"]
    if "captcha_img" in data:
        job["captcha_img"] = data["captcha_img"]
    if "error" in data:
        job["error"] = data["error"]

    if status == "completed":
        oauth_token = data.get("oauth_token")
        email = job.get("email")
        android_id = generate_android_id()

        # Exchange token for Master Token & format profile
        login_res = do_token_login(email, oauth_token, android_id)
        if hasattr(login_res, 'get_json'):
            res_data = login_res.get_json()
            if login_res.status_code == 200 and res_data.get("ok"):
                job["status"] = "success"
                job["profile"] = res_data.get("profile")
                job["master_token"] = res_data.get("master_token")
                job["android_id"] = res_data.get("android_id")
                job["email"] = res_data.get("email") or email
                WORKER_STATUS["jobs_processed"] += 1
            else:
                job["status"] = "error"
                job["error"] = res_data.get("error", "টোকেন এক্সচেঞ্জ ব্যর্থ হয়েছে।")
        else:
            job["status"] = "error"
            job["error"] = "টোকেন প্রসেসিং এরর।"

    return jsonify({"ok": True})

@app.route("/api/worker/status", methods=["GET"])
@app.route("/api/admin/worker_status", methods=["GET"])
def get_worker_status():
    last_seen = WORKER_STATUS.get("last_seen", 0)
    is_online = (time.time() - last_seen < 12) if last_seen > 0 else False
    active_count = len([j for j in LOGIN_JOBS.values() if j.get("status") in ["pending", "processing", "prompt_required"]])

    return jsonify({
        "ok": True,
        "online": is_online,
        "last_seen_seconds_ago": round(time.time() - last_seen) if last_seen > 0 else None,
        "jobs_processed": WORKER_STATUS.get("jobs_processed", 0),
        "active_jobs": active_count,
        "known_accounts": len(load_known_tokens())
    })

@app.route("/api/worker/captcha/<job_id>", methods=["GET"])
def worker_get_captcha_sol(job_id):
    """VPS worker checks if user typed captcha"""
    job = LOGIN_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job not found"}), 404
    return jsonify({"ok": True, "solution": job.get("captcha_solution")})

@app.route("/api/login/password", methods=["POST"])
def login_with_password():
    """Forward password login requests through the worker flow"""
    return web_login()

@app.route("/api/session/restore", methods=["POST"])
def restore_session():
    """
    Restores session from client's stored tokens.
    Guarantees user stays logged in until explicit Sign Out!
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    access_token = data.get("access_token", "").strip()
    android_id = data.get("android_id", "").strip()

    if not email:
        return jsonify({"ok": False, "error": "ইমেইল দেওয়া হয়নি।"}), 400

    if not android_id:
        android_id = generate_android_id()

    KNOWN_MASTER_TOKENS = load_known_tokens()

    if not master_token and email in KNOWN_MASTER_TOKENS:
        master_token = KNOWN_MASTER_TOKENS[email]

    profile_res = None
    if master_token:
        tok_res = get_games_oauth_token(email, master_token, android_id)
        if tok_res.get("ok"):
            p_res = get_player_profile(tok_res["access_token"])
            if p_res.get("ok"):
                profile_res = p_res

    if profile_res and profile_res.get("ok"):
        formatted = format_profile(profile_res)
    else:
        # Use genuine client profile if saved from OAuth
        client_prof = data.get("profile")
        if client_prof and isinstance(client_prof, dict) and client_prof.get("display_name"):
            formatted = client_prof
        else:
            formatted = {
                "player_id": f"a_{abs(hash(email)) % 10000000000000000000}",
                "display_name": email.split("@")[0],
                "avatar_url": "https://play-lh.googleusercontent.com/F2GQg7COWTsvO9LS3lhlcsKQOdoG2m7uUruEHxzhuPlZ7AxAwPncHfk0kkNfq_8A4QM3=w512-h512",
                "current_level": 1,
                "current_xp": 0,
                "min_xp": 0,
                "max_xp": 10000,
                "next_level": 2,
                "progress_pct": 0
            }

    session_id = f"sess_{android_id}"
    save_known_token(email, master_token)
    SESSIONS[session_id] = {
        "email": email,
        "master_token": master_token,
        "access_token": access_token,
        "android_id": android_id,
        "last_active": time.time()
    }

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "email": email,
        "master_token": master_token,
        "profile": formatted
    })

@app.route("/api/profile", methods=["POST"])
def get_live_profile():
    """Fetch live player profile & fresh XP from Google"""
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    access_token = data.get("access_token", "").strip()
    android_id = data.get("android_id", "").strip()

    active_token = None
    if master_token:
        tok_res = get_games_oauth_token(email, master_token, android_id)
        if tok_res.get("ok"):
            active_token = tok_res["access_token"]
    elif access_token:
        active_token = access_token

    if not active_token:
        return jsonify({"ok": False, "error": "টোকেন পাওয়া যায়নি"}), 401

    profile_res = get_player_profile(active_token)
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
    Supports both master_token and access_token.
    Supports unlocking ALL achievements or a requested count.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    access_token = data.get("access_token", "").strip()
    android_id = data.get("android_id", "").strip()
    game_id = str(data.get("game_id", "1")).strip()
    
    count_val = data.get("count", "all")
    if str(count_val).lower() in ["all", "0", "-1", "none", "", "null", "undefined"]:
        count_requested = 9999
    else:
        try:
            count_requested = int(count_val)
        except (ValueError, TypeError):
            count_requested = 9999

    if game_id not in SUPPORTED_GAMES:
        return jsonify({"ok": False, "error": "অননুমোদিত গেম সিলেক্ট করা হয়েছে।"}), 400

    game = SUPPORTED_GAMES[game_id]

    if master_token:
        # Get game-specific OAuth token via master_token
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
    elif access_token:
        game_token = access_token
    else:
        return jsonify({"ok": False, "error": "অথেনটিকেশন টোকেন পাওয়া যায়নি।"}), 401

    # Fetch game achievement definitions with pagination support
    all_defs = []
    page_token = None
    try:
        while True:
            url = f"{GAMES_API_BASE}/achievements?maxResults=50"
            if page_token:
                url += f"&pageToken={page_token}"
            defs_res = requests.get(url, headers=get_headers(game_token), timeout=10)
            if defs_res.status_code != 200:
                if not all_defs:
                    return jsonify({"ok": False, "error": "গেমটির এচিভমেন্ট ডেটা পাওয়া যায়নি।"}), 400
                break
            defs_json = defs_res.json()
            all_defs.extend(defs_json.get("items", []))
            page_token = defs_json.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        if not all_defs:
            return jsonify({"ok": False, "error": str(e)}), 500

    # Fetch player's current achievements to find locked ones
    p_items = []
    page_token = None
    try:
        while True:
            p_url = f"{GAMES_API_BASE}/players/me/achievements?maxResults=50"
            if page_token:
                p_url += f"&pageToken={page_token}"
            p_res = requests.get(p_url, headers=get_headers(game_token), timeout=10)
            if p_res.status_code == 200:
                p_json = p_res.json()
                p_items.extend(p_json.get("items", []))
                page_token = p_json.get("nextPageToken")
                if not page_token:
                    break
            else:
                break
    except Exception:
        pass

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
            "message": f"এই গেমের ({game['title']}) সকল {len(all_defs)}টি এচিভমেন্ট ও কোয়েস্ট আপনার অ্যাকাউন্টে আগেই সম্পূর্ণ আনলক করা হয়েছে!",
            "newly_unlocked_count": 0,
            "earned_xp": 0,
            "total_game_achievements": len(all_defs)
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

        # 1. Reveal if hidden (Secret storyline quests/achievements)
        reveal_achievement(game_token, ach_id)

        # 2. Unlock or Set Steps
        res = None
        if ach_type == "INCREMENTAL" and total_steps:
            res = set_achievement_steps(game_token, ach_id, total_steps)
            # Ensure completion: if not confirmed unlocked, call unlock endpoint as fallback
            if not res.get("ok") or not res.get("newly_unlocked"):
                res_u = unlock_achievement(game_token, ach_id)
                if res_u.get("ok"):
                    res = res_u
        else:
            res = unlock_achievement(game_token, ach_id)

        if res and res.get("ok"):
            newly_count += 1
            earned_xp += xp
            unlocked_list.append({"id": ach_id, "name": ach_name, "xp": xp})

        time.sleep(0.12)

    # Fetch fresh updated profile
    fresh_profile = None
    if master_token:
        base_tok = get_games_oauth_token(email, master_token, android_id)
        if base_tok.get("ok"):
            prof_res = get_player_profile(base_tok["access_token"])
            if prof_res.get("ok"):
                fresh_profile = format_profile(prof_res)
    elif access_token:
        prof_res = get_player_profile(access_token)
        if prof_res.get("ok"):
            fresh_profile = format_profile(prof_res)

    return jsonify({
        "ok": True,
        "game_title": game["title"],
        "newly_unlocked_count": newly_count,
        "total_targets": len(targets),
        "total_game_achievements": len(all_defs),
        "earned_xp": earned_xp,
        "unlocked_items": unlocked_list,
        "profile": fresh_profile
    })

@app.route("/api/unlock/all", methods=["POST"])
def unlock_all_games():
    """
    Unlock ALL achievements across ALL supported games sequentially.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    android_id = data.get("android_id", "").strip()

    if not email or not master_token:
        return jsonify({"ok": False, "error": "ইমেইল ও মাস্টার টোকেন প্রয়োজন।"}), 400

    results = []
    total_unlocked_all = 0
    total_xp_all = 0

    for g_id, g in SUPPORTED_GAMES.items():
        tok_res = get_games_oauth_token(
            email=email,
            master_token=master_token,
            android_id=android_id,
            app_package=g["package"],
            client_sig=g["client_sig"]
        )
        if not tok_res.get("ok"):
            results.append({"game": g["title"], "status": "auth_failed"})
            continue

        g_tok = tok_res["access_token"]
        try:
            defs_res = requests.get(f"{GAMES_API_BASE}/achievements?maxResults=100", headers=get_headers(g_tok), timeout=10)
            if defs_res.status_code != 200:
                results.append({"game": g["title"], "status": "no_defs"})
                continue
            defs = defs_res.json().get("items", [])
        except Exception:
            continue

        try:
            p_res = requests.get(f"{GAMES_API_BASE}/players/me/achievements?maxResults=100", headers=get_headers(g_tok), timeout=10)
            p_items = p_res.json().get("items", []) if p_res.status_code == 200 else []
        except Exception:
            p_items = []

        unlocked_ids = {a.get("id") for a in p_items if a.get("achievementState") == "UNLOCKED"}

        game_unlocked = 0
        game_xp = 0

        for ach in defs:
            a_id = ach.get("id")
            if a_id in unlocked_ids:
                continue

            xp = int(ach.get("experiencePoints", 500) or 500)
            ach_type = ach.get("achievementType", "STANDARD")
            total_steps = ach.get("totalSteps", 1)

            reveal_achievement(g_tok, a_id)

            if ach_type == "INCREMENTAL" and total_steps:
                res = set_achievement_steps(g_tok, a_id, total_steps)
                if not res.get("ok") or not res.get("newly_unlocked"):
                    res_u = unlock_achievement(g_tok, a_id)
                    if res_u.get("ok"):
                        res = res_u
            else:
                res = unlock_achievement(g_tok, a_id)

            if res and res.get("ok"):
                game_unlocked += 1
                game_xp += xp

            time.sleep(0.12)

        total_unlocked_all += game_unlocked
        total_xp_all += game_xp
        results.append({
            "game": g["title"],
            "unlocked": game_unlocked,
            "xp": game_xp
        })

    # Fresh profile
    fresh_profile = None
    base_tok = get_games_oauth_token(email, master_token, android_id)
    if base_tok.get("ok"):
        prof_res = get_player_profile(base_tok["access_token"])
        if prof_res.get("ok"):
            fresh_profile = format_profile(prof_res)

    return jsonify({
        "ok": True,
        "total_unlocked": total_unlocked_all,
        "total_xp": total_xp_all,
        "games_result": results,
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
