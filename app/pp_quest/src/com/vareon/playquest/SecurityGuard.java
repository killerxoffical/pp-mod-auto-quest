package com.vareon.playquest;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import android.os.Debug;
import android.provider.Settings;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.File;
import java.io.FileReader;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.GZIPInputStream;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * Hardened Fortress SecurityGuard for PP QUEST (com.ppm.quest).
 * 5-Layer Protection:
 * 1. Full Multi-Asset AES-256-CBC + HMAC-SHA256 Encrypted Vault (assets/v.dat) — ZERO HTML/JS/PNG/SVG/JSON in APK
 * 2. Dual-Layer Anti-Signature-Kill (PackageManager + Raw Disk JarFile META-INF X.509 Cert Verification)
 * 3. Certificate-Bound AES/HMAC Key Derivation (Re-signing APK mathematically breaks vault decryption)
 * 4. Anti-MT/NP/Frida/Xposed/LSPosed/SandHook/Debugger/Clone Detection (Fail-Closed Process Kill)
 * 5. Build-Time String Encryption + R8 Full Code Obfuscation + AAPT2 Resource Confusion
 */
public class SecurityGuard {
    // ==================== BUILD-INJECTED XOR-OBFUSCATED CONSTANTS ====================
    private static final byte XOR_MASK = (byte) 0x5A;
    private static final byte[] ENC_CERT_SHA256 = new byte[] { 0 };
    private static final byte[] ENC_VAULT_SHA256 = new byte[] { 0 };
    private static final byte[] ENC_VAULT_PEPPER = new byte[] { 0 };
    private static final byte[] ENC_EXPECTED_PKG = new byte[] { 0 };
    private static final byte[] ENC_WORKER_BASE = new byte[] { 0 };
    private static final byte[] ENC_PPMOD_PORTAL = new byte[] { 0 };
    private static final byte[] ENC_RENDER_BASE = new byte[] { 0 };

    private static volatile byte[] sVerifiedCertSha256 = null;
    private static volatile Map<String, byte[]> sVaultAssets = null;
    private static final Object VAULT_LOCK = new Object();

