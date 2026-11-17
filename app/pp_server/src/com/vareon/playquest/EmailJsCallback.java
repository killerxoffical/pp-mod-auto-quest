package com.vareon.playquest;

import android.webkit.ValueCallback;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@SuppressWarnings("rawtypes")
public class EmailJsCallback implements ValueCallback {
    private final MainActivity activity;

    public EmailJsCallback(MainActivity activity) {
        this.activity = activity;
    }

    @Override
    public void onReceiveValue(Object obj) {
        if (obj == null) return;
        String value = obj.toString();
        if (value.isEmpty() || "null".equals(value)) return;
        try {
            Pattern pattern = Pattern.compile("[a-zA-Z0-9._%+-]+@gmail\\.com");
            Matcher matcher = pattern.matcher(value);
            if (matcher.find()) {
                activity.setDetectedEmail(matcher.group(0));
            }
        } catch (Exception ignored) {}
    }
}
