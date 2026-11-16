# 🎮 PlayQuest Unlocker • Web Engine (Render.com)
**VAREON Studio • 100% Free Self-Hosted Google Play Games Quest & Achievement Engine**

---

## 🌟 প্রধান বৈশিষ্ট্যসমূহ (Key Features)

1. **🌐 সম্পূর্ণ ওয়েব ইন্টারফেস (Mobile & Desktop Responsive):**
   - ইউজার ফ্রেন্ডলি ডার্ক-মোড ইন্টারফেস।
   - গুগল প্লে গেমস লাইভ প্রোফাইল: রিয়েল **Gamer Tag**, **Avatar**, **Play Level (LVL 16)** এবং লাইভ **XP Progress Bar**।
2. **💾 অল-টাইম লগইন সেভ (Persistent Login & Auto-Restore):**
   - একবার লগইন করলেই ব্রাউজারের `localStorage`-এ সেশন নিরাপদভাবে সেভ থাকবে।
   - যত দিন ইউজার নিজে থেকে "সাইন আউট" বাটনে চাপ না দিচ্ছে, ততদিন সাইট রিলোড বা বন্ধ করলেও লগইন অবস্থায় থাকবে।
   - **মাল্টি-অ্যাকাউন্ট সুইচার:** একের অধিক গুগল অ্যাকাউন্ট সেভ রেখে এক ক্লিকে অ্যাকাউন্ট পরিবর্তন করার সুবিধা।
3. **🎯 ১-ক্লিকে ৮টি রিয়েল গেমের এচিভমেন্ট ও কোয়েস্ট আনলক:**
   - 🏃 **Subway Surfers** (১১৯টি এচিভমেন্ট)
   - 🌾 **Hay Day** (১০৮টি এচিভমেন্ট)
   - ☕ **Gossip Harbor** (১৬টি এচিভমেন্ট)
   - 🔫 **Call of Duty: Mobile** (২৬টি এচিভমেন্ট)
   - 🔥 **Free Fire MAX** (১৬টি এচিভমেন্ট)
   - 🚗 **Hill Climb Racing** (৯৭টি এচিভমেন্ট)
   - 🗿 **Temple Run 2** (১০৭টি এচিভমেন্ট)
   - 🐦 **Angry Birds 2** (৪৯টি এচিভমেন্ট)
4. **🚀 Render.com-এ হোস্টিংয়ের জন্য প্রস্তুত:**
   - `ppmod-quest-unlock.onrender.com` লিংকের জন্য সরাসরি অপটিমাইজ করা।
   - `Procfile`, `render.yaml`, `requirements.txt` কনফিগার করা।

---

## 💻 লোকাল মেশিনে টেস্ট করার নিয়ম

```powershell
cd achievement_unlocker
python app.py
```
এরপর ব্রাউজারে প্রবেশ করুন: `http://localhost:5000`

---

## 🚀 GitHub-এ পুশ ও Render.com-এ ডেপ্লয় করার নির্দেশিকা

### ১. GitHub রিপোজিটরিতে পুশ করুন:
GitHub-এ একটি নতুন রিপোজিটরি তৈরি করুন (যেমন: `ppmod-quest-unlock`), তারপর আপনার টার্মিনালে নিচের ৩টি কমান্ড দিন:

```bash
cd achievement_unlocker
git remote add origin https://github.com/<your-username>/ppmod-quest-unlock.git
git branch -M main
git push -u origin main
```

### ২. Render.com-এ সেটআপ করুন:
1. **[dashboard.render.com](https://dashboard.render.com)**-এ লগইন করুন।
2. **New +** ➔ **Web Service** সিলেক্ট করুন।
3. আপনার GitHub রিপোজিটরি (`ppmod-quest-unlock`) সিলেক্ট করুন।
4. কনফিগারেশন সেট করুন:
   - **Name:** `ppmod-quest-unlock` (Render এর ডিফল্ট ডোমেইন হবে `ppmod-quest-unlock.onrender.com`)
   - **Environment:** `Python 3`
   - **Region:** `Singapore` (or closest)
   - **Branch:** `main`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. **Create Web Service** বাটনে ক্লিক করুন।
6. ২-৩ মিনিটের মধ্যে আপনার সাইট লাইভ হয়ে যাবে:  
   👉 **`https://ppmod-quest-unlock.onrender.com`**