    public static boolean performSecurityCheck(Context context) {
        try {
            if (context == null) return false;

            // 1. Strict Package Name Lock
            String expectedPkg = decodeString(ENC_EXPECTED_PKG);
            if (expectedPkg.isEmpty() || !expectedPkg.equals(context.getPackageName())) {
                return false;
            }

            // 2. Anti-Debuggable Flag & Active Debugger / Hook / Signature Killer Detection
            if ((context.getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
                return false;
            }
            if (isDebuggerOrHookActive()) {
                return false;
            }

            // 3. Anti-Clone / Dual Space / Virtual App Detection
            if (detectCloneOrDualSpace(context)) {
                return false;
            }

            // 4. Anti-PMS-Hook Source APK Path Verification
            String sourceDir = context.getApplicationInfo().sourceDir;
            if (sourceDir == null || sourceDir.trim().isEmpty()) {
                return false;
            }
            String lowerSrc = sourceDir.toLowerCase(Locale.US);
            if (lowerSrc.contains("mt_hook") || lowerSrc.contains("orig.apk")
                    || lowerSrc.contains("/cache/") || lowerSrc.contains("/sdcard/")
                    || lowerSrc.contains("killer")) {
                return false;
            }

            // 5. Dual-Layer Signature Verification (PackageManager + Raw JarFile on Disk)
            if (!verifyAppSignature(context)) {
                return false;
            }

            // 6. Encrypted Multi-Asset Vault Binary Integrity Check (1 byte edit in v.dat = instant kill)
            if (!verifyAssetIntegrity(context)) {
                return false;
            }

            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    public static boolean isDebuggerOrHookActive() {
        try {
            if (Debug.isDebuggerConnected() || Debug.waitingForDebugger()) {
                return true;
            }

            String[] badClasses = new String[] {
                "bin.mt.signature.KillerApplication",
                "cc.binmt.signature.PmsHookApplication",
                "cc.binmt.signature.Hook",
                "com.np.dex.PmsHookApplication",
                "np.manager.SignatureKiller",
                "com.swift.sandhook.SandHook",
                "de.robv.android.xposed.XposedBridge",
                "de.robv.android.xposed.XposedHelpers",
                "me.weishu.epic.art.Epic",
                "com.saurik.substrate.MS"
            };
            ClassLoader cl = SecurityGuard.class.getClassLoader();
            for (String cls : badClasses) {
                try {
                    Class.forName(cls, false, cl);
                    return true;
                } catch (Throwable ignored) {}
            }

            String[] fridaPaths = new String[] {
                "/data/local/tmp/frida-server",
                "/data/local/tmp/re.frida.server",
                "/data/local/tmp/frida-agent.so"
            };
            for (String p : fridaPaths) {
                if (new File(p).exists()) return true;
            }

            BufferedReader br = null;
            try {
                br = new BufferedReader(new FileReader("/proc/self/maps"));
                String line;
                while ((line = br.readLine()) != null) {
                    String lower = line.toLowerCase(Locale.US);
                    if (lower.contains("frida") || lower.contains("xposed")
                            || lower.contains("lsposed") || lower.contains("edxposed")
                            || lower.contains("substrate") || lower.contains("signaturekiller")
                            || lower.contains("sandhook") || lower.contains("binmt")) {
                        return true;
                    }
                }
            } catch (Throwable ignored) {
            } finally {
                try { if (br != null) br.close(); } catch (Throwable ignored) {}
            }
        } catch (Throwable ignored) {}
        return false;
    }

    public static boolean verifyAppSignature(Context context) {
        try {
            if (context == null) return false;
            byte[] expectedCert = unmaskBytes(ENC_CERT_SHA256);
            if (expectedCert.length != 32) return false;

            boolean pmMatched = false;
            PackageManager pm = context.getPackageManager();
            String pkg = context.getPackageName();
            Signature[] signatures = null;

            if (Build.VERSION.SDK_INT >= 28) {
                try {
                    PackageInfo info = pm.getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES);
                    if (info != null && info.signingInfo != null) {
                        signatures = info.signingInfo.hasMultipleSigners()
                                ? info.signingInfo.getApkContentsSigners()
                                : info.signingInfo.getSigningCertificateHistory();
                    }
                } catch (Throwable ignored) {}
            }
            if (signatures == null || signatures.length == 0) {
                PackageInfo info = pm.getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
                if (info != null) signatures = info.signatures;
            }
            if (signatures == null || signatures.length == 0) return false;

            MessageDigest md = MessageDigest.getInstance("SHA-256");
            for (Signature sig : signatures) {
                byte[] digest = md.digest(sig.toByteArray());
                if (constantTimeEquals(expectedCert, digest)) {
                    pmMatched = true;
                    break;
                }
            }
            if (!pmMatched) return false;

            byte[] rawApkCert = extractRawApkCertSha256(context.getApplicationInfo().sourceDir);
            if (rawApkCert == null || !constantTimeEquals(expectedCert, rawApkCert)) {
                return false;
            }

            sVerifiedCertSha256 = rawApkCert;
            return true;
        } catch (Throwable e) {
            return false;
        }
    }

    public static byte[] extractRawApkCertSha256(String apkPath) {
        if (apkPath == null || apkPath.isEmpty()) return null;
        JarFile jf = null;
        try {
            jf = new JarFile(apkPath, true);
            JarEntry entry = jf.getJarEntry("AndroidManifest.xml");
            if (entry == null) entry = jf.getJarEntry("classes.dex");
            if (entry == null) return null;

            InputStream is = jf.getInputStream(entry);
            byte[] buf = new byte[8192];
            while (is.read(buf) != -1) {
                // Must drain entry so JarFile populates entry.getCertificates()
            }
            is.close();

            Certificate[] certs = entry.getCertificates();
            if (certs == null || certs.length == 0) return null;

            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return md.digest(certs[0].getEncoded());
        } catch (Throwable t) {
            return null;
        } finally {
            try { if (jf != null) jf.close(); } catch (Throwable ignored) {}
        }
    }

    public static boolean verifyAssetIntegrity(Context context) {
        InputStream is = null;
        try {
            if (context == null) return false;
            byte[] expectedVault = unmaskBytes(ENC_VAULT_SHA256);
            if (expectedVault.length != 32) return false;

            is = context.getAssets().open("v.dat");
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[16384];
            int len;
            while ((len = is.read(buf)) != -1) {
                md.update(buf, 0, len);
            }
            byte[] actual = md.digest();
            return constantTimeEquals(expectedVault, actual);
        } catch (Throwable t) {
            return false;
        } finally {
            try { if (is != null) is.close(); } catch (Throwable ignored) {}
        }
    }

    /**
     * Decrypts the multi-asset vault (assets/v.dat) purely into RAM once, bound to live APK cert + pkg + pepper.
     * Contains ALL HTML, JS, JSON, SVG, and PNG files — ZERO web files exist in plaintext inside the APK!
     */
    private static Map<String, byte[]> ensureVaultLoaded(Context context) {
        Map<String, byte[]> cached = sVaultAssets;
        if (cached != null) return cached;

        synchronized (VAULT_LOCK) {
            if (sVaultAssets != null) return sVaultAssets;
            InputStream is = null;
            try {
                if (context == null || !performSecurityCheck(context)) {
                    killAppProcess();
                    return null;
                }
                byte[] certSha = sVerifiedCertSha256;
                if (certSha == null) {
                    certSha = extractRawApkCertSha256(context.getApplicationInfo().sourceDir);
                }
                if (certSha == null || certSha.length != 32) {
                    killAppProcess();
                    return null;
                }

                is = context.getAssets().open("v.dat");
                ByteArrayOutputStream rawOut = new ByteArrayOutputStream();
                byte[] buf = new byte[32768];
                int n;
                while ((n = is.read(buf)) != -1) {
                    rawOut.write(buf, 0, n);
                }
                byte[] blob = rawOut.toByteArray();
                if (blob.length <= 48) {
                    killAppProcess();
                    return null;
                }

                byte[] iv = Arrays.copyOfRange(blob, 0, 16);
                byte[] storedMac = Arrays.copyOfRange(blob, 16, 48);
                byte[] cipherBytes = Arrays.copyOfRange(blob, 48, blob.length);

                byte[] pepper = unmaskBytes(ENC_VAULT_PEPPER);
                byte[] pkgBytes = context.getPackageName().getBytes("UTF-8");

                MessageDigest mdAes = MessageDigest.getInstance("SHA-256");
                mdAes.update(certSha);
                mdAes.update((byte) '|');
                mdAes.update(pkgBytes);
                mdAes.update((byte) '|');
                mdAes.update(pepper);
                byte[] aesKey = mdAes.digest();

                MessageDigest mdMac = MessageDigest.getInstance("SHA-256");
                mdMac.update("MAC|".getBytes("UTF-8"));
                mdMac.update(certSha);
                mdMac.update((byte) '|');
                mdMac.update(pepper);
                byte[] hmacKey = mdMac.digest();

                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
                mac.update(iv);
                mac.update(cipherBytes);
                byte[] calcMac = mac.doFinal();
                if (!constantTimeEquals(storedMac, calcMac)) {
                    killAppProcess();
                    return null;
                }

                Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
                cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new IvParameterSpec(iv));
                byte[] plainBundle = cipher.doFinal(cipherBytes);

                DataInputStream dis = new DataInputStream(new ByteArrayInputStream(plainBundle));
                int magic = dis.readInt();
                if (magic != 0x50505156) { // "PPQV"
                    killAppProcess();
                    return null;
                }
                int count = dis.readInt();
                if (count <= 0 || count > 500) {
                    killAppProcess();
                    return null;
                }

                Map<String, byte[]> map = new HashMap<String, byte[]>(count * 2);
                for (int i = 0; i < count; i++) {
                    int nameLen = dis.readUnsignedShort();
                    byte[] nameBytes = new byte[nameLen];
                    dis.readFully(nameBytes);
                    String name = new String(nameBytes, "UTF-8").toLowerCase(Locale.US);
                    byte isGz = dis.readByte();
                    int payloadLen = dis.readInt();
                    byte[] payload = new byte[payloadLen];
                    dis.readFully(payload);

                    if (isGz == 1) {
                        GZIPInputStream gis = new GZIPInputStream(new ByteArrayInputStream(payload));
                        ByteArrayOutputStream out = new ByteArrayOutputStream();
                        int r;
                        while ((r = gis.read(buf)) != -1) {
                            out.write(buf, 0, r);
                        }
                        gis.close();
                        payload = out.toByteArray();
                    }
                    map.put(name, payload);
                }
                dis.close();
                sVaultAssets = map;
                return map;
            } catch (Throwable t) {
                killAppProcess();
                return null;
            } finally {
                try { if (is != null) is.close(); } catch (Throwable ignored) {}
            }
        }
    }

    public static byte[] getVaultAsset(Context context, String relPath) {
        try {
            if (relPath == null || relPath.isEmpty()) return null;
            Map<String, byte[]> map = ensureVaultLoaded(context);
            if (map == null) return null;
            String key = relPath.trim().toLowerCase(Locale.US);
            while (key.startsWith("/")) key = key.substring(1);
            return map.get(key);
        } catch (Throwable t) {
            return null;
        }
    }

    public static byte[] decryptVaultHtmlBytes(Context context) {
        return getVaultAsset(context, "index.html");
    }

    public static boolean isNetworkInterceptionActive(Context context) {
        try {
            String proxyHost = System.getProperty("http.proxyHost");
            String proxyPort = System.getProperty("http.proxyPort");
            if (proxyHost != null && !proxyHost.isEmpty() && !"0".equals(proxyPort)) {
                return true;
            }
            String globalProxy = Settings.Global.getString(context.getContentResolver(), Settings.Global.HTTP_PROXY);
            if (globalProxy != null && !globalProxy.isEmpty() && !globalProxy.contains(":0")) {
                return true;
            }
        } catch (Throwable ignored) {}
        return false;
    }

    public static boolean isRootedDevice(Context context) {
        try {
            String[] paths = {
                "/system/app/Superuser.apk",
                "/system/xbin/su",
                "/system/bin/su",
                "/sbin/su",
                "/system/sd/xbin/su"
            };
            for (String path : paths) {
                if (new File(path).exists()) return true;
            }
            if (Build.TAGS != null && Build.TAGS.contains("test-keys")) return true;
        } catch (Throwable ignored) {}
        return false;
    }

    public static boolean isDeviceAuthorized(Context context) {
        return false;
    }

    public static String getDeviceId(Context context) {
        try {
            if (context == null) return "46e14d2451d85c3f";
            android.content.SharedPreferences prefs = context.getSharedPreferences("pp_device_meta", Context.MODE_PRIVATE);
            String savedId = prefs.getString("unique_device_id", null);
            if (savedId != null && !savedId.trim().isEmpty()) {
                return savedId;
            }
            String id = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
            if (id == null || id.trim().isEmpty() || "46e14d2451d85c3f".equalsIgnoreCase(id) || "9774d56d682e549c".equalsIgnoreCase(id)) {
                id = "emu_" + java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 16);
            }
            prefs.edit().putString("unique_device_id", id).apply();
            return id;
        } catch (Throwable e) {
            return "46e14d2451d85c3f";
        }
    }

