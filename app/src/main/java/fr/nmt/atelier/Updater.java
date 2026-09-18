package fr.nmt.atelier;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Mise à jour depuis la page Releases du dépôt public.
 *
 * L'app interroge l'API GitHub sans authentification, compare la version
 * publiée à la sienne, télécharge l'APK et lance l'installateur Android.
 * Aucune manipulation de fichier côté utilisateur.
 */
public class Updater {

    private static final String RELEASE_API =
            "https://api.github.com/repos/NMTsWorkshop/atelier-nmt/releases/latest";

    /** Renvoie un JSON : {available, version, current, url, notes} */
    static String check(Activity act) {
        JSONObject out = new JSONObject();
        try {
            String current = act.getPackageManager()
                    .getPackageInfo(act.getPackageName(), 0).versionName;
            out.put("current", current);

            String body = get(RELEASE_API);
            JSONObject rel = new JSONObject(body);

            String tag = rel.optString("tag_name", "");
            String name = rel.optString("name", "");
            String version = extractVersion(name);
            if (version.length() == 0) version = extractVersion(tag);

            String url = "";
            JSONArray assets = rel.optJSONArray("assets");
            if (assets != null) {
                for (int i = 0; i < assets.length(); i++) {
                    JSONObject a = assets.getJSONObject(i);
                    if (a.optString("name", "").endsWith(".apk")) {
                        url = a.optString("browser_download_url", "");
                        break;
                    }
                }
            }

            out.put("version", version);
            out.put("url", url);
            out.put("notes", rel.optString("body", ""));
            out.put("available", url.length() > 0 && isNewer(version, current));
            out.put("ok", true);
        } catch (Throwable t) {
            try {
                out.put("ok", false);
                out.put("error", String.valueOf(t.getMessage()));
            } catch (Exception ignored) {
            }
        }
        return out.toString();
    }

    /** « Atelier NMT 1.2 » ou « v1.2 » → « 1.2 » */
    private static String extractVersion(String s) {
        if (s == null) return "";
        StringBuilder b = new StringBuilder();
        boolean started = false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c >= '0' && c <= '9') { b.append(c); started = true; }
            else if (c == '.' && started) { b.append(c); }
            else if (started) { break; }
        }
        return b.toString();
    }

    /** Compare « 1.10 » et « 1.9 » correctement, segment par segment. */
    static boolean isNewer(String candidate, String current) {
        if (candidate == null || candidate.length() == 0) return false;
        String[] a = candidate.split("\\.");
        String[] b = current == null ? new String[0] : current.split("\\.");
        int n = Math.max(a.length, b.length);
        for (int i = 0; i < n; i++) {
            int x = i < a.length ? parse(a[i]) : 0;
            int y = i < b.length ? parse(b[i]) : 0;
            if (x != y) return x > y;
        }
        return false;
    }

    private static int parse(String s) {
        try { return Integer.parseInt(s.trim()); } catch (Exception e) { return 0; }
    }

    /** Télécharge l'APK puis ouvre l'installateur. Renvoie un JSON. */
    static String download(Activity act, String url) {
        JSONObject out = new JSONObject();
        try {
            if (Build.VERSION.SDK_INT >= 26 && !act.getPackageManager().canRequestPackageInstalls()) {
                out.put("ok", false);
                out.put("needPermission", true);
                out.put("error", "autorisation d'installation requise");
                return out.toString();
            }

            File dir = new File(act.getCacheDir(), "maj");
            if (!dir.exists()) dir.mkdirs();
            File apk = new File(dir, "atelier-nmt.apk");

            HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setConnectTimeout(20000);
            conn.setReadTimeout(120000);
            conn.setInstanceFollowRedirects(true);
            InputStream is = conn.getInputStream();
            FileOutputStream fos = new FileOutputStream(apk);
            byte[] buf = new byte[16384];
            int n;
            long total = 0;
            while ((n = is.read(buf)) > 0) { fos.write(buf, 0, n); total += n; }
            fos.close();
            is.close();
            conn.disconnect();

            if (total < 10000) throw new Exception("téléchargement incomplet");

            Uri uri = FileProvider.getUriForFile(
                    act, act.getPackageName() + ".fileprovider", apk);

            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(uri, "application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            act.startActivity(i);

            out.put("ok", true);
            out.put("bytes", total);
        } catch (Throwable t) {
            try {
                out.put("ok", false);
                out.put("error", String.valueOf(t.getMessage()));
            } catch (Exception ignored) {
            }
        }
        return out.toString();
    }

    /** Ouvre l'écran Android « Installer des applications inconnues » pour cette app. */
    static void openInstallPermission(Activity act) {
        try {
            if (Build.VERSION.SDK_INT >= 26) {
                Intent i = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + act.getPackageName()));
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                act.startActivity(i);
            }
        } catch (Exception ignored) {
        }
    }

    private static String get(String url) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(20000);
        conn.setRequestProperty("Accept", "application/vnd.github+json");
        conn.setRequestProperty("User-Agent", "AtelierNMT");
        InputStream is = conn.getResponseCode() < 400
                ? conn.getInputStream() : conn.getErrorStream();
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
        is.close();
        conn.disconnect();
        return new String(bos.toByteArray(), "UTF-8");
    }
}
