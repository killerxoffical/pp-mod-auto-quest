package com.vareon.playquest;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import android.os.Debug;
import android.provider.Settings;
import android.util.Log;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileReader;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.util.Arrays;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.GZIPInputStream;

import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * Hardened Fortress SecurityGuard for PP QUEST (com.ppm.quest).
 * Protects against:
 * 1. APK Decompile / Asset Editing (AES-256-CBC + HMAC-SHA256 encrypted UI vault, zero plaintext HTML in APK)
 * 2. Re-signing / Repackaging (Dual PackageManager + raw JarFile META-INF certificate verification)
 * 3. MT Manager / NP Manager "Kill Signature Verification" (PMS hook & classloader/maps detection + cert-bound AES key)
 * 4. Frida / Xposed / LSPosed / Debugger / Clone / Dual Space
 * 5. Endpoint String Extraction (Fresh build-time XOR-obfuscated byte arrays for all URLs & hashes)
 */
public class SecurityGuard {
    private static final String TAG = "PPQGuard";

    // ==================== BUILD-INJECTED XOR-OBFUSCATED CONSTANTS ====================
    // Every build generates fresh XOR masks so NO plain cert SHA-256, hash, pepper, or API URL appears in classes.dex!
    private static final byte XOR_MASK = (byte) 75;

    // Official release certificate SHA-256 (32 raw bytes, XOR-masked)
    private static final byte[] ENC_CERT_SHA256 = new byte[] { (byte)15, (byte)-114, (byte)-112, (byte)-25, (byte)-50, (byte)-70, (byte)126, (byte)92, (byte)122, (byte)-18, (byte)-22, (byte)-20, (byte)95, (byte)-122, (byte)-87, (byte)120, (byte)13, (byte)-82, (byte)-52, (byte)9, (byte)-64, (byte)79, (byte)116, (byte)1, (byte)19, (byte)6, (byte)-120, (byte)88, (byte)113, (byte)56, (byte)14, (byte)-61 };

    // Expected SHA-256 of assets/vault/core.bin (32 raw bytes, XOR-masked)
    private static final byte[] ENC_VAULT_SHA256 = new byte[] { (byte)-102, (byte)-93, (byte)-103, (byte)103, (byte)-27, (byte)-41, (byte)24, (byte)-76, (byte)37, (byte)-1, (byte)-40, (byte)-41, (byte)-16, (byte)25, (byte)62, (byte)-107, (byte)53, (byte)-69, (byte)16, (byte)-24, (byte)92, (byte)-49, (byte)-18, (byte)119, (byte)-113, (byte)55, (byte)-103, (byte)-74, (byte)78, (byte)127, (byte)-125, (byte)123 };

    // Build-specific 32-byte key derivation pepper (XOR-masked)
    private static final byte[] ENC_VAULT_PEPPER = new byte[] { (byte)3, (byte)-26, (byte)25, (byte)-2, (byte)-104, (byte)51, (byte)36, (byte)69, (byte)2, (byte)52, (byte)-86, (byte)29, (byte)82, (byte)-29, (byte)-19, (byte)83, (byte)-104, (byte)-88, (byte)127, (byte)21, (byte)29, (byte)100, (byte)101, (byte)47, (byte)-73, (byte)-2, (byte)-127, (byte)-117, (byte)75, (byte)-59, (byte)-117, (byte)46 };

    // Obfuscated package name ("com.ppm.quest")
    private static final byte[] ENC_EXPECTED_PKG = new byte[] { (byte)40, (byte)59, (byte)24, (byte)56, (byte)71, (byte)-96, (byte)-100, (byte)-68, (byte)-62, (byte)41, (byte)24, (byte)109, (byte)75 };

    // Obfuscated API endpoints
    private static final byte[] ENC_WORKER_BASE = new byte[] { (byte)35, (byte)32, (byte)1, (byte)102, (byte)68, (byte)-22, (byte)-34, (byte)-67, (byte)-61, (byte)44, (byte)16, (byte)113, (byte)91, (byte)-11, (byte)-104, (byte)-22, (byte)-46, (byte)106, (byte)17, (byte)116, (byte)66, (byte)-92, (byte)-128, (byte)-16, (byte)-48, (byte)39, (byte)27, (byte)122, (byte)1, (byte)-65, (byte)-122, (byte)-8, (byte)-64, (byte)-47, (byte)39, (byte)5, (byte)57, (byte)84, (byte)-76, (byte)-124 };
    private static final byte[] ENC_PPMOD_PORTAL = new byte[] { (byte)35, (byte)32, (byte)1, (byte)102, (byte)68, (byte)-22, (byte)-34, (byte)-67, (byte)-61, (byte)44, (byte)16, (byte)113, (byte)91, (byte)-85, (byte)-41, (byte)-12, (byte)-34, (byte)48, (byte)9, (byte)111, (byte)65, (byte)-71, (byte)-49, (byte)-29, (byte)-45, (byte)60, (byte)66 };
    private static final byte[] ENC_RENDER_BASE = new byte[] { (byte)35, (byte)32, (byte)1, (byte)102, (byte)68, (byte)-22, (byte)-34, (byte)-67, (byte)-61, (byte)44, (byte)80, (byte)115, (byte)80, (byte)-68, (byte)-44, (byte)-5, (byte)-50, (byte)48, (byte)10, (byte)43, (byte)86, (byte)-75, (byte)-124, (byte)-15, (byte)-41, (byte)98, (byte)2, (byte)96, (byte)93, (byte)-83, (byte)-121, (byte)-18, (byte)-50, (byte)-58, (byte)123, (byte)21, (byte)120, (byte)93 };

    // Cached verified raw cert SHA-256 bytes (computed directly from APK on disk)
    private static volatile byte[] sVerifiedCertSha256 = null;

