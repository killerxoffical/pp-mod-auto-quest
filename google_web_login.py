"""
Google EmbeddedSetup Authenticator
Opens an interactive Chrome window for Google Sign-In and captures the oauth_token cookie.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def login_and_get_oauth_token(email: str = "", password: str = "", headless: bool = False, timeout_sec: int = 180) -> dict:
    """
    Opens Google's official Android EmbeddedSetup sign-in page.
    Allows user to smoothly sign in in Chrome.
    Continuously listens for the oauth_token session cookie in the background.
    """
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        
        # Remove navigator.webdriver flag
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        # Pre-fill email in URL if available so user doesn't even need to type it!
        login_url = "https://accounts.google.com/EmbeddedSetup"
        if email:
            login_url += f"?Email={email.strip()}"

        print("🌐 গুগল সাইন-ইন পেজ লোড হচ্ছে...")
        driver.get(login_url)

        print("\n" + "=" * 60)
        print("👉 আপনার স্ক্রিনে গুগল লগইন উইন্ডোটি দেখতে পাচ্ছেন।")
        print("👉 সেখানে পাসওয়ার্ড দিয়ে লগইন করুন (ফোনে নোটিফিকেশন আসলে Yes চাপুন)।")
        print("⏳ লগইন সম্পন্ন হওয়া মাত্রই সিস্টেম স্বয়ংক্রিয়ভাবে টোকেন নিয়ে নেবে...")
        print("=" * 60 + "\n")

        # Poll cookies every 1.5 seconds until oauth_token is found or window closed
        start_time = time.time()
        oauth_token = None

        while time.time() - start_time < timeout_sec:
            try:
                # Check if user closed the browser window manually
                if not driver.window_handles:
                    return {"ok": False, "error": "WindowClosed", "message": "ব্রাউজার উইন্ডো বন্ধ করে দেওয়া হয়েছে।"}

                cookies = driver.get_cookies()
                for c in cookies:
                    if c.get("name") == "oauth_token":
                        oauth_token = c.get("value")
                        break

                if oauth_token:
                    break

                # Also check current URL
                current_url = driver.current_url.lower()
                if "closeoob" in current_url or "success" in current_url:
                    # Look deeper into cookies or wait 1 second
                    time.sleep(1)
                    for c in driver.get_cookies():
                        if c.get("name") == "oauth_token":
                            oauth_token = c.get("value")
                            break
                    if oauth_token:
                        break

            except Exception:
                # If window was closed during get_cookies
                return {"ok": False, "error": "WindowClosed", "message": "ব্রাউজার উইন্ডো বন্ধ করা হয়েছে।"}

            time.sleep(1.5)

        if oauth_token:
            print("🎉 অসাধারণ! গুগল সেশন টোকেন (oauth_token) সফলভাবে ক্যাপচার হয়েছে!")
            return {"ok": True, "oauth_token": oauth_token}
        else:
            return {"ok": False, "error": "Timeout", "message": "নির্ধারিত সময়ের (৩ মিনিট) মধ্যে লগইন সম্পন্ন হয়নি।"}

    except Exception as e:
        return {"ok": False, "error": str(e), "message": f"লগইন প্রক্রিয়ায় ত্রুটি: {str(e)}"}
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
