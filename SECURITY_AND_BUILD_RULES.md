# PP QUEST & PP MOD — Security & Build Safety Rules

Before editing or building **`PP_Quest.apk` (`com.ppm.quest`)**, you **MUST** read and strictly follow:
- `app/pp_quest/SECURITY_AND_BUILD_RULES.md`

### Quick Mandatory Rules:
1. Edit PP QUEST UI & web assets ONLY inside `app/pp_quest/src_web/` (NEVER put plaintext HTML/JS/PNG/SVG in `assets/www/`).
2. Build `PP_Quest.apk` EXCLUSIVELY via:
   ```powershell
   python "app\pp_quest\build_quest_apk.py"
   ```
3. NEVER weaken or remove any of the **8-Layer Fortress Protections**:
   - Multi-Asset AES-256-CBC + HMAC-SHA256 Encrypted Vault (`assets/v.dat`)
   - Full Java String Literal Encryption (0 readable URLs/APIs in `classes.dex`)
   - R8 Aggressive Code Shrinking & Class/Method Obfuscation (`p.A`, `p.B`, ...)
   - AAPT2 Resource Confusion (`--shorten-resource-paths --collapse-resource-names`) & max 2 mandatory launcher PNGs in `res/`
   - Dual PackageManager + Raw `JarFile` Anti-Signature-Kill verification
   - Triple-Bound Vault Key (`Cert SHA-256 + AndroidManifest.xml SHA-256 + resources.arsc SHA-256`)
   - Strict `android.app.Application` class lock
   - Fail-Closed Anti-Proxy / Anti-Hook / Anti-Clone + Automated Penetration Audit
4. Keep `PP_Quest.apk` signed with `app/pp_quest/release.keystore` (`alias=ppserver`) so existing users get seamless OTA updates.
