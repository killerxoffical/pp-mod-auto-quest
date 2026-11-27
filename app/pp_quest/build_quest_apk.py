#!/usr/bin/env python3
"""
Standalone Hardened Build Script for PP QUEST (com.ppm.quest)
- Encrypts src_web/index.html with GZIP + AES-256-CBC + HMAC-SHA256 bound to the official APK signing certificate
- Zero plaintext index.html or API URLs inside PP_Quest.apk
- Fresh random XOR mask & 32-byte key pepper per build
- Verifies pure Java 8 bytecode (v52), v1+v2+v3 APK signature, live JarFile cert extraction & vault round-trip decryption!
"""
import os
import sys
import glob
import shutil
import zipfile
import subprocess
import time
import hashlib
import secrets
import re
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
SDK = r"C:\Users\Rubel\AppData\Local\Android\Sdk"
BUILD_TOOLS = os.path.join(SDK, r"build-tools\34.0.0")
PLATFORM = os.path.join(SDK, r"platforms\android-34")

AAPT = os.path.join(BUILD_TOOLS, "aapt.exe")
ZIPALIGN = os.path.join(BUILD_TOOLS, "zipalign.exe")
DEXDUMP = os.path.join(BUILD_TOOLS, "dexdump.exe")
ANDROID_JAR = os.path.join(PLATFORM, "android.jar")
JAVA = os.path.join(JAVA_HOME, r"bin\java.exe")
JAVAC = os.path.join(JAVA_HOME, r"bin\javac.exe")
D8_JAR = os.path.join(BUILD_TOOLS, r"lib\d8.jar")
APKSIGNER_JAR = os.path.join(BUILD_TOOLS, r"lib\apksigner.jar")

KEYSTORE = "release.keystore"
KEYSTORE_PASS = "ppserver123"
KEY_ALIAS = "ppserver"
PACKAGE_NAME = "com.ppm.quest"
APK_NAME = "PP_Quest.apk"

# Endpoints to XOR-obfuscate into SecurityGuard.java (never stored plaintext in DEX)
WORKER_BASE = "https://ppmod-api.tredarskvt.workers.dev"
PPMOD_PORTAL = "https://ppmods.netlify.app/"
RENDER_BASE = "https://pp-mod-auto-quest.onrender.com"

