package com.vareon.gateway;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;

/**
 * Storage manager for PP Auto Gateway v2.0.
 * - Automatically resets today's local SMS feed & daily counters every midnight (Asia/Dhaka) so storage NEVER fills up.
 * - Maintains a compact rolling set of synced TrxIDs (max 150) so inbox catch-up never double-uploads old SMS.
 * - Routes 100% directly to Cloudflare Worker D1 (zero dead Render server lag).
 */
public class GatewayStorage {
    private static final String PREF_NAME = "pp_payment_gateway_prefs_v2";
    private static final String KEY_ENABLED = "gw_enabled";
    private static final String KEY_CF_URL = "gw_cf_url";
    private static final String KEY_SECRET = "gw_secret";
    private static final String KEY_RECORDS = "gw_records_today";
    private static final String KEY_TODAY_DATE = "gw_today_date";
    private static final String KEY_SYNCED_TRX = "gw_synced_trx_set";
    private static final String KEY_STAT_FORWARDED = "stat_forwarded";
    private static final String KEY_STAT_APPROVED = "stat_approved";
    private static final String KEY_STAT_AMOUNT = "stat_amount";

    public static final String DEFAULT_CF = "https://ppmod-api.tredarskvt.workers.dev";
    public static final String DEFAULT_SECRET = "PPMOD_GATEWAY_SEC_2025";

    private final SharedPreferences prefs;

    public GatewayStorage(Context context) {
        this.prefs = context.getApplicationContext().getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        ensureDailyReset();
    }

    public static String getTodayDhakaDate() {
        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        sdf.setTimeZone(TimeZone.getTimeZone("Asia/Dhaka"));
        return sdf.format(new Date());
    }

    /**
     * Automatically clears yesterday's local SMS log & daily counters at midnight so phone storage never bloats.
     */
    public synchronized void ensureDailyReset() {
        String today = getTodayDhakaDate();
        String savedDate = prefs.getString(KEY_TODAY_DATE, "");
        if (!today.equals(savedDate)) {
            prefs.edit()
                .putString(KEY_TODAY_DATE, today)
                .putString(KEY_RECORDS, "[]")
                .putInt(KEY_STAT_FORWARDED, 0)
                .putInt(KEY_STAT_APPROVED, 0)
                .putLong(KEY_STAT_AMOUNT, Double.doubleToLongBits(0.0))
                .apply();
        }
    }

    public boolean isEnabled() {
        return prefs.getBoolean(KEY_ENABLED, true);
    }

    public void setEnabled(boolean enabled) {
        prefs.edit().putBoolean(KEY_ENABLED, enabled).apply();
    }

    public String getServerUrl() {
        return getCloudflareUrl();
    }

    public void setServerUrl(String url) {
        setCloudflareUrl(url);
    }

    public String getCloudflareUrl() {
        String url = prefs.getString(KEY_CF_URL, DEFAULT_CF);
        if (url == null || url.trim().isEmpty() || url.contains("onrender.com")) {
            url = DEFAULT_CF;
            prefs.edit().putString(KEY_CF_URL, url).apply();
        }
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }

    public void setCloudflareUrl(String url) {
        if (url != null && !url.trim().isEmpty()) {
            String clean = url.trim();
            if (clean.endsWith("/")) clean = clean.substring(0, clean.length() - 1);
            prefs.edit().putString(KEY_CF_URL, clean).apply();
        }
    }

    public String getSecretKey() {
        String sec = prefs.getString(KEY_SECRET, DEFAULT_SECRET);
        return (sec == null || sec.trim().isEmpty()) ? DEFAULT_SECRET : sec.trim();
    }

    public void setSecretKey(String secret) {
        if (secret != null && !secret.trim().isEmpty()) {
            prefs.edit().putString(KEY_SECRET, secret.trim()).apply();
        }
    }

    public int getStatForwarded() {
        ensureDailyReset();
        return prefs.getInt(KEY_STAT_FORWARDED, 0);
    }

    public int getStatApproved() {
        ensureDailyReset();
        return prefs.getInt(KEY_STAT_APPROVED, 0);
    }

    public double getStatAmount() {
        ensureDailyReset();
        return Double.longBitsToDouble(prefs.getLong(KEY_STAT_AMOUNT, Double.doubleToLongBits(0.0)));
    }

