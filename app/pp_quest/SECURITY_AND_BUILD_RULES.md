# PP QUEST (`com.ppm.quest`) — MANDATORY SECURITY & BUILD RULES

> **CRITICAL NOTICE FOR ALL FUTURE AI ASSISTANTS & DEVELOPERS:**
> You **MUST** read and obey EVERY rule in this document before editing or building `PP_Quest.apk`.
> Never weaken, bypass, or strip ANY of the 8 security layers below!

---

## 1. Project Separation & Source Locations
- **PP QUEST standalone project folder:** `app/pp_quest/` (`package="com.ppm.quest"`)
  - Editable Mobile Web UI & ALL static web assets (HTML, JS, PNG, SVG, Lottie JSON): **`app/pp_quest/src_web/`**
  - Editable Java source code: **`app/pp_quest/src/com/vareon/playquest/`**
  - Android Manifest: **`app/pp_quest/AndroidManifest.xml`**
  - Minimal Android OS resources (ONLY 2 mandatory launcher icons + 1 layout): **`app/pp_quest/res/`**
  - Official Release Keystore (NEVER change keystore, otherwise OTA updates break!): **`app/pp_quest/release.keystore`** (`alias=ppserver`)
- **PPM Cloud Server (`PPM_Cloud.apk`)** lives separately in `app/pp_server/`.
- **Web App (`ppmod.netlify.app`)** lives separately in `pp mod/index.html`.
- **NEVER** overwrite `app/pp_quest/src_web/index.html` with `pp mod/index.html` (Mobile App UI and Web UI are strictly separate!).

---

## 2. How to Build `PP_Quest.apk` (ONLY Allowed Command)
ALWAYS build `PP_Quest.apk` exclusively using:
```powershell
python "app\pp_quest\build_quest_apk.py"
```
- **NEVER** build `PP_Quest.apk` with plain `d8`, `dx`, or legacy `aapt`!
- **NEVER** place plaintext `index.html`, `.js`, `.json`, `.svg`, or `.png` files into `app/pp_quest/assets/www/`! Put all UI files in `app/pp_quest/src_web/` so `build_quest_apk.py` encrypts them into `assets/v.dat`.
- **NEVER** add extra unused PNGs into `app/pp_quest/res/drawable/`! Only the 2 mandatory Android OS launcher icons (`ic_launcher_quest.png`, `ic_launcher_quest_round.png`) are allowed in `res/drawable/`.

---

## 3. Mandatory 8-Layer Fortress Protection (DO NOT REMOVE OR WEAKEN)
Every release of `PP_Quest.apk` MUST keep ALL 8 layers active and verified:

1. **Layer 1 — Multi-Asset AES-256-CBC + HMAC-SHA256 Encrypted Vault (`assets/v.dat`):**
   - ALL files in `app/pp_quest/src_web/` (`index.html`, `progress.js`, `splash_quest_lottie.json`, all `.png`/`.svg`) are packed and encrypted into a single binary `assets/v.dat`, decrypted strictly in RAM by `SecurityGuard.getVaultAsset()` and served by `MainActivity.SafeMainWebClient` + `loadEncryptedVaultUi()`.
   - Final APK `assets/` MUST contain **ONLY** `assets/v.dat` (0 `.html`, 0 `.png`, 0 `.js`, 0 `.svg`, 0 `.json`).
2. **Layer 2 — Build-Time Full Java String Literal Encryption:**
   - `build_quest_apk.py` encrypts all Java string literals (`len >= 2`) in a temporary build copy (`out_classes/src_obf/`) into per-string XOR+rolling byte arrays decoded at runtime by `_S.d(...)`, leaving clean readable source files untouched in `app/pp_quest/src/`.
   - Final `classes.dex` MUST contain **0** readable URLs (`workers.dev`, `onrender.com`, `netlify.app`, `accounts.google.com`, `googleapis.com`) and **0** readable `/api/...` paths.
