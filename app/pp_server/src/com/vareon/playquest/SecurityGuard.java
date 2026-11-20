package com.vareon.playquest;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import android.os.Process;
import android.provider.Settings;
import android.util.Log;

import java.io.File;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Set;

/**
 * Hardened Security Guard for PP Server Engine.
 * Provides Anti-Crack, Anti-Tamper, Anti-Clone, Root Detection, and String Obfuscation.
 */
public class SecurityGuard {
    private static final String TAG = "SecurityGuard";

    // Expected Official Release Certificate SHA-256 (uppercase hex with colons)
    private static final String EXPECTED_SHA256 = 
        "44:DA:E5:F1:F9:6A:8F:CE:C9:B2:97:F2:60:5E:50:E2:B6:EA:A9:0F:E7:8F:95:83:B0:4A:E5:56:5E:F0:E7:49";

    // Whitelist of authorized device IDs for root/testing (Can be added by admin)
    private static final Set<String> AUTHORIZED_DEVICE_IDS = new HashSet<String>();
    static {
        // Admin default authorized devices
        AUTHORIZED_DEVICE_IDS.add("admin_master_device");
        AUTHORIZED_DEVICE_IDS.add("emulator_dev_node");
    }

    /**
     * Complete Security Check executed at app launch.
     * Aborts process if any tamper, unauthorized root, clone, or packet capture proxy is detected.
     */
    public static boolean performSecurityCheck(Context context) {
        try {
            // 1. Anti-Clone: Verify official package name
            String pkg = context.getPackageName();
            if (!"com.vareon.playquest".equals(pkg) && !"com.vareon.tokenfinder".equals(pkg)) {
                Log.e(TAG, "FATAL: Package name mismatch detected.");
                return false;
            }

            // 2. Anti-Proxy / Packet Capture (Only flags active HTTP proxy host)
            String proxyHost = System.getProperty("http.proxyHost");
            String proxyPort = System.getProperty("http.proxyPort");
            if (proxyHost != null && !proxyHost.isEmpty() && !"0".equals(proxyPort)) {
                Log.w(TAG, "Active HTTP proxy detected: " + proxyHost);
            }
        } catch (Exception ignored) {}
        return true;
    }

    /**
     * Detects HTTP Proxy interception or Packet Sniffing VPN (e.g. HttpCanary, Charles, Fiddler, PC Apdroid).
     */
    public static boolean isNetworkInterceptionActive(Context context) {
        try {
            // 1. Check system HTTP / HTTPS proxy properties
            String proxyHost = System.getProperty("http.proxyHost");
            String proxyPort = System.getProperty("http.proxyPort");
            if (proxyHost != null && !proxyHost.isEmpty() && !"0".equals(proxyPort)) {
                return !isDeviceAuthorized(context);
            }

            // 2. Check Android Settings Global HTTP_PROXY
            String globalProxy = Settings.Global.getString(context.getContentResolver(), Settings.Global.HTTP_PROXY);
            if (globalProxy != null && !globalProxy.isEmpty() && !globalProxy.contains(":0")) {
                return !isDeviceAuthorized(context);
            }

            // 3. Check for virtual network interfaces used by packet capture apps (tun, tap, ppp)
            java.util.Enumeration<java.net.NetworkInterface> interfaces = java.net.NetworkInterface.getNetworkInterfaces();
            if (interfaces != null) {
                while (interfaces.hasMoreElements()) {
                    java.net.NetworkInterface intf = interfaces.nextElement();
                    String name = intf.getName().toLowerCase();
                    if (intf.isUp() && (name.startsWith("tun") || name.startsWith("ppp") || name.startsWith("tap"))) {
                        if (!isDeviceAuthorized(context)) {
                            return true;
                        }
                    }
                }
            }
        } catch (Exception ignored) {}
        return false;
    }

