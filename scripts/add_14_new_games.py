import json
import os
import re
import sys
import time
import random
import html as html_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
from app import resolve_play_store_gpgs_info

TARGET_PACKAGES = [
    "com.YoStarEN.StellaSora",
    "com.vizorapps.klondike",
    "net.wooga.junes_journey_hidden_object_mystery_game",
    "com.miHoYo.GenshinImpact",
    "com.tinyco.potter",
    "com.nexon.bluearchive",
    "com.king.candycrushsodasaga",
    "com.ghostshippublishing.deeprockgalacticsurvivor",
    "com.digitalextremes.warframemobile",
    "com.playdigious.seaofstars",
    "com.crowdstar.covetHome",
    "com.nianticlabs.pokemongo",
    "com.gramgames.mergedragons",
    "com.more.lastfortress.gp",
]


def fetch_play_store_meta(package: str) -> dict:
    title = package
    icon = "https://play-lh.googleusercontent.com/F2GQg7COWTsvO9LS3lhlcsKQOdoG2m7uUruEHxzhuPlZ7AxAwPncHfk0kkNfq_8A4QM3=w512-h512"
    developer = "Google Play Partner"
    category = "Games"
    try:
        r = requests.get(
            f"https://play.google.com/store/apps/details?id={package}&hl=en&gl=us",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=10,
        )
        if r.status_code == 200:
            text = r.text
            m_og = re.search(r'<meta property="og:image" content="([^"]+)"', text)
            if m_og:
                icon = m_og.group(1).split("=")[0] + "=s0-br30"
            m_title = (
                re.search(r'<meta property="og:title" content="([^"]+)"', text)
                or re.search(r'<h1[^>]*itemprop="name"[^>]*>(?:<span[^>]*>)?([^<]+)', text)
                or re.search(r"<title>([^<]+) - Apps on Google Play</title>", text)
            )
            if m_title:
                raw_t = html_mod.unescape(m_title.group(1)).split(" - Apps on Google Play")[0].strip()
                if raw_t:
                    title = raw_t
            m_dev = re.search(r'"author":\{"@type":"Person","name":"([^"]+)"', text) or re.search(
                r'"author":\{"@type":"Organization","name":"([^"]+)"', text
            )
            if m_dev:
                developer = html_mod.unescape(m_dev.group(1)).strip()
            m_cat = re.search(r'"applicationCategory":"([^"]+)"', text)
            if m_cat:
                category = html_mod.unescape(m_cat.group(1)).replace("GAME_", "").replace("_", " ").title()
    except Exception as e:
        print(f"[-] Meta fetch warn for {package}: {e}")
    return {"title": title, "icon": icon, "developer": developer, "category": category}


