package com.vareon.playquest;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Random;

public class CloudSyncClient {
    public static final String CF_WORKER_URL = "https://ppmod-api.tredarskvt.workers.dev/api/sync/save";
    public static final String RENDER_URL = "https://pp-mod-auto-quest.onrender.com/api/sync/create";

    public interface SyncCallback {
        void onSuccess(String code);
        void onError(String msg);
    }

    public static void syncAccount(String email, String token, SyncCallback callback) {
        new Thread(new SyncWorker(email, token, callback)).start();
    }

    private static class SyncWorker implements Runnable {
        private final String email;
        private final String token;
        private final SyncCallback callback;

        SyncWorker(String email, String token, SyncCallback callback) {
            this.email = email;
            this.token = token;
            this.callback = callback;
        }

        @Override
        public void run() {
            String generatedCode = "";

            // 1. Try Render API
            try {
                URL rUrl = new URL(RENDER_URL);
                HttpURLConnection conn = (HttpURLConnection) rUrl.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);

                JSONObject body = new JSONObject();
                body.put("email", email);
                body.put("token", token);

                OutputStream os = conn.getOutputStream();
                os.write(body.toString().getBytes("UTF-8"));
                os.close();

                if (conn.getResponseCode() == 200) {
                    BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = br.readLine()) != null) sb.append(line);
                    br.close();

                    JSONObject res = new JSONObject(sb.toString());
                    if (res.optBoolean("ok", false) && res.has("code")) {
                        generatedCode = res.getString("code");
                    }
                }
            } catch (Exception ignored) {}

            if (generatedCode == null || generatedCode.length() != 6) {
                Random rand = new Random();
                generatedCode = String.valueOf(100000 + rand.nextInt(900000));
            }

            // 2. Persist to Cloudflare D1
            try {
                URL cfUrl = new URL(CF_WORKER_URL);
                HttpURLConnection cfConn = (HttpURLConnection) cfUrl.openConnection();
                cfConn.setRequestMethod("POST");
                cfConn.setRequestProperty("Content-Type", "application/json");
                cfConn.setDoOutput(true);
                cfConn.setConnectTimeout(6000);
                cfConn.setReadTimeout(6000);

                JSONObject cfBody = new JSONObject();
                cfBody.put("email", email);
                cfBody.put("token", token);
                cfBody.put("code", generatedCode);

                OutputStream os = cfConn.getOutputStream();
                os.write(cfBody.toString().getBytes("UTF-8"));
                os.close();

                cfConn.getResponseCode();
            } catch (Exception ignored) {}

            new Handler(Looper.getMainLooper()).post(new ResultPoster(callback, generatedCode));
        }
    }

    private static class ResultPoster implements Runnable {
        private final SyncCallback callback;
        private final String code;

        ResultPoster(SyncCallback callback, String code) {
            this.callback = callback;
            this.code = code;
        }

        @Override
        public void run() {
            if (callback != null) {
                callback.onSuccess(code);
            }
        }
    }
}
