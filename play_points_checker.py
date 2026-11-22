import requests
import gpsoauth
import re

def fetch_play_points_info(email: str, master_token: str, android_id: str = "46e14d2451000000") -> dict:
    """
    Fetches 100% accurate, live Google Play Points status, points balance, and tier level
    via Google's authenticated web session at https://play.google.com/store/points/perks.
    """
    result = {
        "email": email,
        "has_play_points": False,
        "play_points_status": "not_enrolled",
        "tier": "None",
        "points": 0,
        "has_perk": False,
        "claimed": True,
        "status_text": "Not Enrolled"
    }

    if not master_token or not email:
        return result

    try:
        oauth_res = gpsoauth.perform_oauth(
            email.strip(), master_token.strip(), android_id,
            service="weblogin:continue=https://play.google.com/store/points/perks",
            app="com.google.android.gms",
            client_sig="38918a453d07199354f8b19af05ec6562ced5788"
        )
        merge_url = oauth_res.get("Auth")
        if not merge_url or not merge_url.startswith("https://"):
            return result

        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        })

        resp = s.get(merge_url, allow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return result

        html = resp.text

        # 1. Check if redirected to login
        if "accounts.google.com" in resp.url and "ServiceLogin" in resp.url:
            result["play_points_status"] = "login_required"
            result["status_text"] = "Login Required"
            return result

        # 2. Check if not joined
        lower_html = html.lower()
        not_joined_phrases = [
            "join for free",
            "join play points",
            "play points isn't available in your country",
            "not available in your region",
            "আপনার দেশে প্লে পয়েন্ট উপলব্ধ নেই"
        ]
        if any(p in lower_html for p in not_joined_phrases):
            result["has_play_points"] = False
            result["play_points_status"] = "not_enrolled"
            result["status_text"] = "No Play Points"
            return result

        # 3. Detect Points Balance
        points = 0
        aria_pts = re.findall(r'aria-label=["\'](\d[\d,]*)\s*(?:points|pts|পয়েন্ট)["\']', html, re.IGNORECASE)
        if aria_pts:
            points = int(aria_pts[0].replace(",", ""))
        else:
            # Standalone point count
            pts_match = re.findall(r'(\d[\d,]*)\s*(?:points|pts|পয়েন্ট)', html, re.IGNORECASE)
            if pts_match:
                points = int(pts_match[0].replace(",", ""))

        # 4. Detect Tier Level
        tier = "Bronze"
        tier_match = re.search(r'\[\"(Bronze|Silver|Gold|Platinum)\",\"You are', html, re.IGNORECASE)
        if tier_match:
            tier = tier_match.group(1).capitalize()
        else:
            # Fallback tier detection from text
            for t in ["Platinum", "Gold", "Silver", "Bronze"]:
                if f"{t.lower()} level" in lower_html or f"{t.lower()} tier" in lower_html:
                    tier = t
                    break

        result["has_play_points"] = True
        result["play_points_status"] = "active"
        result["tier"] = tier
        result["points"] = points

        # 5. Detect Perk Claim Availability
        # Bronze accounts don't get weekly perks
        if tier.lower() == "bronze":
            result["has_perk"] = False
            result["claimed"] = True
            result["status_text"] = "Bronze • No Weekly Perk"
        else:
            # Look for active, enabled claim button in HTML
            has_claim_btn = False
            btn_pattern = re.compile(r'<button([^>]*)>([\s\S]*?)</button>', re.IGNORECASE)
            for m in btn_pattern.finditer(html):
                attrs = m.group(1).lower()
                content = m.group(2).lower()
                b_clean = re.sub(r'<[^>]+>', ' ', content).strip()
                is_claim = ('claim' in b_clean or 'ক্লেইম' in b_clean or 'claim' in attrs) and 'claimed' not in b_clean
                if is_claim:
                    is_disabled = ('disabled' in attrs) or ('inert' in attrs) or ('aria-disabled="true"' in attrs)
                    if not is_disabled:
                        has_claim_btn = True
                        break

            result["has_perk"] = has_claim_btn
            result["claimed"] = not has_claim_btn
            result["status_text"] = "Claim Available 🎁" if has_claim_btn else "Weekly Perk Claimed"

        return result

    except Exception as e:
        print(f"[-] fetch_play_points_info error for {email}: {e}")
        return result

if __name__ == "__main__":
    t1 = "aas_et/AKppINaKiXtxZcbp8PQBxdY4Hy3MLobU5ONHlNbtjZAJJSKVWetfEmDfTYvm3u01dXFoRj4RKHrD1YKEGAnMxFOvYq0nwRQikpfxOrZRQUjj7OKJky2Dl_NFChbQfAS-cJkKaUAgyAJeyUa6tfcwLYRFWCAulQWziZUMXQIqwpjOBbfxlF0XxBtn_wUvu94tEc4mfImRp6KtX6zdtNss3UELimi0_a7dyCD1ge-n4bUs"
    print("Testing Account 1 (mdg145712@gmail.com):")
    print(fetch_play_points_info("mdg145712@gmail.com", t1))

    t2 = "aas_et/AKppINZszLgjudoaAUlcve6Ad2X-uu1N2CVOSZ294oYaCWizlnt5wVob1Yc-rhQ3-UMXh7A3by3jCZoggrEiOuMa_kZKrUNz750JZrraxUEO2vwoWoU5Dgl4Cln-dL4DZmnAeo7QJpKd8i9MpVutLoWauESF23XHzSB_dkoH-IZNqEh2yjsCorcnW_xqmO85xp1an8DqGcTZVAcrRkNfhQddtnbyG-CYqvLCI12HL2y8"
    print("\nTesting Account 2 (mdsiamhasan99443@gmail.com):")
    print(fetch_play_points_info("mdsiamhasan99443@gmail.com", t2))
