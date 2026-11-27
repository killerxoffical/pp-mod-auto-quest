import os
import re
import sys
import shutil
import struct
import secrets
import zipfile
import hashlib
import subprocess

# ==============================================================================
# PP QUEST (com.ppm.quest) - 5-LAYER FORTRESS STANDALONE APK BUILDER
# ==============================================================================
# Layer 1: Full Multi-Asset AES-256-CBC + HMAC-SHA256 Encrypted Vault (assets/v.dat)
#          -> ZERO plaintext HTML, JS, JSON, SVG, or PNG files in assets/!
# Layer 2: Automated Java String Literal Encryption across ALL .java files
#          -> ZERO readable URLs, /api/ paths, Firebase keys, or anti-crack strings in classes.dex!
# Layer 3: Full R8 Code Shrinking & Aggressive Obfuscation (com.android.tools.r8.R8)
#          -> Repackages & renames SecurityGuard, CloudSyncClient, AccountStorage, etc. into p.a, p.b, p.c...
# Layer 4: Google AAPT2 Resource Confusion (--shorten-resource-paths --collapse-resource-names)
#          -> Shortens res/ paths (res/A.png, res/B.xml) & collapses resource names in resources.arsc!
# Layer 5: Dual-Layer Anti-Signature-Kill (PackageManager + Raw JarFile META-INF) + Cert-Bound Vault Key
# ==============================================================================

QUEST_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(QUEST_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)

ANDROID_SDK = r"C:\Users\Rubel\AppData\Local\Android\Sdk"
BUILD_TOOLS = os.path.join(ANDROID_SDK, "build-tools", "34.0.0")
ANDROID_JAR = os.path.join(ANDROID_SDK, "platforms", "android-34", "android.jar")
AAPT2 = os.path.join(BUILD_TOOLS, "aapt2.exe")
D8_JAR = os.path.join(BUILD_TOOLS, "lib", "d8.jar")
APKSIGNER_JAR = os.path.join(BUILD_TOOLS, "lib", "apksigner.jar")
ZIPALIGN = os.path.join(BUILD_TOOLS, "zipalign.exe")

# Prefer modern JDK (17/21/25) required by R8 8.2+
def find_modern_java():
    candidates = [
        r"C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin\java.exe",
    ]
    javac_path = shutil.which("javac")
    if javac_path:
        sibling = os.path.join(os.path.dirname(os.path.abspath(javac_path)), "java.exe")
        if os.path.exists(sibling):
            candidates.insert(0, sibling)
    for c in candidates:
        if os.path.exists(c):
            return c
    return "java"

JAVA_BIN = find_modern_java()
JAVAC_BIN = shutil.which("javac") or os.path.join(os.path.dirname(JAVA_BIN), "javac.exe")

KEYSTORE_PATH = os.path.join(QUEST_DIR, "release.keystore")
KEY_ALIAS = "ppserver"
KEY_PASS = "ppserver123"

PACKAGE_NAME = "com.ppm.quest"
WORKER_BASE_URL = "https://ppmod-api.tredarskvt.workers.dev"
PPMOD_PORTAL_URL = "https://ppmod.netlify.app"
RENDER_BASE_URL = "https://pp-mod-auto-quest.onrender.com"

SRC_WEB_DIR = os.path.join(QUEST_DIR, "src_web")
SRC_JAVA_DIR = os.path.join(QUEST_DIR, "src")
RES_DIR = os.path.join(QUEST_DIR, "res")
MANIFEST_PATH = os.path.join(QUEST_DIR, "AndroidManifest.xml")
OUT_BUILD_DIR = os.path.join(QUEST_DIR, "out_classes")

