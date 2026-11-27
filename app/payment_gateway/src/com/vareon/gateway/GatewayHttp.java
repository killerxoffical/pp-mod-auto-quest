package com.vareon.gateway;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Direct Cloudflare Worker D1 HTTP Forwarder with 3x Automatic Retry & Honest Status Reporting.
 * Zero Firebase writes, zero slow Render hops, zero false "SAVED" status on network failures.
 */
public class GatewayHttp {

    public interface GatewayCallback {
        void onComplete(String trxId, String status, String message);
    }

    public static void forwardSms(GatewayStorage storage, SmsRecord record, GatewayCallback callback) {
        new Thread(new ForwardTask(storage, record, callback)).start();
    }

    public static void forwardSmsSync(GatewayStorage storage, SmsRecord record, GatewayCallback callback) {
        new ForwardTask(storage, record, callback).run();
    }

    private static class ForwardTask implements Runnable {
        private final GatewayStorage storage;
        private final SmsRecord record;
        private final GatewayCallback callback;

        ForwardTask(GatewayStorage storage, SmsRecord record, GatewayCallback callback) {
            this.storage = storage;
            this.record = record;
            this.callback = callback;
        }

        @Override
        public void run() {
            String resultingStatus = "RETRY";
            String serverMsg = "Network error - queued for auto retry";
            boolean syncedOk = false;
            boolean isAutoApproved = false;

            String cfUrl = storage.getCloudflareUrl() + "/api/gateway/sms";
            String secret = storage.getSecretKey();

            JSONObject payload = new JSONObject();
            try {
                payload.put("secret", secret);
                payload.put("sender", record.getSender());
                payload.put("message", record.getRawMessage());
                payload.put("trxId", record.getTrxId());
                payload.put("amount", record.getAmount());
                payload.put("balance", record.getBalance());
                payload.put("method", record.getMethod());
                payload.put("timestamp", record.getTimestamp());
            } catch (Exception ignored) {}

            // 3x Automatic Retry with short backoff (0ms -> 1200ms -> 3000ms)
            int[] waits = new int[] { 0, 1200, 3000 };
            JSONObject resp = null;
            for (int attempt = 0; attempt < waits.length; attempt++) {
                if (waits[attempt] > 0) {
                    try { Thread.sleep(waits[attempt]); } catch (InterruptedException ignored) {}
                }
                resp = postJson(cfUrl, payload, secret);
                if (resp != null) break;
            }

            if (resp != null) {
                if (resp.optBoolean("autoApproved", false)) {
                    resultingStatus = "AUTO_APPROVED";
                    syncedOk = true;
                    isAutoApproved = true;
                    serverMsg = "Auto Approved & Credited in D1!";
                } else if (resp.optBoolean("locked", false)) {
                    resultingStatus = "LOCKED";
                    syncedOk = true;
                    serverMsg = "Admin Personal Locked";
                } else if (resp.optBoolean("duplicate", false)) {
                    resultingStatus = "DUPLICATE";
                    syncedOk = true;
                    serverMsg = "Already Claimed / Used";
                } else if (resp.optBoolean("expired", false)) {
                    resultingStatus = "EXPIRED";
                    syncedOk = true;
                    serverMsg = "Expired (>30m)";
                } else if (resp.optBoolean("ok", false)) {
                    resultingStatus = "SYNCED";
                    syncedOk = true;
                    serverMsg = "Synced to Cloudflare D1";
                } else {
                    resultingStatus = "FAILED";
                    serverMsg = resp.optString("error", "Rejected by server");
                }
            }

            boolean wasAlreadySynced = storage.isTrxSynced(record.getTrxId());
            if (syncedOk) {
                storage.markTrxSynced(record.getTrxId());
                if (!wasAlreadySynced) {
                    storage.recordStats(true, isAutoApproved, record.getAmount());
                }
            }
            storage.updateRecordStatus(record.getTrxId(), resultingStatus);

            if (callback != null) {
                callback.onComplete(record.getTrxId(), resultingStatus, serverMsg);
            }
        }
    }

    private static JSONObject postJson(String targetUrl, JSONObject body, String secret) {
        HttpURLConnection conn = null;
        try {
            URL u = new URL(targetUrl);
            conn = (HttpURLConnection) u.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("x-gateway-secret", secret);
            conn.setRequestProperty("User-Agent", "PPAutoGateway/2.0");
            conn.setDoOutput(true);
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);

            OutputStream os = conn.getOutputStream();
            os.write(body.toString().getBytes("UTF-8"));
            os.flush();
            os.close();

            int code = conn.getResponseCode();
            BufferedReader br;
            if (code >= 200 && code < 300) {
                br = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
            } else if (conn.getErrorStream() != null) {
                br = new BufferedReader(new InputStreamReader(conn.getErrorStream(), "UTF-8"));
            } else {
                return null;
            }

            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line);
            }
            br.close();

            if (sb.length() == 0) return null;
            return new JSONObject(sb.toString());
        } catch (Exception e) {
            return null;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }
}
