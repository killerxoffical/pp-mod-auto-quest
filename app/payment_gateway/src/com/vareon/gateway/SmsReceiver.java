package com.vareon.gateway;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.telephony.SmsMessage;

/**
 * Zero-Drop SMS BroadcastReceiver using goAsync() + WakeLock so Android 8-15
 * NEVER freezes or kills the Cloudflare D1 upload while the screen is locked.
 */
public class SmsReceiver extends BroadcastReceiver {
    public static final String ACTION_SMS_PROCESSED = "com.vareon.gateway.ACTION_SMS_PROCESSED";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !"android.provider.Telephony.SMS_RECEIVED".equals(intent.getAction())) {
            return;
        }

        Context appContext = context.getApplicationContext();
        GatewayStorage storage = new GatewayStorage(appContext);
        if (!storage.isEnabled()) {
            return;
        }

        Bundle bundle = intent.getExtras();
        if (bundle == null) return;

        Object[] pdus = (Object[]) bundle.get("pdus");
        String format = bundle.getString("format");
        if (pdus == null || pdus.length == 0) return;

        StringBuilder fullBody = new StringBuilder();
        String sender = "";
        long timestamp = System.currentTimeMillis();

        for (Object pdu : pdus) {
            try {
                SmsMessage message;
                if (Build.VERSION.SDK_INT >= 23 && format != null) {
                    message = SmsMessage.createFromPdu((byte[]) pdu, format);
                } else {
                    message = SmsMessage.createFromPdu((byte[]) pdu);
                }
                if (message != null) {
                    if (sender.isEmpty()) {
                        sender = message.getDisplayOriginatingAddress();
                        if (message.getTimestampMillis() > 0) {
                            timestamp = message.getTimestampMillis();
                        }
                    }
                    fullBody.append(message.getMessageBody());
                }
            } catch (Exception ignored) {}
        }

        String rawText = fullBody.toString();
        if (rawText.isEmpty()) return;

        SmsRecord record = SmsParser.parse(sender, rawText, timestamp);
        if (record == null) return;

        if (storage.isTrxSynced(record.getTrxId())) {
            return;
        }

        storage.addRecord(record);

        PendingResult pendingResult = goAsync();
        PowerManager.WakeLock wl = null;
        try {
            PowerManager pm = (PowerManager) appContext.getSystemService(Context.POWER_SERVICE);
            if (pm != null) {
                wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PPGateway:SmsUpload");
                wl.acquire(18000L);
            }
        } catch (Throwable ignored) {}

        new Thread(new AsyncUploadWorker(appContext, storage, record, pendingResult, wl)).start();
    }

    private static class SmsProcessedNotifier implements GatewayHttp.GatewayCallback {
        private final Context appContext;

        SmsProcessedNotifier(Context appContext) {
            this.appContext = appContext;
        }

        @Override
        public void onComplete(String trxId, String status, String message) {
            Intent notifyIntent = new Intent(ACTION_SMS_PROCESSED);
            notifyIntent.setPackage(appContext.getPackageName());
            notifyIntent.putExtra("trxId", trxId);
            notifyIntent.putExtra("status", status);
            appContext.sendBroadcast(notifyIntent);
        }
    }

    private static class AsyncUploadWorker implements Runnable {
        private final Context appContext;
        private final GatewayStorage storage;
        private final SmsRecord record;
        private final PendingResult pendingResult;
        private final PowerManager.WakeLock wakeLock;

        AsyncUploadWorker(Context ctx, GatewayStorage st, SmsRecord rec, PendingResult pr, PowerManager.WakeLock wl) {
            this.appContext = ctx;
            this.storage = st;
            this.record = rec;
            this.pendingResult = pr;
            this.wakeLock = wl;
        }

        @Override
        public void run() {
            try {
                GatewayHttp.forwardSmsSync(storage, record, new SmsProcessedNotifier(appContext));
            } finally {
                try { if (wakeLock != null && wakeLock.isHeld()) wakeLock.release(); } catch (Throwable ignored) {}
                try { pendingResult.finish(); } catch (Throwable ignored) {}
            }
        }
    }
}