# Pure Java helper for AES-256-CBC + HMAC-SHA256 multi-asset vault encryption & live APK verification
VAULT_TOOL_JAVA = r'''
import java.io.*;
import java.security.*;
import java.security.cert.Certificate;
import java.util.*;
import java.util.jar.*;
import java.util.zip.*;
import javax.crypto.*;
import javax.crypto.spec.*;

public class VaultTool {
    private static final int MAGIC = 0x50505156; // "PPQV"

    private static byte[] hexToBytes(String hex) {
        hex = hex.replace(":", "").trim();
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    private static String bytesToHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x & 0xff));
        return sb.toString();
    }

    private static byte[] readAll(InputStream is) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[32768];
        int n;
        while ((n = is.read(buf)) != -1) bos.write(buf, 0, n);
        return bos.toByteArray();
    }

    private static boolean shouldGzip(String name) {
        String l = name.toLowerCase(Locale.US);
        return l.endsWith(".html") || l.endsWith(".htm") || l.endsWith(".js")
                || l.endsWith(".css") || l.endsWith(".json") || l.endsWith(".svg")
                || l.endsWith(".xml") || l.endsWith(".txt");
    }

    private static byte[] deriveAesKey(byte[] certSha, String pkg, byte[] pepper) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        md.update(certSha);
        md.update((byte) '|');
        md.update(pkg.getBytes("UTF-8"));
        md.update((byte) '|');
        md.update(pepper);
        return md.digest();
    }

    private static byte[] deriveHmacKey(byte[] certSha, byte[] pepper) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        md.update("MAC|".getBytes("UTF-8"));
        md.update(certSha);
        md.update((byte) '|');
        md.update(pepper);
        return md.digest();
    }

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        if ("cert-sha256".equals(mode)) {
            KeyStore ks = KeyStore.getInstance("JKS");
            try (FileInputStream fis = new FileInputStream(args[1])) {
                ks.load(fis, args[3].toCharArray());
            }
            Certificate cert = ks.getCertificate(args[2]);
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            System.out.println(bytesToHex(md.digest(cert.getEncoded())));
            return;
        }

        if ("encrypt-dir".equals(mode)) {
            File srcDir = new File(args[1]);
            File outFile = new File(args[2]);
            byte[] certSha = hexToBytes(args[3]);
            String pkg = args[4];
            byte[] pepper = hexToBytes(args[5]);

            File[] files = srcDir.listFiles();
            if (files == null || files.length == 0) throw new RuntimeException("src_web is empty!");
            Arrays.sort(files, (a, b) -> a.getName().compareToIgnoreCase(b.getName()));

            List<File> regularFiles = new ArrayList<>();
            for (File f : files) {
                if (f.isFile()) regularFiles.add(f);
            }

            ByteArrayOutputStream bundleBos = new ByteArrayOutputStream();
            DataOutputStream dos = new DataOutputStream(bundleBos);
            dos.writeInt(MAGIC);
            dos.writeInt(regularFiles.size());

            long totalRaw = 0;
            for (File f : regularFiles) {
                byte[] raw;
                try (FileInputStream fis = new FileInputStream(f)) {
                    raw = readAll(fis);
                }
                totalRaw += raw.length;
                String key = f.getName().toLowerCase(Locale.US);
                byte[] keyBytes = key.getBytes("UTF-8");
                boolean gz = shouldGzip(key);
                byte[] payload = raw;
                if (gz) {
                    ByteArrayOutputStream gzBos = new ByteArrayOutputStream();
                    try (GZIPOutputStream gos = new GZIPOutputStream(gzBos)) {
                        gos.write(raw);
                    }
                    payload = gzBos.toByteArray();
                }
                dos.writeShort(keyBytes.length);
                dos.write(keyBytes);
                dos.writeByte(gz ? 1 : 0);
                dos.writeInt(payload.length);
                dos.write(payload);
            }
            dos.flush();
            byte[] plainBundle = bundleBos.toByteArray();

            byte[] iv = new byte[16];
            new SecureRandom().nextBytes(iv);

            byte[] aesKey = deriveAesKey(certSha, pkg, pepper);
            byte[] hmacKey = deriveHmacKey(certSha, pepper);

            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new IvParameterSpec(iv));
            byte[] cipherBytes = cipher.doFinal(plainBundle);

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
            mac.update(iv);
            mac.update(cipherBytes);
            byte[] tag = mac.doFinal();

            outFile.getParentFile().mkdirs();
            try (FileOutputStream fos = new FileOutputStream(outFile)) {
                fos.write(iv);
                fos.write(tag);
                fos.write(cipherBytes);
            }
            System.out.println("VAULT_OK:files=" + regularFiles.size() + ":raw=" + totalRaw + ":enc=" + (48 + cipherBytes.length));
            return;
        }

        if ("verify-apk".equals(mode)) {
            String apkPath = args[1];
            File srcDir = new File(args[2]);
            String pkg = args[3];
            byte[] pepper = hexToBytes(args[4]);

            try (JarFile jf = new JarFile(apkPath, true)) {
                JarEntry manifest = jf.getJarEntry("AndroidManifest.xml");
                if (manifest == null) throw new RuntimeException("Missing AndroidManifest.xml");
                try (InputStream is = jf.getInputStream(manifest)) { readAll(is); }
                Certificate[] certs = manifest.getCertificates();
                if (certs == null || certs.length == 0) throw new RuntimeException("No JarFile certificates!");
                byte[] liveCertSha = MessageDigest.getInstance("SHA-256").digest(certs[0].getEncoded());

                JarEntry vaultEntry = jf.getJarEntry("assets/v.dat");
                if (vaultEntry == null) throw new RuntimeException("Missing assets/v.dat!");
                byte[] blob;
                try (InputStream is = jf.getInputStream(vaultEntry)) { blob = readAll(is); }

                byte[] iv = Arrays.copyOfRange(blob, 0, 16);
                byte[] storedMac = Arrays.copyOfRange(blob, 16, 48);
                byte[] cipherBytes = Arrays.copyOfRange(blob, 48, blob.length);

                byte[] aesKey = deriveAesKey(liveCertSha, pkg, pepper);
                byte[] hmacKey = deriveHmacKey(liveCertSha, pepper);

                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
                mac.update(iv);
                mac.update(cipherBytes);
                byte[] calcMac = mac.doFinal();
                if (!Arrays.equals(storedMac, calcMac)) throw new RuntimeException("HMAC mismatch!");

                Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
                cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new IvParameterSpec(iv));
                byte[] plainBundle = cipher.doFinal(cipherBytes);

                DataInputStream dis = new DataInputStream(new ByteArrayInputStream(plainBundle));
                if (dis.readInt() != MAGIC) throw new RuntimeException("Bad vault magic!");
                int count = dis.readInt();

                Map<String, byte[]> decrypted = new HashMap<>();
                for (int i = 0; i < count; i++) {
                    int nLen = dis.readUnsignedShort();
                    byte[] nBytes = new byte[nLen];
                    dis.readFully(nBytes);
                    String name = new String(nBytes, "UTF-8");
                    byte isGz = dis.readByte();
                    int pLen = dis.readInt();
                    byte[] payload = new byte[pLen];
                    dis.readFully(payload);
                    if (isGz == 1) {
                        try (GZIPInputStream gis = new GZIPInputStream(new ByteArrayInputStream(payload))) {
                            payload = readAll(gis);
                        }
                    }
                    decrypted.put(name, payload);
                }

                // Verify EVERY single source file matches byte-for-byte
                int checked = 0;
                for (File f : srcDir.listFiles()) {
                    if (!f.isFile()) continue;
                    byte[] expected;
                    try (FileInputStream fis = new FileInputStream(f)) { expected = readAll(fis); }
                    byte[] actual = decrypted.get(f.getName().toLowerCase(Locale.US));
                    if (actual == null || !Arrays.equals(expected, actual)) {
                        throw new RuntimeException("Mismatch for " + f.getName());
                    }
                    checked++;
                }
                System.out.println("VERIFY_OK:cert=" + bytesToHex(liveCertSha).substring(0, 16) + "...:files_verified=" + checked);
            }
        }
    }
}
'''