    public synchronized void recordStats(boolean isSynced, boolean isApproved, double amount) {
        ensureDailyReset();
        int f = getStatForwarded() + (isSynced ? 1 : 0);
        int a = getStatApproved() + (isApproved ? 1 : 0);
        double amt = getStatAmount() + (isApproved ? amount : 0);
        prefs.edit()
            .putInt(KEY_STAT_FORWARDED, f)
            .putInt(KEY_STAT_APPROVED, a)
            .putLong(KEY_STAT_AMOUNT, Double.doubleToLongBits(amt))
            .apply();
    }

    public synchronized boolean isTrxSynced(String trxId) {
        if (trxId == null || trxId.isEmpty()) return false;
        String key = trxId.trim().toUpperCase(Locale.US);
        try {
            JSONArray arr = new JSONArray(prefs.getString(KEY_SYNCED_TRX, "[]"));
            for (int i = 0; i < arr.length(); i++) {
                if (key.equals(arr.optString(i))) return true;
            }
        } catch (Exception ignored) {}
        return false;
    }

    public synchronized void markTrxSynced(String trxId) {
        if (trxId == null || trxId.isEmpty()) return;
        String key = trxId.trim().toUpperCase(Locale.US);
        try {
            JSONArray oldArr = new JSONArray(prefs.getString(KEY_SYNCED_TRX, "[]"));
            JSONArray newArr = new JSONArray();
            newArr.put(key);
            for (int i = 0; i < oldArr.length() && newArr.length() < 150; i++) {
                String v = oldArr.optString(i);
                if (!key.equals(v)) newArr.put(v);
            }
            prefs.edit().putString(KEY_SYNCED_TRX, newArr.toString()).apply();
        } catch (Exception ignored) {}
    }

    public synchronized List<SmsRecord> getRecords() {
        ensureDailyReset();
        List<SmsRecord> list = new ArrayList<SmsRecord>();
        String jsonStr = prefs.getString(KEY_RECORDS, "[]");
        try {
            JSONArray arr = new JSONArray(jsonStr);
            for (int i = 0; i < arr.length(); i++) {
                JSONObject obj = arr.getJSONObject(i);
                SmsRecord rec = SmsRecord.fromJson(obj);
                if (rec != null) {
                    list.add(rec);
                }
            }
        } catch (JSONException ignored) {}
        return list;
    }

    public synchronized boolean hasRecord(String trxId) {
        if (trxId == null) return false;
        for (SmsRecord r : getRecords()) {
            if (trxId.equalsIgnoreCase(r.getTrxId())) return true;
        }
        return false;
    }

    public synchronized void addRecord(SmsRecord newRecord) {
        ensureDailyReset();
        if (newRecord == null) return;
        List<SmsRecord> current = getRecords();
        List<SmsRecord> updated = new ArrayList<SmsRecord>();

        updated.add(newRecord);
        for (SmsRecord rec : current) {
            if (!rec.getTrxId().equalsIgnoreCase(newRecord.getTrxId())) {
                updated.add(rec);
            }
            if (updated.size() >= 80) break; // Keep today's feed lightweight
        }
        saveRecords(updated);
    }

    public synchronized void updateRecordStatus(String trxId, String status) {
        ensureDailyReset();
        if (trxId == null) return;
        List<SmsRecord> current = getRecords();
        for (SmsRecord rec : current) {
            if (rec.getTrxId().equalsIgnoreCase(trxId)) {
                rec.setStatus(status);
                break;
            }
        }
        saveRecords(current);
    }

    public synchronized List<SmsRecord> getPendingRetryRecords() {
        List<SmsRecord> out = new ArrayList<SmsRecord>();
        for (SmsRecord rec : getRecords()) {
            String st = rec.getStatus();
            if ("PENDING".equalsIgnoreCase(st) || "RETRY".equalsIgnoreCase(st) || "FAILED".equalsIgnoreCase(st)) {
                out.add(rec);
            }
        }
        return out;
    }

    private void saveRecords(List<SmsRecord> list) {
        JSONArray arr = new JSONArray();
        for (SmsRecord rec : list) {
            arr.put(rec.toJson());
        }
        prefs.edit().putString(KEY_RECORDS, arr.toString()).apply();
    }
}
