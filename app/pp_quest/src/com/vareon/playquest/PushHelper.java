package com.vareon.playquest;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.PorterDuff;
import android.graphics.PorterDuffXfermode;
import android.graphics.Rect;
import android.graphics.RectF;
import android.os.Build;
import android.text.TextUtils;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class PushHelper {

    private static final String CHANNEL_ID = "pp_quest_alerts_v2";
    private static final String CHANNEL_NAME = "PP QUEST Notifications";
    private static final String PREF_NAME = "pp_push_dedup_v2";
    private static final String KEY_SEEN_IDS = "seen_ids";
    private static final String KEY_LAST_TS = "last_ts";
    private static final String KEY_USER_UID = "logged_in_uid";
    private static final int PUSH_JOB_ID = 7741;

    public static void setLoggedInUid(Context ctx, String uid) {
        if (ctx == null) return;
        try {
            SharedPreferences sp = ctx.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
            sp.edit().putString(KEY_USER_UID, uid != null ? uid.trim() : "").apply();
        } catch (Throwable ignored) {
        }
    }

    public static String getLoggedInUid(Context ctx) {
        if (ctx == null) return "";
        try {
            SharedPreferences sp = ctx.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
            String u = sp.getString(KEY_USER_UID, "");
            return u != null ? u.trim() : "";
        } catch (Throwable ignored) {
            return "";
        }
    }

    public static void scheduleBackgroundPushJob(Context ctx) {
        if (ctx == null || Build.VERSION.SDK_INT < 21) return;
        try {
            JobScheduler js = (JobScheduler) ctx.getSystemService(Context.JOB_SCHEDULER_SERVICE);
            if (js == null) return;
            ComponentName comp = new ComponentName(ctx, PushPollJobService.class);
            JobInfo.Builder b = new JobInfo.Builder(PUSH_JOB_ID, comp)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setPersisted(true);
            if (Build.VERSION.SDK_INT >= 24) {
                b.setPeriodic(15 * 60 * 1000L, 5 * 60 * 1000L);
            } else {
                b.setPeriodic(15 * 60 * 1000L);
            }
            js.schedule(b.build());
        } catch (Throwable ignored) {
        }
    }

    public static synchronized boolean isAlreadySeen(Context ctx, String notifId) {
        if (ctx == null || TextUtils.isEmpty(notifId)) return false;
        try {
            SharedPreferences sp = ctx.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
            String raw = sp.getString(KEY_SEEN_IDS, "");
            if (raw != null && raw.contains("|" + notifId + "|")) {
                return true;
            }
        } catch (Throwable ignored) {
        }
        return false;
    }

    public static synchronized void markSeen(Context ctx, String notifId, long createdAt) {
        if (ctx == null) return;
        try {
            SharedPreferences sp = ctx.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
            SharedPreferences.Editor ed = sp.edit();
            if (!TextUtils.isEmpty(notifId)) {
                String raw = sp.getString(KEY_SEEN_IDS, "|");
                if (raw == null || raw.isEmpty()) raw = "|";
                if (!raw.contains("|" + notifId + "|")) {
                    raw = raw + notifId + "|";
                    if (raw.length() > 2400) {
                        int cut = raw.indexOf('|', raw.length() - 1600);
                        if (cut > 0) raw = raw.substring(cut);
                    }
                    ed.putString(KEY_SEEN_IDS, raw);
                }
            }
            if (createdAt > 0) {
                long prev = sp.getLong(KEY_LAST_TS, 0L);
                if (createdAt > prev) {
                    ed.putLong(KEY_LAST_TS, createdAt);
                }
            }
            ed.apply();
        } catch (Throwable ignored) {
        }
    }

    public static void pollEdgeNotificationsAsync(final Context ctx) {
        if (ctx == null) return;
        new Thread(new Runnable() {
            @Override
            public void run() {
                pollEdgeNotificationsSync(ctx);
            }
        }).start();
    }

    public static void pollEdgeNotificationsSync(Context ctx) {
        if (ctx == null) return;
        try {
            SharedPreferences sp = ctx.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
            long lastTs = sp.getLong(KEY_LAST_TS, 0L);
            if (lastTs <= 0L) {
                lastTs = System.currentTimeMillis() - (60L * 60L * 1000L);
                sp.edit().putLong(KEY_LAST_TS, lastTs).apply();
            }

            String apiBase = SecurityGuard.getCloudWorkerApi();
            if (TextUtils.isEmpty(apiBase)) return;

            String savedUid = getLoggedInUid(ctx);
            String fullUrl = apiBase + "/api/push/latest?since=" + lastTs + "&limit=5";
            if (!TextUtils.isEmpty(savedUid)) {
                try {
                    fullUrl += "&uid=" + java.net.URLEncoder.encode(savedUid, "UTF-8");
                } catch (Throwable ignored) {
                }
            }
            URL url = new URL(fullUrl);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(6000);
            conn.setReadTimeout(6000);
            conn.setRequestProperty("Accept", "application/json");

            if (conn.getResponseCode() == 200) {
                BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = br.readLine()) != null) {
                    sb.append(line);
                }
                br.close();

                JSONObject root = new JSONObject(sb.toString());
                JSONArray arr = root.optJSONArray("notifications");
                if (arr != null && arr.length() > 0) {
                    // Dispatch oldest -> newest
                    for (int i = arr.length() - 1; i >= 0; i--) {
                        JSONObject item = arr.optJSONObject(i);
                        if (item == null) continue;
                        String id = item.optString("id", "");
                        String title = item.optString("title", "PP QUEST");
                        String msg = item.optString("message", "");
                        String img = item.optString("imageUrl", "");
                        long ts = item.optLong("createdAt", System.currentTimeMillis());
                        if (TextUtils.isEmpty(msg)) continue;
                        if (!TextUtils.isEmpty(id) && isAlreadySeen(ctx, id)) {
                            markSeen(ctx, id, ts);
                            continue;
                        }
                        showRichNotificationSync(ctx, title, msg, img, id, ts);
                    }
                }
            }
            conn.disconnect();
        } catch (Throwable ignored) {
        }
    }

    public static void showRichNotification(final Context ctx, final String title, final String message,
                                            final String imageUrl, final String notifId) {
        if (ctx == null) return;
        new Thread(new Runnable() {
            @Override
            public void run() {
                showRichNotificationSync(ctx, title, message, imageUrl, notifId, System.currentTimeMillis());
            }
        }).start();
    }

    private static void showRichNotificationSync(Context ctx, String title, String message,
                                                 String imageUrl, String notifId, long createdAt) {
        try {
            if (ctx == null) return;
            if (!TextUtils.isEmpty(notifId) && isAlreadySeen(ctx, notifId)) {
                return;
            }
            if (!TextUtils.isEmpty(notifId)) {
                markSeen(ctx, notifId, createdAt);
            }

            NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                NotificationChannel ch = new NotificationChannel(
                        CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_HIGH);
                ch.setDescription("PP QUEST live updates and announcements");
                ch.enableVibration(true);
                ch.enableLights(true);
                ch.setLightColor(0xFF10B981);
                nm.createNotificationChannel(ch);
            }

            Intent openIntent = new Intent(ctx, MainActivity.class);
            openIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            int piFlags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 23) {
                piFlags |= PendingIntent.FLAG_IMMUTABLE;
            }
            PendingIntent pi = PendingIntent.getActivity(ctx, (int) (System.currentTimeMillis() % 10000), openIntent, piFlags);

            Notification.Builder builder = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                    ? new Notification.Builder(ctx, CHANNEL_ID)
                    : new Notification.Builder(ctx);

            String safeTitle = TextUtils.isEmpty(title) ? "PP QUEST" : title;
            String safeMsg = message == null ? "" : message;

            builder.setSmallIcon(R.drawable.ic_notif_quest)
                    .setContentTitle(safeTitle)
                    .setContentText(safeMsg)
                    .setContentIntent(pi)
                    .setAutoCancel(true)
                    .setShowWhen(true)
                    .setWhen(createdAt > 0 ? createdAt : System.currentTimeMillis());

            if (Build.VERSION.SDK_INT >= 21) {
                builder.setColor(0xFF10B981);
                builder.setCategory(Notification.CATEGORY_MESSAGE);
                builder.setVisibility(Notification.VISIBILITY_PUBLIC);
            }
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
                builder.setPriority(Notification.PRIORITY_HIGH);
                builder.setDefaults(Notification.DEFAULT_ALL);
            }

            Bitmap largeLogo = getRoundedLogoBitmap(ctx);
            if (largeLogo != null) {
                builder.setLargeIcon(largeLogo);
            }

            Bitmap bannerBmp = null;
            if (!TextUtils.isEmpty(imageUrl) && imageUrl.startsWith("http")) {
                bannerBmp = downloadBitmap(imageUrl);
            }

            if (bannerBmp != null) {
                Notification.BigPictureStyle bps = new Notification.BigPictureStyle()
                        .bigPicture(bannerBmp)
                        .setBigContentTitle(safeTitle)
                        .setSummaryText(safeMsg);
                builder.setStyle(bps);
            } else {
                builder.setStyle(new Notification.BigTextStyle()
                        .setBigContentTitle(safeTitle)
                        .bigText(safeMsg));
            }

            int idInt = !TextUtils.isEmpty(notifId)
                    ? Math.abs(notifId.hashCode()) % 90000 + 200
                    : ((int) (System.currentTimeMillis() % 90000) + 200);
            nm.notify(idInt, builder.build());
        } catch (Throwable ignored) {
        }
    }

    private static Bitmap getRoundedLogoBitmap(Context ctx) {
        try {
            Bitmap src = BitmapFactory.decodeResource(ctx.getResources(), R.drawable.ic_launcher_quest_round);
            if (src == null) {
                src = BitmapFactory.decodeResource(ctx.getResources(), R.drawable.ic_launcher_quest);
            }
            if (src == null) return null;
            int size = 128;
            Bitmap scaled = Bitmap.createScaledBitmap(src, size, size, true);
            Bitmap out = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
            Canvas canvas = new Canvas(out);
            Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
            RectF rectF = new RectF(0, 0, size, size);
            canvas.drawRoundRect(rectF, 28f, 28f, paint);
            paint.setXfermode(new PorterDuffXfermode(PorterDuff.Mode.SRC_IN));
            canvas.drawBitmap(scaled, new Rect(0, 0, size, size), rectF, paint);
            return out;
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static Bitmap downloadBitmap(String imgUrl) {
        HttpURLConnection conn = null;
        try {
            URL u = new URL(imgUrl);
            conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(4000);
            conn.setDoInput(true);
            conn.connect();
            if (conn.getResponseCode() == 200) {
                InputStream is = conn.getInputStream();
                Bitmap bmp = BitmapFactory.decodeStream(is);
                is.close();
                return bmp;
            }
        } catch (Throwable ignored) {
        } finally {
            if (conn != null) {
                try { conn.disconnect(); } catch (Throwable ignored) {}
            }
        }
        return null;
    }
}