STRING_DECODER_JAVA = r'''package com.vareon.playquest;

public final class _S {
    public static String d(byte[] b, int k) {
        byte[] o = new byte[b.length];
        for (int i = 0; i < b.length; i++) {
            o[i] = (byte) (b[i] ^ ((k + i * 37) & 0xFF));
        }
        try {
            return new String(o, "UTF-8");
        } catch (Throwable t) {
            return "";
        }
    }
}
'''


def run_cmd(cmd, cwd=None, capture=False):
    if capture:
        res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"[ERROR] Command failed ({res.returncode}): {' '.join(cmd)}")
            if res.stdout:
                print(res.stdout)
            if res.stderr:
                print(res.stderr)
            sys.exit(1)
        return res.stdout.strip()
    else:
        res = subprocess.run(cmd, cwd=cwd)
        if res.returncode != 0:
            print(f"[ERROR] Command failed ({res.returncode}): {' '.join(cmd)}")
            sys.exit(1)
        return ""


def xor_mask_bytes(raw_bytes, mask_byte):
    out = []
    for i, b in enumerate(raw_bytes):
        v = b ^ mask_byte ^ ((i * 31) & 0xFF)
        if v >= 128:
            v -= 256
        out.append(f"(byte){v}")
    return "new byte[] { " + ", ".join(out) + " }"


