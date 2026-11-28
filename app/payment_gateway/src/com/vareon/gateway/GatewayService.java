package com.vareon.gateway;

import android.Manifest;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.database.ContentObserver;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;

import java.util.List;

/**
 * 24/7 Immortal Foreground Service for PP Auto Gateway v2.1.
 * - Android 5-15 safe FOREGROUND_SERVICE_TYPE_DATA_SYNC
 * - Live ContentObserver on content://sms + 5s fast watchdog + WakeLock (works across Xiaomi/MIUI, Samsung, Oppo, Realme, Vivo, Huawei, Tecno/Infinix)
 * - Auto-resurrects via AlarmManager on onTaskRemoved() if swiped from Recents
 */
public class GatewayService extends Service {
    public static final String CHANNEL_ID = "pp_auto_gateway_channel_v2";
    public static final int NOTIFICATION_ID = 1001;
    private static final long WATCHDOG_INTERVAL_MS = 5000L;

    private GatewayStorage storage;
    private Handler handler;
    private ContentObserver smsObserver;
    private WatchdogTask watchdogTask;
    private volatile boolean isSyncRunning = false;

    @Override
    public void onCreate() {
        super.onCreate();
        storage = new GatewayStorage(this);
        handler = new Handler(Looper.getMainLooper());
        watchdogTask = new WatchdogTask(this);
        createNotificationChannel();
        registerSmsObserver();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification notification = buildNotification();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }

        handler.removeCallbacks(watchdogTask);
        handler.postDelayed(watchdogTask, 2000L);
        return START_STICKY;
    }

    private void registerSmsObserver() {
        try {
            smsObserver = new SmsInboxObserver(this, handler);
            getContentResolver().registerContentObserver(Uri.parse("content://sms"), true, smsObserver);
        } catch (Throwable ignored) {}
    }

    public void scheduleWatchdogNext() {
        if (handler != null && watchdogTask != null) {
            handler.postDelayed(watchdogTask, WATCHDOG_INTERVAL_MS);
        }
    }

    public void runBackgroundSync() {
        if (isSyncRunning || storage == null || !storage.isEnabled()) return;
        isSyncRunning = true;
        new Thread(new BackgroundSyncWorker(this)).start();
    }

    public void executeSyncInternal() {
        PowerManager.WakeLock wl = null;
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PPGateway:InboxWatchdog");
                wl.acquire(15000L);
            }
        } catch (Throwable ignored) {}

        try {
            storage.ensureDailyReset();

            if (Build.VERSION.SDK_INT < 23 || checkSelfPermission(Manifest.permission.READ_SMS) == PackageManager.PERMISSION_GRANTED) {
                long cutoff = System.currentTimeMillis() - (28L * 60L * 1000L);
                scanUriForPayments(Uri.parse("content://sms/inbox"), "date >= ?", new String[] { String.valueOf(cutoff) });
                // OEM fallback for dual-SIM Xiaomi/Samsung/Vivo/Tecno devices where MFS SMS may sit in content://sms with type=1
                scanUriForPayments(Uri.parse("content://sms"), "type = 1 AND date >= ?", new String[] { String.valueOf(cutoff) });
            }

            List<SmsRecord> pending = storage.getPendingRetryRecords();
            ServiceSyncCallback cb = new ServiceSyncCallback(this);
            for (SmsRecord rec : pending) {
                if (storage.isTrxSynced(rec.getTrxId())) continue;
                GatewayHttp.forwardSmsSync(storage, rec, cb);
            }

            updateNotification();
        } catch (Throwable ignored) {
        } finally {
            try { if (wl != null && wl.isHeld()) wl.release(); } catch (Throwable ignored) {}
            isSyncRunning = false;
        }
    }

    private void scanUriForPayments(Uri uri, String selection, String[] selArgs) {
        Cursor cursor = null;
        try {
            cursor = getContentResolver().query(
                uri,
                new String[] { "address", "body", "date" },
                selection,
                selArgs,
                "date DESC LIMIT 20"
            );
            if (cursor != null) {
                while (cursor.moveToNext()) {
                    String addr = cursor.getString(0);
                    String body = cursor.getString(1);
                    long dt = cursor.getLong(2);
                    SmsRecord rec = SmsParser.parse(addr, body, dt);
                    if (rec != null && !storage.isTrxSynced(rec.getTrxId()) && !storage.hasRecord(rec.getTrxId())) {
                        storage.addRecord(rec);
                    }
                }
            }
        } catch (Throwable ignored) {
        } finally {
            if (cursor != null) {
                try { cursor.close(); } catch (Throwable ignored) {}
            }
        }
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        try {
            if (storage != null && storage.isEnabled()) {
                Intent restartIntent = new Intent(getApplicationContext(), BootReceiver.class);
                restartIntent.setAction(BootReceiver.ACTION_RESTART_SERVICE);
                PendingIntent pi = PendingIntent.getBroadcast(
                    getApplicationContext(),
                    2025,
                    restartIntent,
                    Build.VERSION.SDK_INT >= 23
                        ? (PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE)
                        : PendingIntent.FLAG_UPDATE_CURRENT
                );
                AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
                if (am != null) {
                    long triggerAt = SystemClock.elapsedRealtime() + 3000L;
                    if (Build.VERSION.SDK_INT >= 23) {
                        am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pi);
                    } else {
                        am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pi);
                    }
                }
            }
        } catch (Throwable ignored) {}
        super.onTaskRemoved(rootIntent);
    }

    private Notification buildNotification() {
        Intent openAppIntent = new Intent(this, MainActivity.class);
        PendingIntent pendingIntent = PendingIntent.getActivity(
            this, 0, openAppIntent,
            Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0
        );

        int fwd = storage != null ? storage.getStatForwarded() : 0;
        int app = storage != null ? storage.getStatApproved() : 0;
        String text = "Cloudflare D1 Active • Today: " + fwd + " SMS | " + app + " Auto-Approved";

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= 26) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        return builder
            .setContentTitle("PP Auto Payment Gateway v2.0")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build();
    }

    private void updateNotification() {
        try {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.notify(NOTIFICATION_ID, buildNotification());
            }
        } catch (Throwable ignored) {}
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "PP Auto Gateway Service",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Keeps 24/7 Cloudflare D1 payment SMS bridge active");
            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onDestroy() {
        if (handler != null) handler.removeCallbacksAndMessages(null);
        if (smsObserver != null) {
            try { getContentResolver().unregisterContentObserver(smsObserver); } catch (Throwable ignored) {}
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private static class WatchdogTask implements Runnable {
        private final GatewayService svc;
        WatchdogTask(GatewayService svc) { this.svc = svc; }
        @Override
        public void run() {
            svc.runBackgroundSync();
            svc.scheduleWatchdogNext();
        }
    }

    private static class DelayedSyncTrigger implements Runnable {
        private final GatewayService svc;
        DelayedSyncTrigger(GatewayService svc) { this.svc = svc; }
        @Override
        public void run() {
            svc.runBackgroundSync();
        }
    }

    private static class SmsInboxObserver extends ContentObserver {
        private final GatewayService svc;
        private final Handler h;
        SmsInboxObserver(GatewayService svc, Handler h) {
            super(h);
            this.svc = svc;
            this.h = h;
        }
        @Override
        public void onChange(boolean selfChange) {
            super.onChange(selfChange);
            if (h != null) {
                h.postDelayed(new DelayedSyncTrigger(svc), 1200L);
            }
        }
    }

    private static class BackgroundSyncWorker implements Runnable {
        private final GatewayService svc;
        BackgroundSyncWorker(GatewayService svc) { this.svc = svc; }
        @Override
        public void run() {
            svc.executeSyncInternal();
        }
    }

    private static class ServiceSyncCallback implements GatewayHttp.GatewayCallback {
        private final Context ctx;
        ServiceSyncCallback(Context ctx) { this.ctx = ctx.getApplicationContext(); }
        @Override
        public void onComplete(String trxId, String status, String message) {
            Intent notifyIntent = new Intent(SmsReceiver.ACTION_SMS_PROCESSED);
            notifyIntent.setPackage(ctx.getPackageName());
            notifyIntent.putExtra("trxId", trxId);
            notifyIntent.putExtra("status", status);
            ctx.sendBroadcast(notifyIntent);
        }
    }
}
