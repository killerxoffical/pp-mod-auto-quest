package com.vareon.playquest;

import android.net.Uri;
import android.os.Build;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class AppWebClient extends WebViewClient {
    private final MainActivity activity;

    public AppWebClient(MainActivity activity) {
        this.activity = activity;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
        if (request != null && request.getUrl() != null) {
            String url = request.getUrl().toString();
            activity.checkUrlForToken(url);
            handleUrl(url);
        }
        return false;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
        activity.checkUrlForToken(url);
        handleUrl(url);
        return false;
    }

    @Override
    public void onPageFinished(WebView view, String url) {
        super.onPageFinished(view, url);
        activity.checkUrlForToken(url);
        handleUrl(url);
        activity.extractEmailFromPage();
    }

    @Override
    public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
        // Prevent Chromium renderer crash from killing entire app process
        return true;
    }

    private void handleUrl(String url) {
        if (url == null) return;
        try {
            Uri uri = Uri.parse(url);
            String fragment = uri.getFragment();
            if ("close".equals(fragment) || url.contains("#close") || url.contains("signinconsent") || url.contains("closeoob")) {
                activity.checkCookiesForToken();
            }
        } catch (Exception ignored) {}
    }
}