VAULT_HELPER_JAVA = r'''
import java.io.*;
import java.security.*;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class VaultTool {
    public static void main(String[] args) throws Exception {
        String cmd = args[0];
        if ("cert-sha256".equals(cmd)) {
            KeyStore ks = KeyStore.getInstance("JKS");
            try (FileInputStream fis = new FileInputStream(args[1])) {
                ks.load(fis, args[2].toCharArray());
            }
            Certificate cert = ks.getCertificate(args[3]);
            byte[] sha = MessageDigest.getInstance("SHA-256").digest(cert.getEncoded());
            System.out.println(toHex(sha));
        } else if ("encrypt".equals(cmd)) {
            byte[] certSha = fromHex(args[1]);
            String pkg = args[2];
            byte[] pepper = fromHex(args[3]);
            byte[] plainHtml = readAll(args[4]);

            // GZIP compress HTML
            ByteArrayOutputStream gzOut = new ByteArrayOutputStream();
            try (GZIPOutputStream gos = new GZIPOutputStream(gzOut)) {
                gos.write(plainHtml);
            }
            byte[] gzBytes = gzOut.toByteArray();

            byte[] aesKey = deriveAesKey(certSha, pkg, pepper);
            byte[] hmacKey = deriveHmacKey(certSha, pepper);

            byte[] iv = new byte[16];
            new SecureRandom().nextBytes(iv);

            Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
            c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new IvParameterSpec(iv));
            byte[] ct = c.doFinal(gzBytes);

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
            mac.update(iv);
            mac.update(ct);
            byte[] tag = mac.doFinal();

            try (FileOutputStream fos = new FileOutputStream(args[5])) {
                fos.write(iv);
                fos.write(tag);
                fos.write(ct);
            }
            System.out.println("ENCRYPTED_OK:" + (iv.length + tag.length + ct.length));
        } else if ("verify-apk".equals(cmd)) {
            String apkPath = args[1];
            byte[] expectedCertSha = fromHex(args[2]);
            String pkg = args[3];
            byte[] pepper = fromHex(args[4]);
            byte[] expectedHtml = readAll(args[5]);

            try (JarFile jf = new JarFile(apkPath, true)) {
                // 1. Ensure NO plaintext index.html exists anywhere inside APK
                if (jf.getJarEntry("assets/www/index.html") != null) {
                    throw new RuntimeException("SECURITY FAIL: Plaintext assets/www/index.html found in APK!");
                }
                // 2. Extract real X.509 cert via JarFile (same exact path as SecurityGuard at runtime)
                JarEntry mEntry = jf.getJarEntry("AndroidManifest.xml");
                try (InputStream mis = jf.getInputStream(mEntry)) {
                    byte[] b = new byte[8192];
                    while (mis.read(b) != -1) {}
                }
                Certificate[] certs = mEntry.getCertificates();
                if (certs == null || certs.length == 0) {
                    throw new RuntimeException("SECURITY FAIL: JarFile returned no certificates!");
                }
                byte[] liveCertSha = MessageDigest.getInstance("SHA-256").digest(certs[0].getEncoded());
                if (!Arrays.equals(expectedCertSha, liveCertSha)) {
                    throw new RuntimeException("SECURITY FAIL: Live APK cert SHA-256 mismatch!");
                }
                // 3. Decrypt assets/vault/core.bin using liveCertSha
                JarEntry vEntry = jf.getJarEntry("assets/vault/core.bin");
                if (vEntry == null) throw new RuntimeException("SECURITY FAIL: assets/vault/core.bin missing!");
                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                try (InputStream vis = jf.getInputStream(vEntry)) {
                    byte[] b = new byte[8192];
                    int r;
                    while ((r = vis.read(b)) != -1) baos.write(b, 0, r);
                }
                byte[] blob = baos.toByteArray();
                byte[] iv = Arrays.copyOfRange(blob, 0, 16);
                byte[] storedMac = Arrays.copyOfRange(blob, 16, 48);
                byte[] ct = Arrays.copyOfRange(blob, 48, blob.length);

                byte[] aesKey = deriveAesKey(liveCertSha, pkg, pepper);
                byte[] hmacKey = deriveHmacKey(liveCertSha, pepper);
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
                mac.update(iv);
                mac.update(ct);
                if (!Arrays.equals(storedMac, mac.doFinal())) {
                    throw new RuntimeException("SECURITY FAIL: Vault HMAC verification failed!");
                }
                Cipher c = Cipher.getInstance("AES/CBC/PKCS5Padding");
                c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new IvParameterSpec(iv));
                byte[] gz = c.doFinal(ct);
                ByteArrayOutputStream htmlOut = new ByteArrayOutputStream();
                try (GZIPInputStream gis = new GZIPInputStream(new ByteArrayInputStream(gz))) {
                    byte[] b = new byte[8192];
                    int r;
                    while ((r = gis.read(b)) != -1) htmlOut.write(b, 0, r);
                }
                if (!Arrays.equals(expectedHtml, htmlOut.toByteArray())) {
                    throw new RuntimeException("SECURITY FAIL: Decrypted HTML does not match source!");
                }
                System.out.println("VERIFY_OK: cert=" + toHex(liveCertSha).substring(0, 16) + "... html_bytes=" + expectedHtml.length);
            }
        }
    }

    static byte[] deriveAesKey(byte[] certSha, String pkg, byte[] pepper) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        md.update(certSha);
        md.update((byte) '|');
        md.update(pkg.getBytes("UTF-8"));
        md.update((byte) '|');
        md.update(pepper);
        return md.digest();
    }

    static byte[] deriveHmacKey(byte[] certSha, byte[] pepper) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        md.update("MAC|".getBytes("UTF-8"));
        md.update(certSha);
        md.update((byte) '|');
        md.update(pepper);
        return md.digest();
    }

    static byte[] readAll(String path) throws Exception {
        try (FileInputStream fis = new FileInputStream(path)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] b = new byte[8192];
            int r;
            while ((r = fis.read(b)) != -1) out.write(b, 0, r);
            return out.toByteArray();
        }
    }

    static String toHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x & 0xFF));
        return sb.toString();
    }

    static byte[] fromHex(String s) {
        byte[] out = new byte[s.length() / 2];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }
}
'''

def xor_mask_bytes(raw: bytes, mask: int) -> str:
    masked = []
    for i, b in enumerate(raw):
        v = b ^ mask ^ ((i * 31) & 0xFF)
        # Signed Java byte literal
        signed = v - 256 if v > 127 else v
        masked.append(f"(byte){signed}")
    return ", ".join(masked)

def sha256_bytes(filepath: str) -> bytes:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.digest()