    public static boolean detectCloneOrDualSpace(Context context) {
        try {
            if (context == null) return true;
            String dataDir = context.getApplicationInfo().dataDir;
            if (dataDir == null) return true;
            String lower = dataDir.toLowerCase(Locale.US);
            if (lower.contains("parallel") || lower.contains("dual") || lower.contains("clone")
                    || lower.contains("virtual") || lower.contains("multiple") || lower.contains("multi")) {
                return true;
            }
            String expectedPkg = decodeString(ENC_EXPECTED_PKG);
            if (!expectedPkg.equals(context.getPackageName())) {
                return true;
            }
        } catch (Throwable ignored) {
            return true;
        }
        return false;
    }

    public static void killAppProcess() {
        try {
            android.os.Process.killProcess(android.os.Process.myPid());
            System.exit(0);
        } catch (Throwable ignored) {}
    }

    // ==================== XOR-OBFUSCATED ENDPOINT GETTERS ====================
    public static String getCloudWorkerApi() {
        return decodeString(ENC_WORKER_BASE);
    }

    public static String getPpModPortalUrl() {
        return decodeString(ENC_PPMOD_PORTAL);
    }

    public static String getRenderApi() {
        return decodeString(ENC_RENDER_BASE);
    }

    private static byte[] unmaskBytes(byte[] enc) {
        if (enc == null) return new byte[0];
        byte[] out = new byte[enc.length];
        for (int i = 0; i < enc.length; i++) {
            out[i] = (byte) (enc[i] ^ XOR_MASK ^ ((i * 31) & 0xFF));
        }
        return out;
    }

    private static String decodeString(byte[] enc) {
        try {
            return new String(unmaskBytes(enc), "UTF-8");
        } catch (Throwable t) {
            return "";
        }
    }

    private static boolean constantTimeEquals(byte[] a, byte[] b) {
        if (a == null || b == null || a.length != b.length) return false;
        int diff = 0;
        for (int i = 0; i < a.length; i++) {
            diff |= (a[i] ^ b[i]);
        }
        return diff == 0;
    }
}
