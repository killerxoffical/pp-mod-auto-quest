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
    private static final String KEY_ACCOUNTS = "accounts_list_v2";

    private final SharedPreferences prefs;

    public AccountStorage(Context context) {
        this.prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
    }

    public synchronized List<AccountItem> getAccounts() {
        List<AccountItem> list = new ArrayList<AccountItem>();
        String jsonStr = prefs.getString(KEY_ACCOUNTS, "[]");
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

    public synchronized void saveAccount(AccountItem newItem) {
        if (newItem == null) return;
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

    private void saveList(List<AccountItem> list) {
        JSONArray arr = new JSONArray();
        for (AccountItem item : list) {
            arr.put(item.toJson());
        }
        prefs.edit().putString(KEY_ACCOUNTS, arr.toString()).apply();
    }
}
