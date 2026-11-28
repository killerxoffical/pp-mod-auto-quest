package com.vareon.gateway;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

public class BootReceiver extends BroadcastReceiver {
    public static final String ACTION_RESTART_SERVICE = "com.vareon.gateway.RESTART_SERVICE";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || intent.getAction() == null) {
            return;
        }
        String action = intent.getAction();
        boolean valid = Intent.ACTION_BOOT_COMPLETED.equals(action)
            || Intent.ACTION_LOCKED_BOOT_COMPLETED.equals(action)
            || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)
            || "android.intent.action.QUICKBOOT_POWERON".equals(action)
            || "com.htc.intent.action.QUICKBOOT_POWERON".equals(action)
            || ACTION_RESTART_SERVICE.equals(action);

        if (!valid) {
            return;
        }

        try {
            GatewayStorage storage = new GatewayStorage(context);
            if (storage.isEnabled()) {
                Intent serviceIntent = new Intent(context, GatewayService.class);
                if (Build.VERSION.SDK_INT >= 26) {
                    context.startForegroundService(serviceIntent);
                } else {
                    context.startService(serviceIntent);
                }
            }
        } catch (Throwable ignored) {}
    }
}
