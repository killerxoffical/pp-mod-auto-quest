package com.vareon.gateway;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SmsParser {

    public static SmsRecord parse(String sender, String rawMessage, long timestamp) {
        if (rawMessage == null || rawMessage.trim().isEmpty()) {
            return null;
        }

        String text = rawMessage.replace("\n", " ");
        String lowerSender = sender != null ? sender.toLowerCase() : "";
        String lowerText = text.toLowerCase();

        // 1. Determine Payment Method
        String method = "bKash";
        if (lowerSender.contains("nagad") || lowerText.contains("nagad")) {
            method = "Nagad";
        } else if (lowerSender.contains("rocket") || lowerSender.contains("16216") || lowerText.contains("rocket")) {
            method = "Rocket";
        } else if (lowerSender.contains("upay") || lowerText.contains("upay")) {
            method = "Upay";
        } else if (lowerSender.contains("bkash") || lowerText.contains("bkash")) {
            method = "bKash";
        }

        // 2. Parse TrxID / TxnID
        String trxId = null;
        Pattern trxPattern = Pattern.compile("(?:TrxID|TxnID|Txn|ID|Ref|আইডি)[:\\s]*([A-Za-z0-9]{7,14})", Pattern.CASE_INSENSITIVE);
        Matcher trxMatcher = trxPattern.matcher(text);
        if (trxMatcher.find()) {
            trxId = trxMatcher.group(1).trim().toUpperCase();
        } else {
            // Backup word match (8-12 alphanumeric characters)
            Pattern rawTrxPattern = Pattern.compile("\\b([A-Z0-9]{8,12})\\b");
            Matcher rawMatcher = rawTrxPattern.matcher(text);
            while (rawMatcher.find()) {
                String candidate = rawMatcher.group(1).toUpperCase();
                // Filter out common false positives
                if (!candidate.equals("SUCCESS") && !candidate.equals("PAYMENT") && !candidate.equals("BALANCE")) {
                    trxId = candidate;
                    break;
                }
            }
        }

        if (trxId == null || trxId.length() < 7) {
            return null; // Not a payment notification SMS
        }

        // 3. Parse Amount
        double amount = 0.0;
        Pattern amtPattern = Pattern.compile("(?:Tk|Amount|received|টাকা|BDT)[:\\s]*([\\d,]+(?:\\.\\d+)?)", Pattern.CASE_INSENSITIVE);
        Matcher amtMatcher = amtPattern.matcher(text);
        if (amtMatcher.find()) {
            try {
                amount = Double.parseDouble(amtMatcher.group(1).replace(",", ""));
            } catch (Exception ignored) {}
        } else {
            Pattern amtAltPattern = Pattern.compile("([\\d,]+(?:\\.\\d+)?)\\s*(?:Tk|টাকা|BDT)", Pattern.CASE_INSENSITIVE);
            Matcher altMatcher = amtAltPattern.matcher(text);
            if (altMatcher.find()) {
                try {
                    amount = Double.parseDouble(altMatcher.group(1).replace(",", ""));
                } catch (Exception ignored) {}
            }
        }

        if (amount <= 0.0) {
            return null; // Missing or zero amount
        }

        // 4. Parse Merchant Remaining Balance
        double balance = 0.0;
        Pattern balPattern = Pattern.compile("(?:Balance|ব্যালেন্স|Current Balance)[:\\s]*(?:Tk|টাকা|BDT)?\\s*([\\d,]+(?:\\.\\d+)?)", Pattern.CASE_INSENSITIVE);
        Matcher balMatcher = balPattern.matcher(text);
        if (balMatcher.find()) {
            try {
                balance = Double.parseDouble(balMatcher.group(1).replace(",", ""));
            } catch (Exception ignored) {}
        }

        // 5. Parse Customer Phone Number (if present)
        String senderPhone = "";
        Pattern phonePattern = Pattern.compile("(?:from|Sender)[:\\s]*(01[3-9]\\d{8})", Pattern.CASE_INSENSITIVE);
        Matcher phoneMatcher = phonePattern.matcher(text);
        if (phoneMatcher.find()) {
            senderPhone = phoneMatcher.group(1);
        }

        String recordId = "TX-" + System.currentTimeMillis();
        return new SmsRecord(recordId, sender != null ? sender : "Payment", method, trxId, amount, balance, senderPhone, rawMessage, timestamp, "PENDING");
    }
}
