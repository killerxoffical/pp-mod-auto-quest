package com.vareon.playquest;

import org.json.JSONException;
import org.json.JSONObject;

public class AccountItem {
    private String id;
    private String email;
    private String code;
    private String token;
    private long timestamp;

    public AccountItem(String id, String email, String code, String token, long timestamp) {
        this.id = id;
        this.email = email;
        this.code = code;
        this.token = token;
        this.timestamp = timestamp;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email != null && !email.isEmpty() ? email : "Google Account";
    }

    public String getCode() {
        return code;
    }

    public String getToken() {
        return token;
    }

    public long getTimestamp() {
        return timestamp;
    }

    public JSONObject toJson() {
        JSONObject obj = new JSONObject();
        try {
            obj.put("id", id);
            obj.put("email", email);
            obj.put("code", code);
            obj.put("token", token);
            obj.put("timestamp", timestamp);
        } catch (JSONException ignored) {}
        return obj;
    }

    public static AccountItem fromJson(JSONObject obj) {
        if (obj == null) return null;
        String id = obj.optString("id", "");
        String email = obj.optString("email", "");
        String code = obj.optString("code", "");
        String token = obj.optString("token", "");
        long timestamp = obj.optLong("timestamp", System.currentTimeMillis());
        return new AccountItem(id, email, code, token, timestamp);
    }
}
