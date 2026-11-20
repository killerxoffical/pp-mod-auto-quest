package com.vareon.playquest;

import org.json.JSONException;
import org.json.JSONObject;

public class AccountItem {
    private String id;
    private String email;
    private String code;
    private String token;
    private String country;
    private long timestamp;

    // Real Account State & Balance
    private String balance = "$0.00";
    private int points = 0;
    private boolean hasPerk = true;
    private String lastClaimDate = "";
    private int claimedPoints = 0;
    private boolean isRevoked = false;

    // Strict Account Ownership Isolation
    private String ownerUid = "";
    private String ownerEmail = "";

    public AccountItem(String id, String email, String code, String token, String country, long timestamp) {
        this.id = id;
        this.email = email;
        this.code = code;
        this.token = token;
        this.country = (country != null && !country.isEmpty()) ? country : "GLOBAL";
        this.timestamp = timestamp;
    }

    public AccountItem(String id, String email, String code, String token, String country, String ownerUid, String ownerEmail, long timestamp) {
        this(id, email, code, token, country, timestamp);
        this.ownerUid = (ownerUid != null) ? ownerUid : "";
        this.ownerEmail = (ownerEmail != null) ? ownerEmail : "";
    }

    public AccountItem(String id, String email, String code, String token, long timestamp) {
        this(id, email, code, token, "GLOBAL", timestamp);
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

    public void setCode(String code) {
        this.code = code;
    }

    public String getToken() {
        return token;
    }

    public void setToken(String token) {
        this.token = token;
    }

    public String getMasterToken() {
        return token;
    }

    public String getCountry() {
        return country != null ? country : "GLOBAL";
    }

    public void setCountry(String country) {
        this.country = country;
    }

    public long getTimestamp() {
        return timestamp;
    }

    public String getBalance() {
        return balance != null && !balance.isEmpty() ? balance : "$0.00";
    }

    public void setBalance(String balance) {
        this.balance = balance;
    }

    public int getPoints() {
        return points;
    }

    public void setPoints(int points) {
        this.points = points;
    }

    public boolean hasPerk() {
        return hasPerk;
    }

    public void setHasPerk(boolean hasPerk) {
        this.hasPerk = hasPerk;
    }

    public String getLastClaimDate() {
        return lastClaimDate != null ? lastClaimDate : "";
    }

    public void setLastClaimDate(String lastClaimDate) {
        this.lastClaimDate = lastClaimDate;
    }

    public int getClaimedPoints() {
        return claimedPoints;
    }

    public void setClaimedPoints(int claimedPoints) {
        this.claimedPoints = claimedPoints;
    }

    public boolean isRevoked() {
        return isRevoked;
    }

    public void setRevoked(boolean revoked) {
        isRevoked = revoked;
    }

    public String getOwnerUid() {
        return ownerUid != null ? ownerUid : "";
    }

    public void setOwnerUid(String ownerUid) {
        this.ownerUid = ownerUid;
    }

    public String getOwnerEmail() {
        return ownerEmail != null ? ownerEmail : "";
    }

    public void setOwnerEmail(String ownerEmail) {
        this.ownerEmail = ownerEmail;
    }

    public JSONObject toJson() {
        JSONObject obj = new JSONObject();
        try {
            obj.put("id", id);
            obj.put("email", email);
            obj.put("code", code);
            obj.put("token", token);
            obj.put("country", country);
            obj.put("timestamp", timestamp);
            obj.put("balance", balance);
            obj.put("points", points);
            obj.put("has_perk", hasPerk);
            obj.put("last_claim_date", lastClaimDate);
            obj.put("claimed_points", claimedPoints);
            obj.put("is_revoked", isRevoked);
            obj.put("owner_uid", ownerUid);
            obj.put("owner_email", ownerEmail);
        } catch (JSONException ignored) {
        }
        return obj;
    }

    public static AccountItem fromJson(JSONObject obj) {
        if (obj == null)
            return null;
        String id = obj.optString("id", "");
        String email = obj.optString("email", "");
        String code = obj.optString("code", "");
        String token = obj.optString("token", "");
        String country = obj.optString("country", "GLOBAL");
        long timestamp = obj.optLong("timestamp", System.currentTimeMillis());
        
        AccountItem item = new AccountItem(id, email, code, token, country, timestamp);
        item.setBalance(obj.optString("balance", "$0.00"));
        item.setPoints(obj.optInt("points", 0));
        item.setHasPerk(obj.optBoolean("has_perk", true));
        item.setLastClaimDate(obj.optString("last_claim_date", ""));
        item.setClaimedPoints(obj.optInt("claimed_points", 0));
        item.setRevoked(obj.optBoolean("is_revoked", false));
        item.setOwnerUid(obj.optString("owner_uid", obj.optString("uid", "")));
        item.setOwnerEmail(obj.optString("owner_email", ""));
        return item;
    }
}