def decode_java_string_literal(raw_inner):
    """Decodes Java escape sequences inside a double-quoted string literal."""
    out = []
    i = 0
    n = len(raw_inner)
    while i < n:
        ch = raw_inner[i]
        if ch == '\\' and i + 1 < n:
            nxt = raw_inner[i + 1]
            if nxt == 'n':
                out.append('\n'); i += 2
            elif nxt == 'r':
                out.append('\r'); i += 2
            elif nxt == 't':
                out.append('\t'); i += 2
            elif nxt == 'b':
                out.append('\b'); i += 2
            elif nxt == 'f':
                out.append('\f'); i += 2
            elif nxt == '"':
                out.append('"'); i += 2
            elif nxt == "'":
                out.append("'"); i += 2
            elif nxt == '\\':
                out.append('\\'); i += 2
            elif nxt == 'u' and i + 5 < n:
                try:
                    out.append(chr(int(raw_inner[i + 2:i + 6], 16)))
                    i += 6
                except ValueError:
                    out.append(ch); i += 1
            elif '0' <= nxt <= '7':
                j = i + 1
                oct_digits = ''
                while j < n and len(oct_digits) < 3 and '0' <= raw_inner[j] <= '7':
                    if len(oct_digits) == 2 and oct_digits[0] > '3':
                        break
                    oct_digits += raw_inner[j]
                    j += 1
                out.append(chr(int(oct_digits, 8)))
                i = j
            else:
                out.append(nxt); i += 2
        else:
            out.append(ch); i += 1
    return ''.join(out)


def encode_string_call(decoded_str):
    data = decoded_str.encode("utf-8")
    k = secrets.randbelow(251) + 3
    arr = []
    for idx, b in enumerate(data):
        v = b ^ ((k + idx * 37) & 0xFF)
        if v >= 128:
            v -= 256
        arr.append(str(v))
    return f"_S.d(new byte[]{{{','.join(arr)}}},{k})"


def encrypt_java_file_strings(src_text):
    """
    Java-lexer-aware string literal encryptor.
    Encrypts all string literals (len >= 2) into runtime _S.d(...) calls while
    safely preserving comments, char literals, annotations, and switch case labels.
    """
    out = []
    i = 0
    n = len(src_text)
    in_annotation_parens = 0
    expect_annotation_parens = False
    last_word = ""
    encrypted_count = 0

    while i < n:
        ch = src_text[i]

        # Single-line comment
        if ch == '/' and i + 1 < n and src_text[i + 1] == '/':
            end = src_text.find('\n', i)
            if end == -1:
                out.append(src_text[i:])
                break
            out.append(src_text[i:end + 1])
            i = end + 1
            continue

        # Multi-line comment
        if ch == '/' and i + 1 < n and src_text[i + 1] == '*':
            end = src_text.find('*/', i + 2)
            if end == -1:
                out.append(src_text[i:])
                break
            out.append(src_text[i:end + 2])
            i = end + 2
            continue

        # Char literal
        if ch == "'":
            j = i + 1
            while j < n:
                if src_text[j] == '\\':
                    j += 2
                    continue
                if src_text[j] == "'":
                    j += 1
                    break
                j += 1
            out.append(src_text[i:j])
            i = j
            continue

        # Annotation start (@SuppressWarnings, @JavascriptInterface, etc.)
        if ch == '@':
            j = i + 1
            while j < n and (src_text[j].isalnum() or src_text[j] in '._'):
                j += 1
            out.append(src_text[i:j])
            i = j
            expect_annotation_parens = True
            last_word = ""
            continue

        if expect_annotation_parens:
            if ch in ' \t\r\n':
                out.append(ch); i += 1; continue
            elif ch == '(':
                in_annotation_parens = 1
                expect_annotation_parens = False
                out.append(ch); i += 1; continue
            else:
                expect_annotation_parens = False

        if in_annotation_parens > 0:
            if ch == '"':
                j = i + 1
                while j < n:
                    if src_text[j] == '\\':
                        j += 2; continue
                    if src_text[j] == '"':
                        j += 1; break
                    j += 1
                out.append(src_text[i:j])
                i = j
                continue
            if ch == '(':
                in_annotation_parens += 1
            elif ch == ')':
                in_annotation_parens -= 1
            out.append(ch); i += 1; continue

        # Track identifier keywords (e.g., 'case')
        if ch.isalpha() or ch == '_':
            j = i + 1
            while j < n and (src_text[j].isalnum() or src_text[j] == '_'):
                j += 1
            last_word = src_text[i:j]
            out.append(last_word)
            i = j
            continue

        # Double-quoted string literal
        if ch == '"':
            j = i + 1
            while j < n:
                if src_text[j] == '\\':
                    j += 2
                    continue
                if src_text[j] == '"':
                    break
                j += 1
            raw_inner = src_text[i + 1:j]
            decoded = decode_java_string_literal(raw_inner)

            # Skip empty/1-char strings or switch case labels
            if len(decoded) >= 2 and last_word != "case":
                out.append(encode_string_call(decoded))
                encrypted_count += 1
            else:
                out.append(src_text[i:j + 1])
            i = j + 1
            last_word = ""
            continue

        if not ch.isspace():
            last_word = ""
        out.append(ch)
        i += 1

    return ''.join(out), encrypted_count