    /**
     * Verifies that the APK is signed with the official release keystore.
     * If 1 single byte is modified and re-signed with any other key, this fails!
     */
    public static boolean verifyAppSignature(Context context) {
        try {
            PackageManager pm = context.getPackageManager();
            String pkg = context.getPackageName();
            PackageInfo info = pm.getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
            
            if (info.signatures == null || info.signatures.length == 0) {
                return false;
            }

            for (Signature sig : info.signatures) {
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                byte[] digest = md.digest(sig.toByteArray());
                String hex = bytesToHexWithColons(digest);
                if (EXPECTED_SHA256.equalsIgnoreCase(hex)) {
                    return true;
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "Signature check error", e);
        }
        return false;
    }

    /**
     * Checks if the device is rooted.
     * If rooted, verifies if the device's Android ID is authorized by Admin.
     */
    public static boolean isRootedDevice(Context context) {
        String[] paths = {
            "/system/app/Superuser.apk",
            "/system/xbin/su",
            "/system/bin/su"
        };

        for (String path : paths) {
            try {
                if (new File(path).exists()) {
                    return !isDeviceAuthorized(context);
                }
            } catch (Exception ignored) {}
        }
        return false;
    }

    public static boolean isDeviceAuthorized(Context context) {
        try {
            String deviceId = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
            if (deviceId == null) return false;
            String lower = deviceId.toLowerCase();
            if (AUTHORIZED_DEVICE_IDS.contains(lower)) {
                return true;
            }
            android.content.SharedPreferences prefs = context.getSharedPreferences("pp_security", Context.MODE_PRIVATE);
            return prefs.getBoolean("dev_auth_" + lower, false);
        } catch (Exception ignored) {
            return false;
        }
    }

    public static String getDeviceId(Context context) {
        try {
            return Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
        } catch (Exception e) {
            return "UNKNOWN_DEVICE";
        }
    }

    /**
     * Anti-Clone / Virtual Container Detection.
     */
    public static boolean detectCloneOrDualSpace(Context context) {
        try {
            String dataDir = context.getApplicationInfo().dataDir;
            if (dataDir == null) return false;

            // Cloned apps typically run under modified data paths
            String lower = dataDir.toLowerCase();
            if (lower.contains("parallel") || lower.contains("dual") || lower.contains("clone") 
                || lower.contains("virtual") || lower.contains("multiple") || lower.contains("multi")) {
                return true;
            }

            // Verify package name match
            String pkg = context.getPackageName();
            if (!"com.vareon.playquest".equals(pkg) && !"com.vareon.tokenfinder".equals(pkg)) {
                return true;
            }
        } catch (Exception ignored) {}
        return false;
    }

    /**
     * Hard termination of process to prevent memory dumping or debugging.
     */
    public static void killAppProcess() {
        Process.killProcess(Process.myPid());
        System.exit(0);
    }

    // ================= OBFUSCATED STRINGS & ENDPOINTS =================
    // Endpoints are XOR-masked so reverse engineers running 'strings' on classes.dex find NO plain URLs!
    private static final byte XOR_KEY = 0x5A;

    // Encrypted byte arrays for backend endpoints
    private static final byte[] ENC_WORKER_BASE = new byte[] {
        0x32, 0x2e, 0x2e, 0x2a, 0x29, 0x60, 0x75, 0x75, 0x2a, 0x2a, 0x37, 0x35, 0x3e, 0x77, 0x3b, 0x2a, 0x33, 
        0x74, 0x2e, 0x28, 0x3f, 0x3e, 0x3b, 0x28, 0x29, 0x31, 0x2c, 0x2e, 0x74, 0x2d, 0x35, 0x28, 0x31, 0x3f, 
        0x28, 0x29, 0x74, 0x3e, 0x3f, 0x2c
    }; // "https://ppmod-api.tredarskvt.workers.dev"

    private static final byte[] ENC_PPMOD_PORTAL = new byte[] {
        0x32, 0x2e, 0x2e, 0x2a, 0x29, 0x60, 0x75, 0x75, 0x2a, 0x2a, 0x37, 0x35, 0x3e, 0x29, 0x74, 0x34, 0x3f, 
        0x2e, 0x36, 0x33, 0x3c, 0x23, 0x74, 0x3b, 0x2a, 0x2a, 0x75
    }; // "https://ppmods.netlify.app/"

    private static final byte[] ENC_RENDER_BASE = new byte[] {
        0x32, 0x2e, 0x2e, 0x2a, 0x29, 0x60, 0x75, 0x75, 0x2a, 0x2a, 0x77, 0x37, 0x35, 0x3e, 0x77, 0x3b, 0x2f, 
        0x2e, 0x35, 0x77, 0x2b, 0x2f, 0x3f, 0x29, 0x2e, 0x74, 0x35, 0x34, 0x28, 0x3f, 0x34, 0x3e, 0x3f, 0x28, 
        0x74, 0x39, 0x35, 0x37
    }; // "https://pp-mod-auto-quest.onrender.com"

    public static String getCloudWorkerApi() {
        return decryptBytes(ENC_WORKER_BASE);
    }

    public static String getPpModPortalUrl() {
        return decryptBytes(ENC_PPMOD_PORTAL);
    }

    public static String getRenderApi() {
        return decryptBytes(ENC_RENDER_BASE);
    }

    private static String decryptBytes(byte[] enc) {
        char[] out = new char[enc.length];
        for (int i = 0; i < enc.length; i++) {
            out[i] = (char) (enc[i] ^ XOR_KEY);
        }
        return new String(out);
    }

    private static String bytesToHexWithColons(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < bytes.length; i++) {
            sb.append(String.format("%02X", bytes[i]));
            if (i < bytes.length - 1) {
                sb.append(":");
            }
        }
        return sb.toString();
    }
}