3. **Layer 3 — Full R8 Code Shrinking & Aggressive Obfuscation (`com.android.tools.r8.R8`):**
   - Compiles with `javac -g:none -source 8 -target 8` (strict Java 8 v52 bytecode) and runs R8 with `-repackageclasses 'p'`, `-overloadaggressively`, `-allowaccessmodification`, `-renamesourcefileattribute 'SourceFile'`.
   - ONLY `MainActivity`, `GenericFileProvider`, `@JavascriptInterface` bridge methods, and `R$*` are kept; all internal classes (`SecurityGuard`, `CloudSyncClient`, `AccountStorage`, `ApkDownloadTask`, `GServicesBridge`, etc.) are renamed to `p.A`, `p.B`, `p.C`, ...
4. **Layer 4 — Google AAPT2 Resource Confusion (`aapt2 optimize`):**
   - Runs `aapt2 optimize --shorten-resource-paths --collapse-resource-names` so all `res/` paths are shortened (`res/gh.png`, `res/v9.xml`) and `resources.arsc` names are collapsed.
5. **Layer 5 — Dual-Layer Anti-Signature-Kill Verification:**
   - `SecurityGuard.verifyAppSignature()` checks BOTH `PackageManager` signing certificates AND direct raw disk `JarFile(sourceDir, true)` `META-INF` X.509 certificate SHA-256.
6. **Layer 6 — Triple-Bound Cryptographic Vault Key (Cert + Manifest + ARSC):**
   - AES-256 and HMAC-SHA256 keys for `assets/v.dat` are derived from `liveCertSha256 | liveManifestSha256 | liveArscSha256 | pkg | pepper`.
   - Editing 1 byte of `AndroidManifest.xml` (MT Manager Signature Killer / `debuggable`), `resources.arsc`, or re-signing with another keystore mathematically breaks decryption!
7. **Layer 7 — Strict `Application` Class Lock:**
   - `SecurityGuard.performSecurityCheck()` enforces `"android.app.Application".equals(appCtx.getClass().getName())` — blocking ALL injected Signature Killer Application subclasses (`KillerApplication`, `PmsHookApplication`, etc.).
8. **Layer 8 — Fail-Closed Anti-Hook / Anti-MITM Proxy / Anti-Clone + Penetration Audit:**
   - Fail-closed `performSecurityCheck()` (`catch` MUST return `false`, NEVER `true`!).
   - Blocks active HTTP proxies (`http.proxyHost`/`https.proxyHost`/global proxy), Frida, Xposed/LSPosed, SandHook, MT/NP Signature Killers, debuggers, and Dual Space/App Cloners.
   - `build_quest_apk.py` automatically runs a live `JarFile` + triple-bound decryption self-test AND penetration audit before distributing `PP_Quest.apk` — NEVER ship an APK if the audit fails!

---

## 4. Critical Runtime Behavior Rules (DO NOT BREAK)
- **App Login Google Button (`startGoogleSsoLogin`):** MUST directly invoke `AccountManager.newChooseAccountIntent(...)` WITHOUT pre-checking `getDeviceGoogleEmails().isEmpty()` (Android 8+ returns empty until after the native account picker runs). On cancel, call `notifyWebSsoCancel()` — NEVER redirect app login into One-Time Quest WebView!
- **One-Time Quest Login (`startOneTimeQuestLogin`):** Opens EmbeddedSetup WebView ONLY inside the Quest section.
- **No Internal Jargon in UI:** NEVER show words like `টোকেন`, `ক্লাউডে সেভ`, `GPGS`, or `MANUAL` in user-facing UI text in `app/pp_quest/src_web/index.html`.
- **Single-Source Balance:** Cloudflare D1 (`ppmod-api.tredarskvt.workers.dev`) is the ONLY balance authority — NEVER read/write balance from Firestore.
- **Backend Architecture:** All quest unlocking logic, game catalogs, and achievements live on GitHub (`pp-mod-auto-quest`) + Render + Cloudflare D1 — NEVER embed backend secrets or quest logic inside `PP_Quest.apk`.
