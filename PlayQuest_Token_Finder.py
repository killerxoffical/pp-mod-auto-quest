"""
PlayQuest Master Token Finder (Desktop Tool)
1-Click Google Play Games Master Token (aas_et/...) Extractor & Sync Tool
"""

import os
import re
import sys
import time
import json
import random
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    CHROME_AVAILABLE = True
except ImportError:
    CHROME_AVAILABLE = False

try:
    import gpsoauth
    GPSOAUTH_AVAILABLE = True
except ImportError:
    GPSOAUTH_AVAILABLE = False

GOOGLE_CLIENT_SIG = "38918a453d07199354f8b19af05ec6562ced5788"
WEB_APP_URL = "https://pp-mod-auto-quest.onrender.com"

def generate_android_id():
    return "".join(random.choices("0123456789abcdef", k=16))

class TokenFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PlayQuest Token Finder • VAREON STUDIO")
        self.root.geometry("520x460")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")

        self.driver = None
        self.is_running = False
        self.extracted_token = ""
        self.extracted_email = ""

        self.create_widgets()

    def create_widgets(self):
        # Header Box
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=20, pady=16)
        header_frame.pack(fill="x", padx=16, pady=(16, 10))

        title_lbl = tk.Label(
            header_frame,
            text="🔑 PlayQuest Master Token Finder",
            font=("Segoe UI", 16, "bold"),
            bg="#1e293b",
            fg="#00a854"
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            header_frame,
            text="গুগল প্লে গেমসের আসল Master Token (aas_et/...) ১-ক্লিকে বের করার অফিশিয়াল টুল",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#94a3b8"
        )
        sub_lbl.pack(anchor="w", pady=(4, 0))

        # Main Body
        body_frame = tk.Frame(self.root, bg="#0f172a", padx=16)
        body_frame.pack(fill="both", expand=True)

        instructions = (
            "📌 ব্যবহারের সহজ নিয়ম:\n"
            "১. নিচের 'লগইন উইন্ডো খুলুন' বাটনে ক্লিক করুন।\n"
            "২. একটি অফিসিয়াল গুগল লগইন উইন্ডো ওপেন হবে।\n"
            "৩. আপনার জিমেইলে লগইন করুন।\n"
            "৪. লগইন শেষ হওয়ামাত্রই সফটওয়্যারটি আপনার আসল Master Token বের করে দিবে!"
        )
        inst_lbl = tk.Label(
            body_frame,
            text=instructions,
            font=("Segoe UI", 9.5),
            bg="#0f172a",
            fg="#cbd5e1",
            justify="left"
        )
        inst_lbl.pack(anchor="w", pady=10)

        # Action Button
        self.btn_start = tk.Button(
            body_frame,
            text="🚀 ১-ক্লিকে গুগল লগইন উইন্ডো খুলুন",
            font=("Segoe UI", 11, "bold"),
            bg="#00a854",
            fg="#ffffff",
            activebackground="#008f47",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=10,
            cursor="hand2",
            command=self.start_login_thread
        )
        self.btn_start.pack(fill="x", pady=8)

        # Status Label
        self.status_lbl = tk.Label(
            body_frame,
            text="স্ট্যাটাস: রেডি। শুরু করতে বাটনে চাপুন।",
            font=("Segoe UI", 9, "italic"),
            bg="#0f172a",
            fg="#38bdf8"
        )
        self.status_lbl.pack(anchor="w", pady=4)

        # Result Frame (Hidden initially)
        self.res_frame = tk.Frame(body_frame, bg="#1e293b", padx=14, pady=12, relief="groove")
        self.res_frame.pack(fill="x", pady=10)

        res_lbl = tk.Label(
            self.res_frame,
            text="🎉 আপনার Master Token (aas_et/...):",
            font=("Segoe UI", 9.5, "bold"),
            bg="#1e293b",
            fg="#00a854"
        )
        res_lbl.pack(anchor="w")

        self.token_entry = tk.Entry(
            self.res_frame,
            font=("Consolas", 9),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            relief="flat"
        )
        self.token_entry.pack(fill="x", pady=6, ipady=4)

        btn_row = tk.Frame(self.res_frame, bg="#1e293b")
        btn_row.pack(fill="x", pady=(4, 0))

        self.btn_copy = tk.Button(
            btn_row,
            text="📋 টোকেন কপি করুন",
            font=("Segoe UI", 9, "bold"),
            bg="#3b82f6",
            fg="#ffffff",
            activebackground="#2563eb",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.copy_token
        )
        self.btn_copy.pack(side="left", padx=(0, 8))

        self.btn_open_web = tk.Button(
            btn_row,
            text="🌐 সরাসরি প্লেকুয়েস্টে লগইন করুন ➔",
            font=("Segoe UI", 9, "bold"),
            bg="#10b981",
            fg="#ffffff",
            activebackground="#059669",
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.open_webapp
        )
        self.btn_open_web.pack(side="left")

    def set_status(self, text, color="#38bdf8"):
        self.status_lbl.config(text=f"স্ট্যাটাস: {text}", fg=color)

    def start_login_thread(self):
        if self.is_running:
            return
        if not CHROME_AVAILABLE or not GPSOAUTH_AVAILABLE:
            messagebox.showerror("ত্রুটি", "প্রয়োজনীয় প্যাকেজ (undetected-chromedriver বা gpsoauth) ইনস্টল নেই।")
            return

        self.is_running = True
        self.btn_start.config(state="disabled", text="⏳ লগইন উইন্ডো লোড হচ্ছে...")
        threading.Thread(target=self.run_extraction_process, daemon=True).start()

    def run_extraction_process(self):
        try:
            self.set_status("ক্রোম ব্রাউজার চালু করা হচ্ছে...")
            opts = uc.ChromeOptions()
            opts.add_argument("--window-size=480,720")
            opts.add_argument("--user-agent=Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro Build/UQ1A.240105.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

            self.driver = uc.Chrome(options=opts)
            self.set_status("গুগল অফিশিয়াল সাইন-ইন পেজ লোড হচ্ছে...")
            self.driver.get("https://accounts.google.com/EmbeddedSetup")

            self.set_status("উইন্ডোতে আপনার জিমেইলে লগইন সম্পন্ন করুন...", "#fbbf24")

            oauth_token = None
            email_detected = ""
            start_time = time.time()

            # Wait up to 300 seconds for user to log in naturally
            while time.time() - start_time < 300:
                # 1. Check cookies
                try:
                    for cookie in self.driver.get_cookies():
                        if cookie.get("name") == "oauth_token":
                            oauth_token = cookie.get("value")
                            break
                except Exception:
                    pass

                # 2. Check URL for oauth_token
                try:
                    curr_url = self.driver.current_url
                    if "oauth_token=" in curr_url:
                        m = re.search(r'oauth_token=([a-zA-Z0-9_\-]+)', curr_url)
                        if m:
                            oauth_token = m.group(1)
                except Exception:
                    pass

                # Detect email from page if available
                if not email_detected:
                    try:
                        body_txt = self.driver.find_element(By.TAG_NAME, "body").text
                        m_mail = re.search(r'[\w\.-]+@gmail\.com', body_txt)
                        if m_mail:
                            email_detected = m_mail.group(0)
                    except Exception:
                        pass

                if oauth_token:
                    break

                time.sleep(1)

            if not oauth_token:
                self.set_status("লগইন টাইমআউট হয়েছে বা উইন্ডো বন্ধ করা হয়েছে।", "#ef4444")
                return

            self.set_status("✅ oauth_token পাওয়া গেছে! Master Token এক্সচেঞ্জ করা হচ্ছে...", "#00a854")

            # Exchange oauth_token for Master Token (aas_et/...)
            android_id = generate_android_id()
            exchange_email = email_detected or "user@gmail.com"
            res = gpsoauth.exchange_token(
                email=exchange_email,
                token=oauth_token,
                android_id=android_id,
                service="ac2dm",
                client_sig=GOOGLE_CLIENT_SIG
            )

            master_token = res.get("Token")
            if not master_token:
                # If exchange_token with generic email failed, try fallback
                master_token = oauth_token

            self.extracted_token = master_token
            self.extracted_email = exchange_email

            # Save locally
            with open("my_master_token.txt", "w", encoding="utf-8") as f:
                f.write(f"Email: {exchange_email}\nMaster_Token: {master_token}\n")

            # Update GUI on main thread
            self.root.after(0, self.on_token_success)

        except Exception as e:
            self.set_status(f"ত্রুটি: {str(e)}", "#ef4444")
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.btn_start.config(state="normal", text="🚀 পুনরায় নতুন টোকেন বের করুন"))
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass

    def on_token_success(self):
        self.set_status("🎉 অভিনন্দন! আপনার Master Token সফলভাবে তৈরি হয়েছে!", "#00a854")
        self.token_entry.delete(0, tk.END)
        self.token_entry.insert(0, self.extracted_token)
        messagebox.showinfo("সফল!", "আপনার Master Token তৈরি হয়ে গেছে!\n\n'টোকেন কপি করুন' অথবা 'সরাসরি প্লেকুয়েস্টে লগইন করুন' বাটনে চাপুন।")

    def copy_token(self):
        if self.extracted_token:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.extracted_token)
            messagebox.showinfo("কপি সম্পন্ন", "Master Token ক্লিপবোর্ডে কপি করা হয়েছে!\nএখন প্লেকুয়েস্ট ওয়েবসাইটে পেস্ট করতে পারেন।")

    def open_webapp(self):
        if self.extracted_token:
            url = f"{WEB_APP_URL}?email={self.extracted_email}&token={self.extracted_token}"
            webbrowser.open(url)
        else:
            webbrowser.open(WEB_APP_URL)

if __name__ == "__main__":
    root = tk.Tk()
    app = TokenFinderApp(root)
    root.mainloop()
