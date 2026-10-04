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

    /* ---------- la bibliothèque, par le canal ----------

       Le service du relais ne répond que sur le réseau de l'atelier. Pour
       que la bibliothèque soit lisible de n'importe où, le Pi la publie
       sur le même canal que les relevés : compressée, découpée en
       messages, et seulement quand elle change. */

    static JSONObject bibliotheque(Context c) throws Exception {
        String sujet = sujet(c);
        if (sujet.length() == 0) return new JSONObject();
        String url = "https://ntfy.sh/" + URLEncoder.encode(sujet, "UTF-8")
                + "/json?poll=1&since=24h";
        return biblioDepuis(lire(url));
    }

    /**
     * Les morceaux arrivent dans l'ordre mais plusieurs versions peuvent
     * cohabiter sur le canal : on ne garde que la dernière complète.
     */
    static JSONObject biblioDepuis(String corps) throws Exception {
        String derniere = "";
        java.util.HashMap<String, java.util.TreeMap<Integer, String>> paquets =
                new java.util.HashMap<String, java.util.TreeMap<Integer, String>>();
        java.util.HashMap<String, Integer> attendus = new java.util.HashMap<String, Integer>();

        for (String ligne : String.valueOf(corps).split("\n")) {
            ligne = ligne.trim();
            if (ligne.length() == 0) continue;
            try {
                JSONObject l = new JSONObject(ligne);
                if (!"message".equals(l.optString("event"))) continue;
                JSONObject charge = new JSONObject(l.optString("message", "{}"));
                if (!"biblio".equals(charge.optString("t"))) continue;
                String e = charge.optString("e");
                if (e.length() == 0) continue;
                if (!paquets.containsKey(e)) {
                    paquets.put(e, new java.util.TreeMap<Integer, String>());
                    attendus.put(e, charge.optInt("lots", 1));
                }
                paquets.get(e).put(charge.optInt("lot", 1), charge.optString("d"));
                if (paquets.get(e).size() >= attendus.get(e)) derniere = e;
            } catch (Exception ignored) {
            }
        }
        if (derniere.length() == 0) return new JSONObject();

        StringBuilder serre = new StringBuilder();
        for (String m : paquets.get(derniere).values()) serre.append(m);
        byte[] brut = android.util.Base64.decode(serre.toString(), android.util.Base64.DEFAULT);

        java.util.zip.InflaterInputStream in =
                new java.util.zip.InflaterInputStream(new java.io.ByteArrayInputStream(brut));
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] tampon = new byte[8192];
        int n;
        while ((n = in.read(tampon)) > 0) out.write(tampon, 0, n);
        in.close();

        JSONObject index = new JSONObject(new String(out.toByteArray(), "UTF-8"));
        index.put("ok", true);
        index.put("canal", true);        // lu par le canal, pas en direct
        return index;
    }

    /* ---------- les ordres, dans l'autre sens ----------

       Hors de l'atelier, l'app ne peut pas appeler le relais : elle publie
       un ordre sur le canal, et le relais l'applique à sa relève suivante,
       dans la minute. Le sujet ne protège que la lecture, alors un ordre
       porte une signature calculée avec le jeton. */

    private static final String[] CHAMPS_SIGNES = {
            "id", "at", "quoi", "chemin", "plateau", "fait", "n", "commande", "machine"
    };

    static String signer(String jeton, JSONObject ordre) {
        StringBuilder corps = new StringBuilder();
        for (int i = 0; i < CHAMPS_SIGNES.length; i++) {
            if (i > 0) corps.append('\u001f');
            Object v = ordre.opt(CHAMPS_SIGNES[i]);
            if (v == null || v == JSONObject.NULL) continue;
            if (v instanceof Boolean) corps.append(((Boolean) v) ? "1" : "0");
            else corps.append(String.valueOf(v));
        }
        try {
            javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
            mac.init(new javax.crypto.spec.SecretKeySpec(
                    String.valueOf(jeton == null ? "" : jeton).getBytes("UTF-8"), "HmacSHA256"));
            byte[] signature = mac.doFinal(corps.toString().getBytes("UTF-8"));
            StringBuilder hex = new StringBuilder();
            for (byte b : signature) hex.append(String.format("%02x", b));
            return hex.substring(0, 32);
        } catch (Exception e) {
            return "";
        }
    }

    /** Publie un ordre signé. L'appelant fournit « quoi » et ses champs. */
    static void ordre(Context c, JSONObject ordre, String jeton) throws Exception {
        ordre.put("t", "ordre");
        ordre.put("id", Long.toString(System.currentTimeMillis(), 36)
                + Integer.toString((int) (Math.random() * 46655), 36));
        ordre.put("at", System.currentTimeMillis());
        ordre.put("sig", signer(jeton, ordre));
        publier(c, ordre.toString());
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

    /**
     * Publie un message sur le canal du relais.
     *
     * Sert à la compta : l'application envoie ses commandes, un petit script
     * resté sur le PC les récupère et remplit le tableur. Le canal est le même
     * que celui des relevés d'imprimantes — les deux ne se gênent pas, chaque
     * lecteur ne garde que ce qui le concerne.
     */
    static void publier(Context c, String corps) throws Exception {
        String sujet = sujet(c);
        if (sujet.length() == 0) throw new Exception("aucun sujet de relais enregistré");

        HttpURLConnection h = (HttpURLConnection) new URL(
                "https://ntfy.sh/" + URLEncoder.encode(sujet, "UTF-8")).openConnection();
        h.setConnectTimeout(8000);
        h.setReadTimeout(12000);
        h.setRequestMethod("POST");
        h.setDoOutput(true);
        h.setRequestProperty("Content-Type", "text/plain; charset=utf-8");
        h.setRequestProperty("Priority", "min");
        h.setRequestProperty("Title", "compta");
        byte[] b = corps.getBytes("UTF-8");
        h.setFixedLengthStreamingMode(b.length);
        h.getOutputStream().write(b);
        h.getOutputStream().close();
        int code = h.getResponseCode();
        h.disconnect();
        if (code < 200 || code >= 300) throw new Exception("HTTP " + code);
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