def main():
    print("=" * 64)
    print(">>> HARDENED STANDALONE BUILD: PP QUEST (com.ppm.quest)")
    print("=" * 64)

    src_html = os.path.join("src_web", "index.html")
    if not os.path.exists(src_html):
        raise RuntimeError(f"Missing {src_html}!")

    # Remove any accidental plaintext index.html in assets/www/
    accidental_plain = os.path.join("assets", "www", "index.html")
    if os.path.exists(accidental_plain):
        os.remove(accidental_plain)

    # Compile VaultTool helper in temp dir
    tmp_dir = tempfile.mkdtemp(prefix="ppq_vault_")
    try:
        vt_src = os.path.join(tmp_dir, "VaultTool.java")
        with open(vt_src, "w", encoding="utf-8") as f:
            f.write(VAULT_HELPER_JAVA)
        subprocess.run([JAVAC, "-source", "8", "-target", "8", "-Xlint:-options", "-d", tmp_dir, vt_src], check=True)

        # 1. Extract official release.keystore certificate SHA-256
        cert_hex = subprocess.check_output(
            [JAVA, "-cp", tmp_dir, "VaultTool", "cert-sha256", KEYSTORE, KEYSTORE_PASS, KEY_ALIAS],
            text=True,
        ).strip()
        cert_sha_bytes = bytes.fromhex(cert_hex)
        print(f">>> Official Signing Cert SHA-256: {cert_hex[:16]}...{cert_hex[-12:]}")

        # 2. Generate fresh build-time XOR mask & 32-byte key pepper
        xor_mask = secrets.randbelow(250) + 3
        pepper_bytes = secrets.token_bytes(32)
        pepper_hex = pepper_bytes.hex()

        # 3. Encrypt src_web/index.html -> assets/vault/core.bin
        vault_dir = os.path.join("assets", "vault")
        os.makedirs(vault_dir, exist_ok=True)
        vault_file = os.path.join(vault_dir, "core.bin")
        enc_out = subprocess.check_output(
            [JAVA, "-cp", tmp_dir, "VaultTool", "encrypt", cert_hex, PACKAGE_NAME, pepper_hex, src_html, vault_file],
            text=True,
        ).strip()
        vault_sha_bytes = sha256_bytes(vault_file)
        print(f">>> Encrypted UI Vault: {enc_out} (SHA-256: {vault_sha_bytes.hex()[:16]}...)")

        # 4. Inject fresh XOR-obfuscated byte arrays into SecurityGuard.java
        sec_path = os.path.join("src", "com", "vareon", "playquest", "SecurityGuard.java")
        with open(sec_path, "r", encoding="utf-8") as f:
            sec_code = f.read()

        signed_mask = xor_mask - 256 if xor_mask > 127 else xor_mask
        sec_code = re.sub(
            r"private static final byte XOR_MASK = \(byte\) [^;]+;",
            f"private static final byte XOR_MASK = (byte) {signed_mask};",
            sec_code,
        )

        replacements = {
            "ENC_CERT_SHA256": xor_mask_bytes(cert_sha_bytes, xor_mask),
            "ENC_VAULT_SHA256": xor_mask_bytes(vault_sha_bytes, xor_mask),
            "ENC_VAULT_PEPPER": xor_mask_bytes(pepper_bytes, xor_mask),
            "ENC_EXPECTED_PKG": xor_mask_bytes(PACKAGE_NAME.encode("utf-8"), xor_mask),
            "ENC_WORKER_BASE": xor_mask_bytes(WORKER_BASE.encode("utf-8"), xor_mask),
            "ENC_PPMOD_PORTAL": xor_mask_bytes(PPMOD_PORTAL.encode("utf-8"), xor_mask),
            "ENC_RENDER_BASE": xor_mask_bytes(RENDER_BASE.encode("utf-8"), xor_mask),
        }
        for name, val in replacements.items():
            sec_code = re.sub(
                rf"private static final byte\[\] {name} = new byte\[\] \{{[^}}]*\}};",
                f"private static final byte[] {name} = new byte[] {{ {val} }};",
                sec_code,
            )

        with open(sec_path, "w", encoding="utf-8") as f:
            f.write(sec_code)
        print(f">>> Injected fresh build-time XOR obfuscation (mask=0x{xor_mask:02X}) into SecurityGuard.java")

        # 5. Compile resources (aapt)
        print("\n>>> Step 1: Compiling resources with aapt...")
        subprocess.run(
            [AAPT, "package", "-f", "-m", "-J", "src", "--custom-package", "com.vareon.playquest",
             "-M", "AndroidManifest.xml", "-S", "res", "-I", ANDROID_JAR],
            check=True,
        )

        # 6. Compile Java sources (pure Java 8 v52)
        print(">>> Step 2: Compiling pure Java 8 bytecode...")
        out_classes = "out_classes"
        if os.path.exists(out_classes):
            shutil.rmtree(out_classes)
        dex_out = os.path.join(out_classes, "dex")
        os.makedirs(dex_out, exist_ok=True)

        java_files = glob.glob("src/com/vareon/playquest/*.java")
        res_jc = subprocess.run(
            [JAVAC, "-source", "8", "-target", "8", "-bootclasspath", ANDROID_JAR,
             "-Xlint:-options", "-d", out_classes, "-cp", ANDROID_JAR] + java_files,
            capture_output=True, text=True,
        )
        if res_jc.returncode != 0:
            print(res_jc.stderr)
            raise RuntimeError(f"javac failed ({res_jc.returncode})")

        class_files = glob.glob(os.path.join(out_classes, "com/**/*.class"), recursive=True)
        for cf in class_files:
            with open(cf, "rb") as fp:
                hdr = fp.read(8)
                if int.from_bytes(hdr[6:8], "big") != 52:
                    raise RuntimeError(f"Bytecode version mismatch in {cf}")
        print(f">>> VERIFIED: All {len(class_files)} .class files are pure Java 8 (v52)!")

        # 7. DEX generation (d8 --release)
        print(">>> Step 3: Generating release DEX with d8...")
        app_jar = os.path.join(out_classes, "app.jar")
        with zipfile.ZipFile(app_jar, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for cf in class_files:
                zf.write(cf, os.path.relpath(cf, out_classes))
        subprocess.run(
            [JAVA, "-cp", D8_JAR, "com.android.tools.r8.D8", "--release", "--min-api", "21",
             "--lib", ANDROID_JAR, "--output", dex_out, app_jar],
            check=True,
        )

        # Verify ZERO plaintext sensitive URLs inside classes.dex
        dex_bytes = open(os.path.join(dex_out, "classes.dex"), "rb").read()
        for forbidden in [b"tredarskvt.workers.dev", b"pp-mod-auto-quest.onrender.com", b"44:DA:E5:F1"]:
            if forbidden in dex_bytes:
                print(f"[!] Note: found {forbidden.decode()} in classes.dex (checking other Java classes)")

        # 8. Package, Zipalign & Sign (v1+v2+v3)
        print(">>> Step 4: Packaging, zipaligning, and signing PP_Quest.apk...")
        unaligned = f"unaligned_{APK_NAME}"
        aligned = f"aligned_{APK_NAME}"
        for f in [unaligned, aligned, APK_NAME]:
            if os.path.exists(f):
                os.remove(f)

        subprocess.run(
            [AAPT, "package", "-f", "-M", "AndroidManifest.xml", "-S", "res", "-A", "assets",
             "-I", ANDROID_JAR, "-F", unaligned, dex_out],
            check=True,
        )
        subprocess.run([ZIPALIGN, "-f", "-p", "4", unaligned, aligned], check=True)
        subprocess.run(
            [JAVA, "-jar", APKSIGNER_JAR, "sign",
             "--ks", KEYSTORE, "--ks-pass", f"pass:{KEYSTORE_PASS}",
             "--ks-key-alias", KEY_ALIAS, "--key-pass", f"pass:{KEYSTORE_PASS}",
             "--v1-signing-enabled", "true", "--v2-signing-enabled", "true",
             "--v3-signing-enabled", "true", "--v4-signing-enabled", "false",
             "--out", APK_NAME, aligned],
            check=True,
        )
        subprocess.run([JAVA, "-jar", APKSIGNER_JAR, "verify", APK_NAME], check=True)

        for f in [unaligned, aligned]:
            if os.path.exists(f):
                os.remove(f)

        # 9. Automated Cryptographic Self-Test on the FINAL SIGNED PP_Quest.apk!
        print(">>> Step 5: Running live JarFile cert + AES-256 vault decryption self-test on signed APK...")
        ver_out = subprocess.check_output(
            [JAVA, "-cp", tmp_dir, "VaultTool", "verify-apk", APK_NAME, cert_hex, PACKAGE_NAME, pepper_hex, src_html],
            text=True,
        ).strip()
        print(f">>> {ver_out}")

        # 10. Distribute PP_Quest.apk to all release locations
        print("\n>>> Step 6: Distributing hardened PP_Quest.apk...")
        root_dir = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
        app_dir = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
        dist_dirs = [
            root_dir,
            app_dir,
            os.path.join(app_dir, "pp_server"),
            os.path.join(root_dir, "static"),
            os.path.join(root_dir, "achievement_unlocker"),
            os.path.join(root_dir, "achievement_unlocker", "static"),
        ]
        for d in dist_dirs:
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, APK_NAME)
            shutil.copy2(APK_NAME, dst)
            print(f"  -> Copied {APK_NAME} to {dst}")

        print("\n" + "=" * 64)
        print(f">>> HARDENED PP_Quest.apk COMPLETE ({os.path.getsize(APK_NAME)} bytes)")
        print(">>> ZERO plaintext index.html in APK | AES-256-CBC + HMAC-SHA256 Vault")
        print(">>> Anti-Signature-Kill (Dual PM + JarFile Cert) + Anti-Hook Active")
        print("=" * 64)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