def inject_security_guard_constants(sg_path, cert_sha_bytes, vault_sha_bytes, pepper_bytes):
    with open(sg_path, "r", encoding="utf-8") as f:
        src = f.read()

    mask_byte = secrets.randbelow(250) + 3
    signed_mask = mask_byte - 256 if mask_byte >= 128 else mask_byte

    replacements = {
        "XOR_MASK": f"(byte) {signed_mask}",
        "ENC_CERT_SHA256": xor_mask_bytes(cert_sha_bytes, mask_byte),
        "ENC_VAULT_SHA256": xor_mask_bytes(vault_sha_bytes, mask_byte),
        "ENC_VAULT_PEPPER": xor_mask_bytes(pepper_bytes, mask_byte),
        "ENC_EXPECTED_PKG": xor_mask_bytes(PACKAGE_NAME.encode("utf-8"), mask_byte),
        "ENC_WORKER_BASE": xor_mask_bytes(WORKER_BASE_URL.encode("utf-8"), mask_byte),
        "ENC_PPMOD_PORTAL": xor_mask_bytes(PPMOD_PORTAL_URL.encode("utf-8"), mask_byte),
        "ENC_RENDER_BASE": xor_mask_bytes(RENDER_BASE_URL.encode("utf-8"), mask_byte),
    }

    for field, val_expr in replacements.items():
        if field == "XOR_MASK":
            pattern = r"private static final byte XOR_MASK\s*=\s*[^;]+;"
            repl = f"private static final byte XOR_MASK = {val_expr};"
        else:
            pattern = rf"private static final byte\[\] {field}\s*=\s*new byte\[\]\s*\{{[^}}]+\}};"
            repl = f"private static final byte[] {field} = {val_expr};"
        new_src, cnt = re.subn(pattern, repl, src, count=1)
        if cnt != 1:
            raise RuntimeError(f"Failed to inject {field} into SecurityGuard.java")
        src = new_src

    with open(sg_path, "w", encoding="utf-8") as f:
        f.write(src)
    return mask_byte


def verify_java8_bytecode(classes_dir):
    count = 0
    for root, _, files in os.walk(classes_dir):
        for fn in files:
            if fn.endswith(".class"):
                with open(os.path.join(root, fn), "rb") as f:
                    hdr = f.read(8)
                    major = struct.unpack(">H", hdr[6:8])[0]
                    if major > 52:
                        raise RuntimeError(f"Java 8 violation: {fn} has class version {major} > 52!")
                    count += 1
    return count


