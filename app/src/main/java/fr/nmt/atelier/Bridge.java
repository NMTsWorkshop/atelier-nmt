package fr.nmt.atelier;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.NotificationManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;

/**
 * Pont entre l'interface web et Android.
 * Toutes les méthodes annotées sont appelables depuis le JavaScript via window.NMT.
 */
public class Bridge {

    private final Activity act;
    private final WebView web;

    Bridge(Activity act, WebView web) {
        this.act = act;
        this.web = web;
    }

    /* ---------- timers ---------- */

    @JavascriptInterface
    public void scheduleTimer(String id, String title, String text, double endAt) {
        Timers.schedule(act, id, title, text, (long) endAt);
    }

    @JavascriptInterface
    public void cancelTimer(String id) {
        Timers.cancel(act, id);
    }

    @JavascriptInterface
    public void notifyNow(String title, String text) {
        Timers.schedule(act, "now-" + System.currentTimeMillis(), title, text,
                System.currentTimeMillis() + 1000);
    }

    /* ---------- autorisations ---------- */

    @JavascriptInterface
    public boolean notificationsAllowed() {
        if (Build.VERSION.SDK_INT >= 33) {
            return act.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    == PackageManager.PERMISSION_GRANTED;
        }
        NotificationManager nm =
                (NotificationManager) act.getSystemService(Context.NOTIFICATION_SERVICE);
        return nm == null || nm.areNotificationsEnabled();
    }

    @JavascriptInterface
    public void requestNotifications() {
        if (Build.VERSION.SDK_INT >= 33) {
            act.runOnUiThread(new Runnable() {
                public void run() {
                    act.requestPermissions(
                            new String[]{Manifest.permission.POST_NOTIFICATIONS}, 11);
                }
            });
        } else {
            openAppNotificationSettings();
        }
    }

    @JavascriptInterface
    public boolean exactAlarmsAllowed() {
        if (Build.VERSION.SDK_INT < 31) return true;
        AlarmManager am = (AlarmManager) act.getSystemService(Context.ALARM_SERVICE);
        return am == null || am.canScheduleExactAlarms();
    }

    @JavascriptInterface
    public void openExactAlarmSettings() {
        if (Build.VERSION.SDK_INT < 31) return;
        try {
            Intent i = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                    Uri.parse("package:" + act.getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            act.startActivity(i);
        } catch (Exception e) {
            openAppSettings();
        }
    }

    @JavascriptInterface
    public void openBatterySettings() {
        try {
            Intent i = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            act.startActivity(i);
        } catch (Exception e) {
            openAppSettings();
        }
    }

    private void openAppSettings() {
        try {
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + act.getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            act.startActivity(i);
        } catch (Exception ignored) {
        }
    }

    private void openAppNotificationSettings() {
        try {
            Intent i = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS);
            i.putExtra(Settings.EXTRA_APP_PACKAGE, act.getPackageName());
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            act.startActivity(i);
        } catch (Exception e) {
            openAppSettings();
        }
    }

    /* ---------- requêtes réseau (l'API Shopify n'est pas joignable depuis la WebView) ---------- */

    @JavascriptInterface
    public void httpAsync(final String method, final String url, final String headersJson,
                          final String body, final String cbId) {
        new Thread(new Runnable() {
            public void run() {
                String payload;
                try {
                    payload = doRequest(method, url, headersJson, body);
                } catch (Throwable t) {
                    payload = errorJson(String.valueOf(t.getMessage()));
                }
                final String result = payload;
                web.post(new Runnable() {
                    public void run() {
                        web.evaluateJavascript(
                                "window.NMTcb(" + JSONObject.quote(cbId) + ","
                                        + JSONObject.quote(result) + ")", null);
                    }
                });
            }
        }).start();
    }

    private static String errorJson(String msg) {
        try {
            JSONObject o = new JSONObject();
            o.put("ok", false);
            o.put("status", 0);
            o.put("error", msg);
            return o.toString();
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":\"erreur\"}";
        }
    }

    private static String doRequest(String method, String url, String headersJson, String body)
            throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod(method == null ? "GET" : method.toUpperCase());
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(25000);
        conn.setInstanceFollowRedirects(true);

        if (headersJson != null && headersJson.length() > 2) {
            JSONObject h = new JSONObject(headersJson);
            Iterator<String> it = h.keys();
            while (it.hasNext()) {
                String k = it.next();
                conn.setRequestProperty(k, h.optString(k));
            }
        }

        if (body != null && body.length() > 0 && !"GET".equalsIgnoreCase(method)) {
            conn.setDoOutput(true);
            byte[] out = body.getBytes("UTF-8");
            conn.setFixedLengthStreamingMode(out.length);
            OutputStream os = conn.getOutputStream();
            os.write(out);
            os.flush();
            os.close();
        }

        int status = conn.getResponseCode();
        InputStream is = (status >= 200 && status < 400)
                ? conn.getInputStream() : conn.getErrorStream();
        String text = is == null ? "" : readAll(is);
        conn.disconnect();

