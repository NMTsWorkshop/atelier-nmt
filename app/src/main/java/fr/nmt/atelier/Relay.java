package fr.nmt.atelier;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/**
 * Relais de l'atelier.
 *
 * Un petit appareil resté à l'atelier (Raspberry Pi) relève les imprimantes
 * et publie leur état sur ntfy.sh. Hors du réseau de l'atelier, l'application
 * lit ce relevé : elle n'a besoin que du HTTPS, donc ça marche en 4G comme
 * sur n'importe quel wifi, sans VPN.
 *
 * Le relevé est rangé par adresse IP de machine, ce qui évite d'avoir à
 * synchroniser des identifiants entre le Pi et le téléphone.
 */
public class Relay {

    private static final String PREFS = "nmt_printers";
    private static final String KEY_SUJET = "relay_topic";

    static String sujet(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_SUJET, "");
    }

    static void setSujet(Context c, String sujet) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(KEY_SUJET, sujet == null ? "" : sujet.trim()).apply();
    }

    static boolean actif(Context c) {
        return sujet(c).length() > 0;
    }

    /**
     * Dernier relevé publié, rangé par adresse IP.
     * Renvoie un objet vide si le relais n'a rien publié récemment.
     */
    static JSONObject dernier(Context c) throws Exception {
        String sujet = sujet(c);
        if (sujet.length() == 0) return new JSONObject();

        String url = "https://ntfy.sh/" + URLEncoder.encode(sujet, "UTF-8")
                + "/json?poll=1&since=2h";
        return machinesDepuis(lire(url));
    }

    /**
     * ntfy renvoie un message JSON par ligne, du plus ancien au plus récent :
     * on garde le dernier qui porte bien un relevé de machines.
     */
    static JSONObject machinesDepuis(String corps) {
        JSONObject dernierMsg = null;
        for (String ligne : String.valueOf(corps).split("\n")) {
            ligne = ligne.trim();
            if (ligne.length() == 0) continue;
            try {
                JSONObject l = new JSONObject(ligne);
                if (!"message".equals(l.optString("event"))) continue;
                JSONObject charge = new JSONObject(l.optString("message", "{}"));
                if (charge.optJSONObject("machines") != null) dernierMsg = charge;
            } catch (Exception ignored) {
            }
        }
        if (dernierMsg == null) return new JSONObject();
        JSONObject machines = dernierMsg.optJSONObject("machines");
        return machines == null ? new JSONObject() : machines;
    }

    /** Vrai si le relevé du relais est plus récent que ce qu'on a déjà. */
    static boolean plusRecent(JSONObject relais, JSONObject local) {
        long a = relais == null ? 0 : relais.optLong("at", 0);
        long b = local == null ? 0 : local.optLong("at", 0);
        return a > b;
    }

    private static String lire(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(8000);
        c.setReadTimeout(12000);
        c.setRequestMethod("GET");
        int code = c.getResponseCode();
        InputStream is = (code >= 200 && code < 400) ? c.getInputStream() : c.getErrorStream();
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while (is != null && (n = is.read(buf)) > 0) bos.write(buf, 0, n);
        if (is != null) is.close();
        c.disconnect();
        if (code < 200 || code >= 300) throw new Exception("HTTP " + code);
        return new String(bos.toByteArray(), "UTF-8");
    }

    /** Test manuel, depuis l'écran des réglages. */
    static JSONObject test(Context c) {
        JSONObject out = new JSONObject();
        try {
            JSONObject m = dernier(c);
            JSONArray noms = new JSONArray();
            long plusRecente = 0;
            int ok = 0;
            for (java.util.Iterator<String> it = m.keys(); it.hasNext(); ) {
                JSONObject e = m.optJSONObject(it.next());
                if (e == null) continue;
                noms.put(e.optString("nom", "?"));
                if (e.optBoolean("ok", false)) ok++;
                plusRecente = Math.max(plusRecente, e.optLong("at", 0));
            }
            out.put("ok", m.length() > 0);
            out.put("machines", noms);
            out.put("joignables", ok);
            out.put("at", plusRecente);
            if (m.length() == 0) out.put("error", "aucun relevé publié sur ce sujet");
        } catch (Throwable t) {
            try {
                out.put("ok", false);
                out.put("error", String.valueOf(t.getMessage()));
            } catch (Exception ignored) {
            }
        }
        return out;
    }
}