def build_hardened_pp_quest():
    print("================================================================")
    print(">>> 5-LAYER FORTRESS BUILD: PP QUEST (com.ppm.quest)")
    print("================================================================")
    print(f">>> Using JDK: {JAVA_BIN}")

    if not os.path.isdir(SRC_WEB_DIR) or not os.path.exists(os.path.join(SRC_WEB_DIR, "index.html")):
        raise RuntimeError(f"Missing src_web/index.html at {SRC_WEB_DIR}")

    if os.path.exists(OUT_BUILD_DIR):
        shutil.rmtree(OUT_BUILD_DIR)
    os.makedirs(OUT_BUILD_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Compile VaultTool helper & Pack/Encrypt ALL src_web/* into assets/v.dat
    # ------------------------------------------------------------------
    tool_dir = os.path.join(OUT_BUILD_DIR, "vault_tool")
    os.makedirs(tool_dir, exist_ok=True)
    with open(os.path.join(tool_dir, "VaultTool.java"), "w", encoding="utf-8") as f:
        f.write(VAULT_TOOL_JAVA)
    run_cmd([JAVAC_BIN, "-d", tool_dir, os.path.join(tool_dir, "VaultTool.java")])

    cert_sha_hex = run_cmd(
        [JAVA_BIN, "-cp", tool_dir, "VaultTool", "cert-sha256", KEYSTORE_PATH, KEY_ALIAS, KEY_PASS],
        capture=True,
    )
    cert_sha_bytes = bytes.fromhex(cert_sha_hex)
    print(f">>> Official Cert SHA-256: {cert_sha_hex[:16]}...{cert_sha_hex[-12:]}")

    pepper_bytes = secrets.token_bytes(32)
    pepper_hex = pepper_bytes.hex()

    build_assets_dir = os.path.join(OUT_BUILD_DIR, "assets")
    os.makedirs(build_assets_dir, exist_ok=True)
    vault_out_path = os.path.join(build_assets_dir, "v.dat")

    enc_res = run_cmd(
        [JAVA_BIN, "-cp", tool_dir, "VaultTool", "encrypt-dir", SRC_WEB_DIR, vault_out_path, cert_sha_hex, PACKAGE_NAME, pepper_hex],
        capture=True,
    )
    with open(vault_out_path, "rb") as vf:
        vault_sha_bytes = hashlib.sha256(vf.read()).digest()
    print(f">>> [Layer 1] Multi-Asset AES-256 Vault: {enc_res} (SHA-256: {vault_sha_bytes.hex()[:16]}...)")

    # ------------------------------------------------------------------
    # Step 2: AAPT2 Compile + Link + Resource Confusion (--shorten-resource-paths --collapse-resource-names)
    # ------------------------------------------------------------------
    print(">>> [Layer 4] Compiling & Obfuscating Resources with AAPT2 (Resource Confusion)...")
    res_zip = os.path.join(OUT_BUILD_DIR, "res_compiled.zip")
    gen_r_dir = os.path.join(OUT_BUILD_DIR, "gen_r")
    os.makedirs(gen_r_dir, exist_ok=True)
    linked_apk = os.path.join(OUT_BUILD_DIR, "linked.apk")
    optimized_apk = os.path.join(OUT_BUILD_DIR, "optimized.apk")

    run_cmd([AAPT2, "compile", "--dir", RES_DIR, "-o", res_zip])
    run_cmd([
        AAPT2, "link",
        "--manifest", MANIFEST_PATH,
        "--custom-package", "com.vareon.playquest",
        "-I", ANDROID_JAR,
        "-A", build_assets_dir,
        "--java", gen_r_dir,
        "-o", linked_apk,
        res_zip,
    ])
    run_cmd([
        AAPT2, "optimize",
        "--shorten-resource-paths",
        "--collapse-resource-names",
        "-o", optimized_apk,
        linked_apk,
    ])

    # ------------------------------------------------------------------
    # Step 3: Stage Obfuscated Java Source Tree + Inject Secrets + Encrypt ALL String Literals
    # ------------------------------------------------------------------
    print(">>> [Layer 2] Encrypting ALL Java String Literals across source tree...")
    src_obf_dir = os.path.join(OUT_BUILD_DIR, "src_obf")
    shutil.copytree(SRC_JAVA_DIR, src_obf_dir)

    # Copy exact AAPT2-generated R.java so all integer resource IDs match optimized.apk
    gen_r_file = os.path.join(gen_r_dir, "com", "vareon", "playquest", "R.java")
    dst_r_file = os.path.join(src_obf_dir, "com", "vareon", "playquest", "R.java")
    shutil.copy2(gen_r_file, dst_r_file)

    # Inject fresh XOR-masked cert/vault/pepper/URL arrays into SecurityGuard.java copy
    sg_obf_path = os.path.join(src_obf_dir, "com", "vareon", "playquest", "SecurityGuard.java")
    mask_byte = inject_security_guard_constants(sg_obf_path, cert_sha_bytes, vault_sha_bytes, pepper_bytes)

    # Write _S runtime string decoder
    with open(os.path.join(src_obf_dir, "com", "vareon", "playquest", "_S.java"), "w", encoding="utf-8") as f:
        f.write(STRING_DECODER_JAVA)

    total_encrypted_strings = 0
    java_files = []
    for root, _, files in os.walk(src_obf_dir):
        for fn in files:
            if not fn.endswith(".java"):
                continue
            full_path = os.path.join(root, fn)
            java_files.append(full_path)
            if fn in ("R.java", "_S.java"):
                continue
            with open(full_path, "r", encoding="utf-8") as f:
                orig_code = f.read()
            obf_code, cnt = encrypt_java_file_strings(orig_code)
            total_encrypted_strings += cnt
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(obf_code)

    print(f">>> Encrypted {total_encrypted_strings} Java string literals (XOR mask=0x{mask_byte:02X})")

    # ------------------------------------------------------------------
    # Step 4: Compile Pure Java 8 Bytecode (debug info stripped via -g:none)
    # ------------------------------------------------------------------
    print(">>> Compiling pure Java 8 bytecode (-g:none)...")
    classes_dir = os.path.join(OUT_BUILD_DIR, "classes")
    os.makedirs(classes_dir, exist_ok=True)
    run_cmd([
        JAVAC_BIN, "-g:none", "-source", "8", "-target", "8",
        "-encoding", "UTF-8", "-Xlint:-options",
        "-cp", ANDROID_JAR, "-d", classes_dir,
    ] + java_files)

    class_count = verify_java8_bytecode(classes_dir)
    print(f">>> VERIFIED: All {class_count} .class files are pure Java 8 (v52)!")

    # ------------------------------------------------------------------
    # Step 5: Full R8 Code Shrinking & Aggressive Obfuscation (com.android.tools.r8.R8)
    # ------------------------------------------------------------------
    print(">>> [Layer 3] Running R8 Full Code Shrinking & Aggressive Class/Method Obfuscation...")
    pg_rules_path = os.path.join(OUT_BUILD_DIR, "proguard-rules.pro")
    pg_rules = """
-allowaccessmodification
-overloadaggressively
-repackageclasses 'p'
-renamesourcefileattribute 'SourceFile'
-keepattributes *Annotation*

-keep public class com.vareon.playquest.MainActivity {
    public <init>();
}
-keep public class com.vareon.playquest.GenericFileProvider {
    public <init>();
}
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepclassmembers class com.vareon.playquest.R$* {
    public static <fields>;
}
-dontwarn android.**
-dontwarn java.**
-dontwarn javax.**
-dontwarn org.json.**
"""
    with open(pg_rules_path, "w", encoding="utf-8") as f:
        f.write(pg_rules.strip() + "\n")

    dex_out_dir = os.path.join(OUT_BUILD_DIR, "dex_out")
    os.makedirs(dex_out_dir, exist_ok=True)
    class_files = []
    for root, _, files in os.walk(classes_dir):
        for fn in files:
            if fn.endswith(".class"):
                class_files.append(os.path.join(root, fn))

    run_cmd([
        JAVA_BIN, "-cp", D8_JAR, "com.android.tools.r8.R8",
        "--release",
        "--min-api", "21",
        "--lib", ANDROID_JAR,
        "--pg-conf", pg_rules_path,
        "--output", dex_out_dir,
    ] + class_files)

    dex_file = os.path.join(dex_out_dir, "classes.dex")
    if not os.path.exists(dex_file):
        raise RuntimeError("R8 did not produce classes.dex!")
    print(f">>> R8 Obfuscated classes.dex: {os.path.getsize(dex_file)} bytes")

    # ------------------------------------------------------------------
    # Step 6: Package classes.dex into Resource-Confused APK, Zipalign & Sign (v1+v2+v3)
    # ------------------------------------------------------------------
    print(">>> Packaging, zipaligning, and signing hardened PP_Quest.apk...")
    unaligned_apk = os.path.join(OUT_BUILD_DIR, "unaligned.apk")
    shutil.copy2(optimized_apk, unaligned_apk)
    with zipfile.ZipFile(unaligned_apk, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(dex_file, "classes.dex")

    aligned_apk = os.path.join(OUT_BUILD_DIR, "aligned.apk")
    run_cmd([ZIPALIGN, "-f", "-p", "4", unaligned_apk, aligned_apk])

    final_apk = os.path.join(QUEST_DIR, "PP_Quest.apk")
    run_cmd([
        JAVA_BIN, "-jar", APKSIGNER_JAR, "sign",
        "--ks", KEYSTORE_PATH,
        "--ks-key-alias", KEY_ALIAS,
        "--ks-pass", f"pass:{KEY_PASS}",
        "--key-pass", f"pass:{KEY_PASS}",
        "--v1-signing-enabled", "true",
        "--v2-signing-enabled", "true",
        "--v3-signing-enabled", "true",
        "--out", final_apk,
        aligned_apk,
    ])
    run_cmd([JAVA_BIN, "-jar", APKSIGNER_JAR, "verify", "--verbose", final_apk], capture=True)

    # ------------------------------------------------------------------
    # Step 7: Live JarFile Cert + Multi-Asset Vault Decryption Self-Test & Penetration Audit
    # ------------------------------------------------------------------
    print(">>> [Layer 5] Running live JarFile cert + 16-file AES-256 vault decryption self-test...")
    verify_res = run_cmd(
        [JAVA_BIN, "-cp", tool_dir, "VaultTool", "verify-apk", final_apk, SRC_WEB_DIR, PACKAGE_NAME, pepper_hex],
        capture=True,
    )
    print(f">>> {verify_res}")

    # Automated Penetration Audit on final PP_Quest.apk
    with zipfile.ZipFile(final_apk, "r") as zf:
        names = zf.namelist()
        asset_entries = [n for n in names if n.startswith("assets/")]
        res_entries = [n for n in names if n.startswith("res/")]
        dex_bytes = zf.read("classes.dex")

        if asset_entries != ["assets/v.dat"]:
            raise RuntimeError(f"Asset leak detected! Expected only ['assets/v.dat'], got: {asset_entries}")

        forbidden_dex_tokens = [
            b"tredarskvt.workers.dev",
            b"pp-mod-auto-quest.onrender.com",
            b"ppmod.netlify.app",
            b"accounts.google.com/EmbeddedSetup",
            b"identitytoolkit.googleapis.com",
            b"android.clients.google.com",
            b"games.googleapis.com",
            b"/api/user/find",
            b"/api/login/ppmod",
            b"/api/sync/save",
            b"SecurityGuard;",
            b"CloudSyncClient;",
            b"AccountStorage;",
            b"ApkDownloadTask;",
            b"GServicesBridge;",
            b"SignatureKiller",
            b"KillerApplication",
            b"44dae5f1",
            b"44:DA:E5:F1",
        ]
        found_leaks = [tok.decode() for tok in forbidden_dex_tokens if tok in dex_bytes]
        if found_leaks:
            raise RuntimeError(f"DEX leak detected: {found_leaks}")

        print(f">>> PENETRATION AUDIT PASSED:")
        print(f"    - assets/ entries : {asset_entries} (0 HTML, 0 PNG, 0 JS, 0 SVG, 0 JSON!)")
        print(f"    - res/ entries    : {len(res_entries)} shortened/confused paths (sample: {res_entries[:5]})")
        print(f"    - classes.dex     : 0 leaked URLs, 0 /api/ paths, 0 internal class names, 0 anti-crack strings!")

    # ------------------------------------------------------------------
    # Step 8: Distribute hardened PP_Quest.apk to all repo targets
    # ------------------------------------------------------------------
    targets = [
        os.path.join(ROOT_DIR, "PP_Quest.apk"),
        os.path.join(APP_DIR, "PP_Quest.apk"),
        os.path.join(APP_DIR, "pp_server", "PP_Quest.apk"),
        os.path.join(ROOT_DIR, "static", "PP_Quest.apk"),
        os.path.join(ROOT_DIR, "achievement_unlocker", "PP_Quest.apk"),
        os.path.join(ROOT_DIR, "achievement_unlocker", "static", "PP_Quest.apk"),
    ]
    print("\n>>> Distributing 5-Layer Fortress PP_Quest.apk...")
    for t in targets:
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copy2(final_apk, t)
        print(f"  -> {t}")

    # Clean up temp build folder
    shutil.rmtree(OUT_BUILD_DIR, ignore_errors=True)

    print("\n================================================================")
    print(f">>> 5-LAYER FORTRESS PP_Quest.apk COMPLETE ({os.path.getsize(final_apk)} bytes)")
    print("================================================================")


if __name__ == "__main__":
    build_hardened_pp_quest()