    /**
     * Master Fail-Closed Security Check executed at launch and before serving UI vault.
     * Any tamper, repackage, signature kill, debugger, or clone returns false -> process kill.
     */
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
            String lowerSrc = sourceDir.toLowerCase();
            if (lowerSrc.contains("mt_hook") || lowerSrc.contains("orig.apk")
                    || lowerSrc.contains("/cache/") || lowerSrc.contains("/sdcard/")
                    || lowerSrc.contains("killer")) {
                return false;
            }

            // 5. Dual-Layer Signature Verification (PackageManager + Raw JarFile on Disk)
            if (!verifyAppSignature(context)) {
                return false;
            }

            // 6. Encrypted Vault Binary Integrity Check (1 byte edit in core.bin = instant kill)
            if (!verifyAssetIntegrity(context)) {
                return false;
            }

            return true;
        } catch (Throwable t) {
            // FAIL-CLOSED: never allow bypass on exception
            return false;
        }
    }

    /**
     * Detects debuggers, Frida, Xposed/LSPosed, and MT Manager / NP Manager Signature Killers.
     */
    public static boolean isDebuggerOrHookActive() {
        try {
            if (Debug.isDebuggerConnected() || Debug.waitingForDebugger()) {
                return true;
            }

            // Known Signature Killer, Hook & Repackaging Framework classes
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

            // Frida binaries check
            String[] fridaPaths = new String[] {
                "/data/local/tmp/frida-server",
                "/data/local/tmp/re.frida.server",
                "/data/local/tmp/frida-agent.so"
            };
            for (String p : fridaPaths) {
                if (new File(p).exists()) return true;
            }

            // /proc/self/maps scan for injected hook libraries
            BufferedReader br = null;
            try {
                br = new BufferedReader(new FileReader("/proc/self/maps"));
                String line;
                while ((line = br.readLine()) != null) {
                    String lower = line.toLowerCase();
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

    /**
     * Dual-Layer Signature Verification:
     * Layer A: Android PackageManager signing cert SHA-256
     * Layer B: Direct raw APK JarFile META-INF signature cert SHA-256 (defeats PMS Signature Killer hooks!)
     */
    public static boolean verifyAppSignature(Context context) {
        try {
            if (context == null) return false;
            byte[] expectedCert = unmaskBytes(ENC_CERT_SHA256);
            if (expectedCert.length != 32) return false;

            // Layer A: PackageManager signature check
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

            // Layer B: Direct Raw APK JarFile Certificate Extraction (Bypasses PackageManager hooks!)
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

    /**
     * Reads AndroidManifest.xml through JarFile with signature verification enabled
     * and returns the SHA-256 digest of the real X.509 certificate embedded in META-INF/*.RSA.
     */
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
                // Must read entry completely so JarFile populates entry.getCertificates()
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

    /**
     * Verifies SHA-256 of the encrypted binary asset assets/vault/core.bin.
     */
    public static boolean verifyAssetIntegrity(Context context) {
        InputStream is = null;
        try {
            if (context == null) return false;
            byte[] expectedVault = unmaskBytes(ENC_VAULT_SHA256);
            if (expectedVault.length != 32) return false;

            is = context.getAssets().open("vault/core.bin");
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[8192];
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
     * Decrypts assets/vault/core.bin purely in RAM using a key cryptographically bound to:
     *   - The live APK's raw signing certificate SHA-256 (from META-INF)
     *   - The running package name ("com.ppm.quest")
     *   - The XOR-obfuscated build pepper
     * If anyone re-signs the APK or edits core.bin, HMAC & AES decryption mathematically FAIL!
     */
    public static byte[] decryptVaultHtmlBytes(Context context) {
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

            // Read entire vault/core.bin: [16B IV][32B HMAC-SHA256][AES-256-CBC Ciphertext]
            is = context.getAssets().open("vault/core.bin");
            ByteArrayOutputStream rawOut = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
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

            // Derive AES-256 key = SHA-256(certSha || '|' || pkg || '|' || pepper)
            MessageDigest mdAes = MessageDigest.getInstance("SHA-256");
            mdAes.update(certSha);
            mdAes.update((byte) '|');
            mdAes.update(pkgBytes);
            mdAes.update((byte) '|');
            mdAes.update(pepper);
            byte[] aesKey = mdAes.digest();

            // Derive HMAC key = SHA-256("MAC|" || certSha || '|' || pepper)
            MessageDigest mdMac = MessageDigest.getInstance("SHA-256");
            mdMac.update("MAC|".getBytes("UTF-8"));
            mdMac.update(certSha);
            mdMac.update((byte) '|');
            mdMac.update(pepper);
            byte[] hmacKey = mdMac.digest();

            // Verify HMAC-SHA256(IV || ciphertext)
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
            mac.update(iv);
            mac.update(cipherBytes);
            byte[] calcMac = mac.doFinal();
            if (!constantTimeEquals(storedMac, calcMac)) {
                killAppProcess();
                return null;
            }

            // Decrypt AES-256-CBC/PKCS5Padding
            Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(aesKey, "AES"), new IvParameterSpec(iv));
            byte[] gzipped = cipher.doFinal(cipherBytes);

            // Gunzip purely in RAM
            GZIPInputStream gis = new GZIPInputStream(new ByteArrayInputStream(gzipped));
            ByteArrayOutputStream htmlOut = new ByteArrayOutputStream();
            while ((n = gis.read(buf)) != -1) {
                htmlOut.write(buf, 0, n);
            }
            gis.close();
            return htmlOut.toByteArray();
        } catch (Throwable t) {
            killAppProcess();
            return null;
        } finally {
            try { if (is != null) is.close(); } catch (Throwable ignored) {}
        }
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
            String lower = dataDir.toLowerCase();
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