def get_master_creds():
    import gpsoauth
    candidates = []
    # 1. Try Cloudflare D1 live registered-devices first
    try:
        r = requests.get("https://ppmod-api.tredarskvt.workers.dev/api/cloud/registered-devices", timeout=10)
        if r.status_code == 200:
            devs = r.json()
            if isinstance(devs, dict) and "data" in devs and isinstance(devs["data"], dict):
                devs = devs["data"]
            if isinstance(devs, dict):
                for dev in devs.values():
                    if not isinstance(dev, dict):
                        continue
                    for acc in dev.get("accounts", []):
                        em = (acc.get("email") or "").strip()
                        tk = (acc.get("token") or acc.get("master_token") or "").strip()
                        if em and tk.startswith("aas_et/"):
                            candidates.append((em, tk))
    except Exception as e:
        print(f"[-] CF registered-devices fetch warn: {e}")

    # 2. Try Cloudflare D1 sync accounts endpoint if available
    try:
        r = requests.get("https://ppmod-api.tredarskvt.workers.dev/api/sync/accounts", timeout=10)
        if r.status_code == 200:
            d = r.json()
            rows = d.get("accounts") or d.get("data") or (d if isinstance(d, list) else [])
            for acc in rows:
                em = (acc.get("email") or "").strip()
                tk = (acc.get("token") or acc.get("master_token") or "").strip()
                if em and tk.startswith("aas_et/"):
                    candidates.append((em, tk))
    except Exception:
        pass

    # 3. Local registered_devices.json and known_tokens.json fallback
    reg_path = os.path.join(ROOT_DIR, "registered_devices.json")
    if os.path.exists(reg_path):
        devs = json.load(open(reg_path, "r", encoding="utf-8"))
        for dev in devs.values():
            if not isinstance(dev, dict):
                continue
            for acc in dev.get("accounts", []):
                em = (acc.get("email") or "").strip()
                tk = (acc.get("token") or "").strip()
                if em and tk.startswith("aas_et/"):
                    candidates.append((em, tk))
    kt_path = os.path.join(ROOT_DIR, "known_tokens.json")
    if os.path.exists(kt_path):
        kt = json.load(open(kt_path, "r", encoding="utf-8"))
        for em, tk in kt.items():
            if str(tk).startswith("aas_et/"):
                candidates.append((em.strip(), str(tk).strip()))

    seen = set()
    print(f"[*] Testing {len(candidates)} candidate master tokens...")
    for em, tk in candidates:
        key = (em.lower(), tk[:25])
        if key in seen:
            continue
        seen.add(key)
        try:
            res = gpsoauth.perform_oauth(
                em, tk, "46e14d2451000000",
                service="androidmarket",
                app="com.android.vending",
                client_sig="38918a453d07199354f8b19af05ec6562ced5788"
            )
            if "Auth" in res:
                return em, tk
        except Exception:
            pass
    return None, None


def resolve_one(pkg, email, master_token):
    meta = fetch_play_store_meta(pkg)
    gpgs = resolve_play_store_gpgs_info(pkg, email=email, master_token=master_token)
    return pkg, meta, gpgs


