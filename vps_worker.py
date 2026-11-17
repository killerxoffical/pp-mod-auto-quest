#!/usr/bin/env python3
"""
PlayQuest VPS Background Worker for Daytona Cloud Container
Optimized for 1 vCPU / 1GB RAM Ubuntu Containers
Communicates with https://pp-mod-auto-quest.onrender.com
"""

import os
import sys
import time
import json
import re
import base64
import requests

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

SERVER_URL = os.environ.get("SERVER_URL", "https://pp-mod-auto-quest.onrender.com").rstrip("/")
POLL_INTERVAL = 3  # seconds

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def get_chrome_driver():
    """Initializes an ultra-lightweight headless Chrome instance tuned for 1GB RAM"""
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--blink-settings=imagesEnabled=true")  # Need images for captcha if shown
    options.add_argument("--window-size=412,915")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro Build/UQ1A.240105.004) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    return webdriver.Chrome(options=options)

def wait_for_element(driver, by, value, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            elem = driver.find_element(by, value)
            if elem.is_displayed():
                return elem
        except Exception:
            pass
        time.sleep(0.3)
    return None

def process_login_job(job_id, email, password):
    log(f"🚀 Starting login job {job_id} for {email}...")
    driver = None
    try:
        driver = get_chrome_driver()
        driver.get("https://accounts.google.com/EmbeddedSetup")

        # 1. Type Email
        email_elem = wait_for_element(driver, By.ID, "identifierId", timeout=12)
        if not email_elem:
            try:
                email_elem = driver.find_element(By.CSS_SELECTOR, "input[type='email']")
            except Exception:
                pass

        if not email_elem:
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "error",
                "error": "গুগল লগইন পেজ লোড হতে ব্যর্থ হয়েছে। সার্ভার আবার চেষ্টা করছে..."
            }, timeout=10)
            return

        email_elem.clear()
        email_elem.send_keys(email)
        email_elem.send_keys(Keys.ENTER)
        log("📧 Email entered, waiting for password field...")

        time.sleep(1.5)

        # Check for Email Error
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if "Couldn't find your Google Account" in page_text or "অ্যাকাউন্ট খুঁজে পাওয়া যায়নি" in page_text:
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "error",
                "error": "এই জিমেইল অ্যাকাউন্টটি গুগলে খুঁজে পাওয়া যায়নি। সঠিক ইমেইল দিন।"
            }, timeout=10)
            return

        # Check for Captcha after email
        try:
            c_img = driver.find_element(By.ID, "captchaimg")
            if c_img.is_displayed():
                img_b64 = c_img.screenshot_as_base64
                log("🧩 Captcha detected after email, requesting user input...")
                requests.post(f"{SERVER_URL}/api/worker/update", json={
                    "job_id": job_id,
                    "status": "captcha_required",
                    "captcha_img": img_b64
                }, timeout=10)

                # Poll for solution up to 60s
                c_start = time.time()
                solved = False
                while time.time() - c_start < 60:
                    sol_res = requests.get(f"{SERVER_URL}/api/worker/captcha/{job_id}", timeout=5).json()
                    sol = sol_res.get("solution")
                    if sol:
                        cap_in = driver.find_element(By.ID, "ca") or driver.find_element(By.NAME, "ca")
                        cap_in.send_keys(sol)
                        cap_in.send_keys(Keys.ENTER)
                        solved = True
                        time.sleep(2)
                        break
                    time.sleep(2)
                if not solved:
                    requests.post(f"{SERVER_URL}/api/worker/update", json={
                        "job_id": job_id,
                        "status": "error",
                        "error": "ক্যাপচা সমাধান করার সময়সীমা শেষ হয়েছে।"
                    }, timeout=10)
                    return
        except Exception:
            pass

        # 2. Type Password
        pwd_elem = wait_for_element(driver, By.NAME, "Passwd", timeout=10)
        if not pwd_elem:
            try:
                pwd_elem = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            except Exception:
                pass

        if not pwd_elem:
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "error",
                "error": "পাসওয়ার্ড ফিল্ড পাওয়া যায়নি। দয়া করে ইমেইল সঠিক কিনা চেক করুন।"
            }, timeout=10)
            return

        pwd_elem.clear()
        pwd_elem.send_keys(password)
        pwd_elem.send_keys(Keys.ENTER)
        log("🔑 Password entered, checking 2FA / prompt response...")

        time.sleep(1.5)

        # Check for Wrong Password
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if "Wrong password" in page_text or "ভুল পাসওয়ার্ড" in page_text:
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "error",
                "error": "ভুল পাসওয়ার্ড দেওয়া হয়েছে। দয়া করে সঠিক পাসওয়ার্ড দিন।"
            }, timeout=10)
            return

        # 3. Detect 2FA Prompt Number & Phone Device
        prompt_num = None
        user_phone_device = "আপনার ফোনে"
        for _ in range(25):  # 25 * 0.3s = 7.5s
            body_text = driver.find_element(By.TAG_NAME, "body").text

            dev_m = re.search(r'notification to your\s+([A-Za-z0-9\s\-]+?)(?:\.|\n|\r)', body_text, re.IGNORECASE)
            if dev_m:
                user_phone_device = f"আপনার {dev_m.group(1).strip()} ফোনে"

            m = re.search(r'tap\s+(\d{1,3})\s+on\s+your\s+phone', body_text, re.IGNORECASE)
            if m:
                prompt_num = m.group(1)
                break

            samps = driver.find_elements(By.TAG_NAME, "samp")
            for s in samps:
                st = s.text.strip()
                if st.isdigit() and 1 <= len(st) <= 3:
                    prompt_num = st
                    break
            if prompt_num:
                break

            try:
                elems = driver.find_elements(By.CSS_SELECTOR, "[data-prompt-number]")
                for el in elems:
                    val = el.get_attribute("data-prompt-number")
                    if val and val.isdigit():
                        prompt_num = val
                        break
            except Exception:
                pass
            if prompt_num:
                break

            time.sleep(0.3)

        if prompt_num:
            log(f"🔔 2FA Prompt detected: [{prompt_num}] for device: {user_phone_device}")
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "prompt_required",
                "prompt_number": prompt_num,
                "device_name": user_phone_device
            }, timeout=10)
        else:
            log(f"📱 Security notification sent to device: {user_phone_device} (no number required)")
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "prompt_required",
                "prompt_number": None,
                "device_name": user_phone_device
            }, timeout=10)

        # 4. Wait for phone approval & capture oauth_token
        oauth_token = None
        approval_start = time.time()
        while time.time() - approval_start < 80:
            # Click any Google terms / agree buttons
            try:
                for b in driver.find_elements(By.TAG_NAME, "button"):
                    txt = b.text.lower()
                    if "agree" in txt or "accept" in txt or "পরবর্তী" in txt:
                        if b.is_displayed():
                            b.click()
                            time.sleep(0.5)
                            break
            except Exception:
                pass

            # Check cookies
            for c in driver.get_cookies():
                if c.get("name") == "oauth_token":
                    oauth_token = c.get("value")
                    break
            if oauth_token:
                break

            # Check URL
            curr_url = driver.current_url
            if "oauth_token=" in curr_url:
                m = re.search(r'oauth_token=([a-zA-Z0-9_\-]+)', curr_url)
                if m:
                    oauth_token = m.group(1)
                    break

            time.sleep(1.2)

        if oauth_token:
            log(f"✨ SUCCESS: Captured oauth_token for {email}!")
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "completed",
                "oauth_token": oauth_token
            }, timeout=15)
        else:
            log(f"❌ Timeout waiting for user phone approval ({email})")
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "error",
                "error": "ফোনে নির্দিষ্ট সময়ে ট্যাপ করা হয়নি (টাইমআউট)। আবার চেষ্টা করুন।"
            }, timeout=10)

    except Exception as e:
        log(f"❌ Error during job {job_id}: {e}")
        try:
            requests.post(f"{SERVER_URL}/api/worker/update", json={
                "job_id": job_id,
                "status": "error",
                "error": f"লগইন প্রক্রিয়ায় ত্রুটি: {str(e)}"
            }, timeout=10)
        except Exception:
            pass
    finally:
        if driver:
            try:
                driver.quit()
                log("🛑 Headless browser closed. Memory freed.")
            except Exception:
                pass

def main():
    log("==================================================")
    log("🔥 PlayQuest VPS Background Worker Started")
    log(f"📡 Connected to: {SERVER_URL}")
    log("==================================================")

    if not SELENIUM_AVAILABLE:
        log("❌ Error: Selenium is not installed! Run: pip install selenium")
        sys.exit(1)

    while True:
        try:
            res = requests.get(f"{SERVER_URL}/api/worker/poll", timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok") and data.get("job_id"):
                    process_login_job(data["job_id"], data["email"], data["password"])
        except Exception as e:
            # Server unreachable or sleeping
            pass
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
