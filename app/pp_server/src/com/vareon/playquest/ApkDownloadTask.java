package com.vareon.playquest;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class ApkDownloadTask {
    private static final String TAG = "ApkDownloadTask";
    private static volatile boolean isDownloading = false;
    private static File downloadedFile = null;

    public static void startDownload(final MainActivity activity, final String apkUrl) {
        if (activity == null) return;
        if (isDownloading) {
            Toast.makeText(activity, "Download already in progress...", Toast.LENGTH_SHORT).show();
            return;
        }
        if (apkUrl == null || apkUrl.trim().isEmpty()) {
            Toast.makeText(activity, "Invalid download URL", Toast.LENGTH_SHORT).show();
            return;
        }

        isDownloading = true;
        Thread downloadThread = new Thread(new WorkerRunnable(activity, apkUrl.trim()));
        downloadThread.start();
    }

    public static void installApk(final MainActivity activity) {
        if (activity == null) return;
        File apk = downloadedFile;
        if (apk == null || !apk.exists()) {
            File outDir = activity.getExternalFilesDir(null);
            if (outDir == null) outDir = activity.getCacheDir();
            File defApk = new File(outDir, "PPM_Cloud_v5.1.apk");
            if (defApk.exists() && defApk.length() > 500000) {
                apk = defApk;
            } else {
                Toast.makeText(activity, "Please download the update first", Toast.LENGTH_SHORT).show();
                return;
            }
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (!activity.getPackageManager().canRequestPackageInstalls()) {
                    Toast.makeText(activity, "Please allow 'Install unknown apps' permission to update", Toast.LENGTH_LONG).show();
                    Intent permIntent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES);
                    permIntent.setData(Uri.parse("package:" + activity.getPackageName()));
                    activity.startActivity(permIntent);
                    return;
                }
            }

            Intent intent = new Intent(Intent.ACTION_VIEW);
            Uri apkUri;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                apkUri = Uri.parse("content://com.ppm.cloud.provider/" + apk.getName());
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } else {
                apkUri = Uri.fromFile(apk);
            }
            intent.setDataAndType(apkUri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(intent);
        } catch (Exception e) {
            Log.e(TAG, "Install failed", e);
            Toast.makeText(activity, "Install failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    public static class WorkerRunnable implements Runnable {
        private final MainActivity activity;
        private final String apkUrl;

        public WorkerRunnable(MainActivity act, String url) {
            this.activity = act;
            this.apkUrl = url;
        }

        @Override
        public void run() {
            InputStream in = null;
            FileOutputStream out = null;
            HttpURLConnection conn = null;
            try {
                URL url = new URL(apkUrl);
                for (int redirectCount = 0; redirectCount < 5; redirectCount++) {
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setInstanceFollowRedirects(true);
                    conn.setConnectTimeout(15000);
                    conn.setReadTimeout(30000);
                    conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android " + Build.VERSION.RELEASE + ") PPM_Cloud/5.1");
                    conn.connect();

                    int status = conn.getResponseCode();
                    if (status == HttpURLConnection.HTTP_MOVED_PERM || status == HttpURLConnection.HTTP_MOVED_TEMP || status == 307 || status == 308) {
                        String newUrl = conn.getHeaderField("Location");
                        if (newUrl != null && !newUrl.isEmpty()) {
                            url = new URL(newUrl);
                            conn.disconnect();
                            continue;
                        }
                    }
                    break;
                }

                int totalLength = conn.getContentLength();
                in = conn.getInputStream();

                File outDir = activity.getExternalFilesDir(null);
                if (outDir == null) outDir = activity.getCacheDir();
                File apkFile = new File(outDir, "PPM_Cloud_v5.1.apk");
                if (apkFile.exists()) {
                    apkFile.delete();
                }

                out = new FileOutputStream(apkFile);
                byte[] buffer = new byte[8192];
                long downloaded = 0;
                int bytesRead;
                long lastUpdateTime = 0;

                while ((bytesRead = in.read(buffer)) != -1) {
                    out.write(buffer, 0, bytesRead);
                    downloaded += bytesRead;

                    long now = System.currentTimeMillis();
                    if (now - lastUpdateTime > 150) {
                        lastUpdateTime = now;
                        int percent = (totalLength > 0) ? (int) ((downloaded * 100) / totalLength) : -1;
                        activity.runOnUiThread(new ProgressRunnable(activity, percent, downloaded, totalLength));
                    }
                }

                out.flush();
                downloadedFile = apkFile;
                isDownloading = false;

                activity.runOnUiThread(new CompleteRunnable(activity, downloaded, totalLength > 0 ? totalLength : downloaded));

            } catch (Exception e) {
                isDownloading = false;
                Log.e(TAG, "Download error", e);
                activity.runOnUiThread(new ErrorRunnable(activity, e.getMessage()));
            } finally {
                try { if (in != null) in.close(); } catch (Exception ignored) {}
                try { if (out != null) out.close(); } catch (Exception ignored) {}
                try { if (conn != null) conn.disconnect(); } catch (Exception ignored) {}
            }
        }
    }

    public static class ProgressRunnable implements Runnable {
        private final MainActivity activity;
        private final int percent;
        private final long downloaded;
        private final long total;

        public ProgressRunnable(MainActivity act, int p, long d, long t) {
            this.activity = act;
            this.percent = p;
            this.downloaded = d;
            this.total = t;
        }

        @Override
        public void run() {
            if (activity.getMainAppWebView() != null) {
                activity.getMainAppWebView().evaluateJavascript("if(window.onApkDownloadProgress) window.onApkDownloadProgress(" + percent + ", " + downloaded + ", " + total + ");", null);
            }
        }
    }

    public static class CompleteRunnable implements Runnable {
        private final MainActivity activity;
        private final long downloaded;
        private final long total;

        public CompleteRunnable(MainActivity act, long d, long t) {
            this.activity = act;
            this.downloaded = d;
            this.total = t;
        }

        @Override
        public void run() {
            if (activity.getMainAppWebView() != null) {
                activity.getMainAppWebView().evaluateJavascript("if(window.onApkDownloadProgress) window.onApkDownloadProgress(100, " + downloaded + ", " + total + ");", null);
                activity.getMainAppWebView().evaluateJavascript("if(window.onApkDownloadComplete) window.onApkDownloadComplete();", null);
            }
            installApk(activity);
        }
    }

    public static class ErrorRunnable implements Runnable {
        private final MainActivity activity;
        private final String error;

        public ErrorRunnable(MainActivity act, String err) {
            this.activity = act;
            this.error = err;
        }

        @Override
        public void run() {
            Toast.makeText(activity, "Download error: " + error, Toast.LENGTH_LONG).show();
            if (activity.getMainAppWebView() != null) {
                String clean = error != null ? error.replace("'", "\\'") : "Unknown error";
                activity.getMainAppWebView().evaluateJavascript("if(window.onApkDownloadError) window.onApkDownloadError('" + clean + "');", null);
            }
        }
    }
}
