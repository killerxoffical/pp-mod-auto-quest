package com.vareon.playquest;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class AccountStorage {
    private static final String PREF_NAME = "pp_server_accounts_pref";
    private static final String KEY_ACCOUNTS = "accounts_list_v3";

    // PP Mod User Session Keys
    private static final String KEY_IS_LOGGED_IN = "is_logged_in";
    private static final String KEY_USER_UID = "user_uid";
    private static final String KEY_USER_EMAIL = "user_email";
    private static final String KEY_USER_NAME = "user_name";
    private static final String KEY_USER_AVATAR = "user_avatar";
    private static final String KEY_USER_COINS = "user_coins";
    private static final String KEY_USER_AUTH_TOKEN = "user_auth_token";

    private final SharedPreferences prefs;

    public AccountStorage(Context context) {
        this.prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
    }

    // ================= USER SESSION MANAGEMENT =================
    public boolean isLoggedIn() {
        return prefs.getBoolean(KEY_IS_LOGGED_IN, false);
    }

    public void saveUserSession(String uid, String email, String name, String avatar, int coins, String token) {
        prefs.edit()
            .putBoolean(KEY_IS_LOGGED_IN, true)
            .putString(KEY_USER_UID, uid)
            .putString(KEY_USER_EMAIL, email)
            .putString(KEY_USER_NAME, name)
            .putString(KEY_USER_AVATAR, avatar != null ? avatar : "")
            .putInt(KEY_USER_COINS, coins)
            .putString(KEY_USER_AUTH_TOKEN, token)
            .apply();
    }

    public void saveUserSession(String uid, String email, String name, int coins, String token) {
        saveUserSession(uid, email, name, "", coins, token);
    }

    public void updateUserCoins(int coins) {
        prefs.edit().putInt(KEY_USER_COINS, coins).apply();
    }

    public String getUserUid() {
        return prefs.getString(KEY_USER_UID, "");
    }

    public String getUserEmail() {
        return prefs.getString(KEY_USER_EMAIL, "");
    }

    public String getUserName() {
        return prefs.getString(KEY_USER_NAME, "PP User");
    }

    public String getUserAvatar() {
        return prefs.getString(KEY_USER_AVATAR, "");
    }

    public String getUserDisplayName() {
        return getUserName();
    }

    public int getUserCoins() {
        return prefs.getInt(KEY_USER_COINS, 0);
    }

    public String getUserAuthToken() {
        return prefs.getString(KEY_USER_AUTH_TOKEN, "");
    }

    public String getAccountsStorageKey() {
        String uid = getUserUid();
        if (uid != null && !uid.trim().isEmpty()) {
            return KEY_ACCOUNTS + "_" + uid.trim();
        }
        String email = getUserEmail();
        if (email != null && !email.trim().isEmpty()) {
            return KEY_ACCOUNTS + "_" + email.trim().toLowerCase().replaceAll("[^a-zA-Z0-9]", "_");
        }
        return KEY_ACCOUNTS + "_guest";
    }

    public void clearUserSession() {
        String accKey = getAccountsStorageKey();
        prefs.edit()
            .putBoolean(KEY_IS_LOGGED_IN, false)
            .remove(KEY_USER_UID)
            .remove(KEY_USER_EMAIL)
            .remove(KEY_USER_NAME)
            .remove(KEY_USER_AVATAR)
            .remove(KEY_USER_COINS)
            .remove(KEY_USER_AUTH_TOKEN)
            .remove(accKey)
            .apply();
    }

    public synchronized void clearAccounts() {
        prefs.edit().remove(getAccountsStorageKey()).apply();
    }

    // ================= CONNECTED ACCOUNTS =================
    public synchronized List<AccountItem> getAccounts() {
        List<AccountItem> list = new ArrayList<AccountItem>();
        String jsonStr = prefs.getString(getAccountsStorageKey(), "[]");
        try {
            JSONArray arr = new JSONArray(jsonStr);
            for (int i = 0; i < arr.length(); i++) {
                JSONObject obj = arr.getJSONObject(i);
                AccountItem item = AccountItem.fromJson(obj);
                if (item != null) {
                    list.add(item);
                }
            }
        } catch (JSONException ignored) {}
        return list;
    }

    public synchronized List<AccountItem> getAccountsFiltered(String countryFilter, String searchQuery) {
        List<AccountItem> all = getAccounts();
        List<AccountItem> filtered = new ArrayList<AccountItem>();

        String q = (searchQuery != null) ? searchQuery.toLowerCase().trim() : "";
        boolean filterCountry = (countryFilter != null && !countryFilter.equalsIgnoreCase("ALL") && !countryFilter.equalsIgnoreCase("GLOBAL"));

        for (AccountItem item : all) {
            // Country filter
            if (filterCountry && !item.getCountry().equalsIgnoreCase(countryFilter)) {
                continue;
            }

            // Search query filter (matches email or code)
            if (!q.isEmpty()) {
                String em = item.getEmail().toLowerCase();
                String cd = item.getCode().toLowerCase();
                if (!em.contains(q) && !cd.contains(q)) {
                    continue;
                }
            }

            filtered.add(item);
        }
        return filtered;
    }

    public synchronized void saveAccount(AccountItem newItem) {
        if (newItem == null) return;
        if (newItem.getOwnerUid().isEmpty()) {
            newItem.setOwnerUid(getUserUid());
        }
        if (newItem.getOwnerEmail().isEmpty()) {
            newItem.setOwnerEmail(getUserEmail());
        }
        List<AccountItem> current = getAccounts();
        List<AccountItem> updated = new ArrayList<AccountItem>();
        
        // Add new item at top
        updated.add(newItem);

        // Keep others (avoid duplicate by email or code)
        for (AccountItem item : current) {
            boolean sameEmail = item.getEmail().equalsIgnoreCase(newItem.getEmail()) && !newItem.getEmail().isEmpty();
            boolean sameCode = item.getCode().equals(newItem.getCode());
            if (!sameEmail && !sameCode) {
                updated.add(item);
            }
        }

        saveList(updated);
    }

    public synchronized void deleteAccount(String code) {
        if (code == null) return;
        List<AccountItem> current = getAccounts();
        List<AccountItem> updated = new ArrayList<AccountItem>();
        for (AccountItem item : current) {
            if (!code.equals(item.getCode())) {
                updated.add(item);
            }
        }
        saveList(updated);
    }

    public synchronized void replaceAllAccounts(List<AccountItem> list) {
        if (list == null) list = new ArrayList<AccountItem>();
        saveList(list);
    }

    public synchronized void saveAccounts(List<AccountItem> list) {
        replaceAllAccounts(list);
    }

    private void saveList(List<AccountItem> list) {
        JSONArray arr = new JSONArray();
        for (AccountItem item : list) {
            arr.put(item.toJson());
        }
        prefs.edit().putString(getAccountsStorageKey(), arr.toString()).apply();
    }
}
