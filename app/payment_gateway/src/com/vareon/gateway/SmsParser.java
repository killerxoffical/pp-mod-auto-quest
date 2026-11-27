package com.vareon.gateway;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Precision Bangladesh MFS Incoming Payment SMS Parser (v2.0).
 * Supports bKash, Nagad, Rocket, and Upay (English + Bangla digits).
 * Strictly captures ONLY incoming money-received SMS and rejects all outgoing/OTP/promo SMS.
 */
public class SmsParser {

    private static final String[] OUTGOING_OR_NON_DEPOSIT = new String[] {
        "you have sent",
        "send money to",
        "cash out",
        "cash-out",
        "mobile recharge",
        "recharge of",
        "bill pay",
        "payment of tk",
        "payment to ",
        "add money failed",
        "verification code",
        "one time password",
        "your otp",
        "otp is",
        "do not share",
        "pin reset",
        "আপনি পাঠিয়েছেন",
        "পাঠানো হয়েছে",
        "ক্যাশ আউট",
        "রিচার্জ"
    };

    private static final String[] INCOMING_KEYWORDS = new String[] {
        "you have received",
        "money received",
        "received tk",
        "received bdt",
        "received from",
        "cash in",
        "cash-in",
        "cashin",
        "credited",
        "deposited",
        "payment received",
        "পেয়েছেন",
        "ক্যাশ ইন",
        "রিসিভ"
    };