        JSONObject res = new JSONObject();
        res.put("ok", status >= 200 && status < 300);
        res.put("status", status);
        res.put("body", text);
        if (status < 200 || status >= 300) {
            res.put("error", "HTTP " + status + (text.length() > 0 ? " — " + trim(text) : ""));
        }
        return res.toString();
    }

    private static String trim(String s) {
        s = s.replaceAll("\\s+", " ").trim();
        return s.length() > 160 ? s.substring(0, 160) + "…" : s;
    }

    private static String readAll(InputStream is) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
        is.close();
        return new String(bos.toByteArray(), "UTF-8");
    }

    /* ---------- mise a jour de l'application ---------- */

    @JavascriptInterface
    public String appVersion() {
        try {
            return act.getPackageManager()
                    .getPackageInfo(act.getPackageName(), 0).versionName;
        } catch (Throwable t) {
            return "?";
        }
    }

    /** Interroge la page Releases et rappelle window.NMTcb avec le resultat. */
    @JavascriptInterface
    public void checkUpdate(final String cbId) {
        new Thread(new Runnable() {
            public void run() {
                final String res = Updater.check(act);
                web.post(new Runnable() {
                    public void run() {
                        web.evaluateJavascript(
                                "window.NMTcb(" + JSONObject.quote(cbId) + ","
                                        + JSONObject.quote(res) + ")", null);
                    }
                });
            }
        }).start();
    }

    /** Telecharge l'APK puis ouvre l'installateur Android. */
    @JavascriptInterface
    public void installUpdate(final String url, final String cbId) {
        new Thread(new Runnable() {
            public void run() {
                final String res = Updater.download(act, url);
                web.post(new Runnable() {
                    public void run() {
                        web.evaluateJavascript(
                                "window.NMTcb(" + JSONObject.quote(cbId) + ","
                                        + JSONObject.quote(res) + ")", null);
                    }
                });
            }
        }).start();
    }

    @JavascriptInterface
    public void openInstallPermission() {
        Updater.openInstallPermission(act);
    }

    /* ---------- presse-papiers ----------
       Le presse-papiers survit à une désinstallation, contrairement aux
       données de l'app : c'est le chemin le plus sûr pour transporter
       une sauvegarde d'une version à l'autre. */

    @JavascriptInterface
    public boolean copyToClipboard(final String text) {
        try {
            android.content.ClipboardManager cm = (android.content.ClipboardManager)
                    act.getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm == null) return false;
            cm.setPrimaryClip(android.content.ClipData.newPlainText("Atelier NMT", text));
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    /* ---------- sauvegarde de fichier ---------- */

    @JavascriptInterface
    public String saveFile(String name, String content) {
        try {
            byte[] data = content.getBytes("UTF-8");
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Downloads.DISPLAY_NAME, name);
                cv.put(MediaStore.Downloads.MIME_TYPE, "application/json");
                cv.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                Uri uri = act.getContentResolver()
                        .insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                if (uri == null) return null;
                OutputStream os = act.getContentResolver().openOutputStream(uri);
                if (os == null) return null;
                os.write(data);
                os.close();
                return "Téléchargements/" + name;
            }
            File dir = act.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS);
            if (dir == null) dir = act.getFilesDir();
            File f = new File(dir, name);
            FileOutputStream fos = new FileOutputStream(f);
            fos.write(data);
            fos.close();
            return f.getAbsolutePath();
        } catch (Throwable t) {
            return null;
        }
    }

    /* ---------- imprimantes du réseau local ---------- */

    /** Enregistre la liste des machines connectées et (dé)clenche la relève. */
    @JavascriptInterface
    public void savePrinters(String json) {
        Printers.saveConfig(act, json == null ? "[]" : json);
        if (Sync.hasPrinters(act)) {
            Sync.schedule(act);
        } else {
            Sync.cancel(act);
        }
    }

    /** Liste des machines connectées, telle qu'enregistrée. */
    @JavascriptInterface
    public String printerConfig() {
        return Printers.config(act).toString();
    }

    /** Dernier état connu de chaque machine, tel que stocké par la relève. */
    @JavascriptInterface
    public String printerStates() {
        return Printers.states(act).toString();
    }

    /** Sujet du relais de l'atelier, tel qu'enregistré. */
    @JavascriptInterface
    public String relayTopic() {
        return Relay.sujet(act);
    }

    /** Enregistre le sujet du relais. */
    @JavascriptInterface
    public void saveRelay(String sujet) {
        Relay.setSujet(act, sujet);
    }

    /** Test du relais depuis l'écran des réglages. */
    @JavascriptInterface
    public void testRelay(final String cbId) {
        new Thread(new Runnable() {
            public void run() {
                callBack(cbId, Relay.test(act).toString());
            }
        }).start();
    }

    /** Relève immédiate de toutes les machines, puis rappel vers le JS. */
    @JavascriptInterface
    public void syncPrinters(final String cbId) {
        new Thread(new Runnable() {
            public void run() {
                try {
                    Sync.runOnce(act, 25);
                } catch (Throwable ignored) {
                }
                callBack(cbId, Printers.states(act).toString());
            }
        }).start();
    }

    /** Test d'une seule machine, pour l'écran de configuration. */
    @JavascriptInterface
    public void probePrinter(final String confJson, final String cbId) {
        new Thread(new Runnable() {
            public void run() {
                String payload;
                try {
                    payload = Printers.poll(new JSONObject(confJson)).toString();
                } catch (Throwable t) {
                    payload = errorJson(String.valueOf(t.getMessage()));
                }
                callBack(cbId, payload);
            }
        }).start();
    }

    private void callBack(final String cbId, final String payload) {
        web.post(new Runnable() {
            public void run() {
                web.evaluateJavascript(
                        "window.NMTcb(" + JSONObject.quote(cbId) + ","
                                + JSONObject.quote(payload) + ")", null);
            }
        });
    }
}