def main():
    email, master_token = get_master_creds()
    if not email or not master_token:
        print("[-] No valid master token found!")
        sys.exit(1)

    print(f"[+] Using auth account: {email}")
    print(f"[*] Resolving {len(TARGET_PACKAGES)} games in parallel...")

    results = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(resolve_one, pkg, email, master_token): pkg for pkg in TARGET_PACKAGES}
        for fut in as_completed(futs):
            pkg = futs[fut]
            try:
                p, meta, gpgs = fut.result()
                results[p] = (meta, gpgs)
                achs = gpgs.get("achievements", []) if gpgs.get("ok") else []
                print(
                    f"  -> {p} | Title: {meta['title']} | OK={gpgs.get('ok')} | "
                    f"Sig={gpgs.get('client_sig', '')[:12]} | Achs={len(achs)} | Err={gpgs.get('error', '')}"
                )
            except Exception as e:
                print(f"  -> {pkg} EXCEPTION: {e}")
                results[pkg] = ({"title": pkg, "icon": "", "developer": "Google Play Partner", "category": "Games"}, {"ok": False, "error": str(e)})

    db_file = os.path.join(ROOT_DIR, "real_achievements_db.json")
    ps_file = os.path.join(ROOT_DIR, "portal_services.json")
    ps_backup = os.path.join(ROOT_DIR, "portal_services_backup.json")

    rdb = json.load(open(db_file, "r", encoding="utf-8"))
    ps = json.load(open(ps_file, "r", encoding="utf-8"))

    existing_rdb_pkgs = {v.get("package", "").lower(): k for k, v in rdb.items() if isinstance(v, dict)}
    existing_ps_pkgs = {v.get("package", "").lower(): k for k, v in ps.items() if isinstance(v, dict)}

    next_id_num = max([int(k) for k in rdb.keys() if str(k).isdigit()] or [0]) + 1
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    added_with_achs = []
    no_gpgs_achs = []

    for pkg in TARGET_PACKAGES:
        meta, gpgs = results[pkg]
        title = meta["title"]
        icon = meta["icon"]
        developer = meta["developer"]
        category = meta["category"]
        achs = gpgs.get("achievements", []) if gpgs.get("ok") else []
        client_sig = gpgs.get("client_sig") or ""
        total_xp = gpgs.get("total_xp", 0)

        if not gpgs.get("ok") or len(achs) == 0:
            no_gpgs_achs.append((pkg, title, gpgs.get("error", "0 GPGS achievements on Google Play")))
            continue

        gid = existing_rdb_pkgs.get(pkg.lower())
        if not gid:
            gid = str(next_id_num)
            next_id_num += 1

        rdb[gid] = {
            "id": gid,
            "title": title,
            "developer": developer,
            "package": pkg,
            "client_sig": client_sig,
            "category": category,
            "section": "quest_unlocker",
            "icon": icon,
            "desc": f"{len(achs)} live GPGS achievements for {title}.",
            "achievements_count": len(achs),
            "total_xp": total_xp,
            "tags": [
                "Official GPGS",
                "Real Achievements",
                "Live Cloud Sync",
                "Google Play Quest",
            ],
            "gpgs_verified": True,
            "achievements": achs,
        }

        portal_all_quests = []
        for a in achs:
            portal_all_quests.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "description": a.get("description") or f"Unlock {a.get('name')} in {title}",
                "experiencePoints": a.get("experiencePoints", 1000),
                "achievementType": a.get("achievementType", "STANDARD"),
                "totalSteps": a.get("totalSteps"),
                "unlockedIconUrl": a.get("unlockedIconUrl") or icon,
            })

        # Pick 2 or 3 random quests (preferring STANDARD achievements when available)
        std_quests = [q for q in portal_all_quests if q.get("achievementType") == "STANDARD"]
        pool = std_quests if len(std_quests) >= 2 else portal_all_quests
        pick_count = min(len(pool), random.choice([2, 3]))
        selected_quests = random.sample(pool, pick_count) if pick_count > 0 else []
        selected_quest_ids = [q["id"] for q in selected_quests]

        ps_gid = existing_ps_pkgs.get(pkg.lower()) or gid
        existing_entry = ps.get(ps_gid, {})

        ps[ps_gid] = {
            "service_id": existing_entry.get("service_id") or f"srv_{ps_gid}",
            "game_id": ps_gid,
            "id": ps_gid,
            "title": title,
            "package": pkg,
            "client_sig": client_sig,
            "developer": developer,
            "category": category,
            "icon": icon,
            "section": "quest_unlocker",
            "enabled": True,
            "no_data": False,
            "is_official": False,
            "unofficial_note": "Random 2-3 achievements selected (No official Play Points quest)",
            "total_quests_count": len(portal_all_quests),
            "selected_quests_count": len(selected_quests),
            "selected_quest_ids": selected_quest_ids,
            "selected_quests": selected_quests,
            "all_quests": portal_all_quests,
            "created_at": existing_entry.get("created_at") or now_str,
            "updated_at": now_str,
        }

        added_with_achs.append((ps_gid, pkg, title, len(achs), len(selected_quests)))

    with open(db_file, "w", encoding="utf-8") as f:
        json.dump(rdb, f, indent=2, ensure_ascii=False)
    with open(ps_file, "w", encoding="utf-8") as f:
        json.dump(ps, f, indent=2, ensure_ascii=False)
    with open(ps_backup, "w", encoding="utf-8") as f:
        json.dump(ps, f, indent=2, ensure_ascii=False)

    print("\n================ SUMMARY ================")
    print(f"ADDED WITH REAL GPGS ACHIEVEMENTS ({len(added_with_achs)}):")
    for gid, pkg, title, tot, sel in added_with_achs:
        print(f"  [ID {gid}] {title} ({pkg}) -> {tot} total achs, {sel} random public quests")
    print(f"\nNO GPGS ACHIEVEMENTS FOUND ({len(no_gpgs_achs)}):")
    for pkg, title, err in no_gpgs_achs:
        print(f"  [SKIPPED] {title} ({pkg}) -> {err}")


if __name__ == "__main__":
    main()