    public static String normalizeDigits(String input) {
        if (input == null) return "";
        char[] bangla = new char[] { '০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯' };
        StringBuilder sb = new StringBuilder(input.length());
        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);
            boolean replaced = false;
            for (int d = 0; d < bangla.length; d++) {
                if (c == bangla[d]) {
                    sb.append((char) ('0' + d));
                    replaced = true;
                    break;
                }
            }
            if (!replaced) sb.append(c);
        }
        return sb.toString();
    }

    public static SmsRecord parse(String sender, String rawMessage, long timestamp) {
        if (rawMessage == null || rawMessage.trim().isEmpty()) {
            return null;
        }

        String text = normalizeDigits(rawMessage).replace("\r", " ").replace("\n", " ").replaceAll("\\s+", " ").trim();
        String lowerSender = sender != null ? sender.toLowerCase(Locale.US) : "";
        String lowerText = text.toLowerCase(Locale.US);

        // 1. Strict Incoming-Only Guard: reject outgoing Cash Out / Send Money / Recharge / OTP SMS
        boolean hasIncoming = false;
        for (String kw : INCOMING_KEYWORDS) {
            if (lowerText.contains(kw)) {
                hasIncoming = true;
                break;
            }
        }
        for (String bad : OUTGOING_OR_NON_DEPOSIT) {
            if (lowerText.contains(bad) && !hasIncoming) {
                return null;
            }
        }
        // Must explicitly indicate an incoming payment/credit
        if (!hasIncoming) {
            return null;
        }

        // 2. Determine Payment Method (bKash / Nagad / Rocket / Upay)
        String method = "bKash";
        if (lowerSender.contains("rocket") || lowerSender.contains("16216") || lowerSender.contains("dbbl")
                || lowerSender.contains("nexus") || lowerSender.contains("dutch-bangla")
                || lowerText.contains("nexuspay") || lowerText.contains("rocket") || lowerText.contains("রকেট")
                || lowerText.contains("dbbl") || lowerText.contains("16216") || lowerText.contains("dutch-bangla")
                || lowerText.contains("a/c:***") || lowerText.contains("a/c:")) {
            method = "Rocket";
        } else if (lowerSender.contains("nagad") || lowerSender.contains("16167") || lowerSender.contains("nagad-bd")
                || lowerText.contains("nagad") || lowerText.contains("নগদ")
                || (lowerText.contains("money received") && lowerText.contains("txnid"))) {
            method = "Nagad";
        } else if (lowerSender.contains("upay") || lowerSender.contains("16268") || lowerSender.contains("ucb")
                || lowerText.contains("upay") || lowerText.contains("উপায়") || lowerText.contains("উপায়")
                || lowerText.contains("16268") || lowerText.contains("ucb")) {
            method = "Upay";
        } else if (lowerSender.contains("bkash") || lowerSender.contains("16247")
                || lowerText.contains("bkash") || lowerText.contains("বিকাশ") || lowerText.contains("16247")
                || lowerText.contains("trxid")) {
            method = "bKash";
        }

        // 3. Parse TrxID / TxnID accurately
        String trxId = null;
        Pattern trxPattern = Pattern.compile(
            "(?:TrxID|TxnID|TxnId|Txn_ID|Transaction\\s*ID|Txn\\s*ID|Txn|আইডি)[:\\s#-]*([A-Za-z0-9]{7,16})",
            Pattern.CASE_INSENSITIVE
        );
        Matcher trxMatcher = trxPattern.matcher(text);
        if (trxMatcher.find()) {
            trxId = trxMatcher.group(1).trim().toUpperCase(Locale.US);
        }

        if (trxId == null || trxId.length() < 7) {
            return null;
        }

        // Refine method from TrxID structure if sender was generic
        if ("bKash".equals(method) && !lowerSender.contains("bkash") && !lowerText.contains("bkash") && !lowerText.contains("trxid")) {
            if (trxId.matches("^\\d{9,12}$")) {
                method = "Rocket";
            } else if (trxId.length() == 8 && lowerText.contains("txnid")) {
                method = "Nagad";
            }
        }

        // 4. Parse Received Amount accurately (ignoring Fee: Tk 0.00 & Balance: Tk ...)
        // Strip Balance & Fee segments first so we never accidentally read Fee or Balance as payment amount!
        String amountSearchText = text
            .replaceAll("(?i)(?:Current\\s*)?(?:Balance|ব্যালেন্স)[:\\s]*(?:Tk\\.?|BDT|টাকা)?\\s*[\\d,]+(?:\\.\\d+)?", " ")
            .replaceAll("(?i)(?:Fee|Charge|Comm)[:\\s]*(?:Tk\\.?|BDT|টাকা)?\\s*[\\d,]+(?:\\.\\d+)?", " ");

        double amount = 0.0;
        Pattern[] amtPatterns = new Pattern[] {
            // "Amount: Tk 500.00" or "Amount: 500.00" (Nagad/Upay)
            Pattern.compile("(?:Amount|Received|Cash[\\s-]*In|Credited|Deposited)[:\\s]*(?:Tk\\.?|BDT|টাকা)?\\s*([\\d,]+(?:\\.\\d+)?)", Pattern.CASE_INSENSITIVE),
            // "Tk 500.00" / "Tk. 500.00" / "Tk500.00" / "BDT 500"
            Pattern.compile("(?:Tk\\.?|BDT|টাকা)\\s*([\\d,]+(?:\\.\\d+)?)", Pattern.CASE_INSENSITIVE),
            // "500.00 Tk" / "500 টাকা"
            Pattern.compile("([\\d,]+(?:\\.\\d+)?)\\s*(?:Tk\\.?|BDT|টাকা)", Pattern.CASE_INSENSITIVE)
        };

        for (Pattern p : amtPatterns) {
            Matcher m = p.matcher(amountSearchText);
            if (m.find()) {
                try {
                    double parsed = Double.parseDouble(m.group(1).replace(",", ""));
                    if (parsed > 0.0) {
                        amount = parsed;
                        break;
                    }
                } catch (Exception ignored) {}
            }
        }

        if (amount <= 0.0) {
            return null;
        }

        // 5. Parse Merchant Remaining Balance (optional, for display)
        double balance = 0.0;
        Pattern balPattern = Pattern.compile("(?:Current\\s*)?(?:Balance|ব্যালেন্স)[:\\s]*(?:Tk\\.?|BDT|টাকা)?\\s*([\\d,]+(?:\\.\\d+)?)", Pattern.CASE_INSENSITIVE);
        Matcher balMatcher = balPattern.matcher(text);
        if (balMatcher.find()) {
            try {
                balance = Double.parseDouble(balMatcher.group(1).replace(",", ""));
            } catch (Exception ignored) {}
        }

        // 6. Parse Customer Phone / Account (optional)
        String senderPhone = "";
        Pattern phonePattern = Pattern.compile("(?:from|Sender)[:\\s]*(01[3-9]\\d{8})", Pattern.CASE_INSENSITIVE);
        Matcher phoneMatcher = phonePattern.matcher(text);
        if (phoneMatcher.find()) {
            senderPhone = phoneMatcher.group(1);
        } else {
            Pattern acPattern = Pattern.compile("(?:A/C:?\\s*\\*{0,3}(\\d{3,11}))", Pattern.CASE_INSENSITIVE);
            Matcher acMatcher = acPattern.matcher(text);
            if (acMatcher.find()) {
                senderPhone = "A/C:***" + acMatcher.group(1);
            }
        }

        String recordId = "TX-" + trxId;
        return new SmsRecord(recordId, sender != null ? sender : method, method, trxId, amount, balance, senderPhone, rawMessage, timestamp, "PENDING");
    }
}
