package fr.nmt.atelier;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/**
 * Lecture directe des imprimantes sur le réseau local.
 *
 * Creality (K2, K1…) : Klipper expose Moonraker en HTTP, aucune authentification.
 * Bambu : la machine publie son état en MQTT sur le port 8883, avec le code
 * d'accès LAN — et cela fonctionne sans couper le cloud, vérifié sur P1S.
 */
public class Printers {

    private static final String PREFS = "nmt_printers";
    private static final String KEY_CONF = "conf";
    private static final String KEY_STATE = "state";

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    /* ---------- configuration, écrite depuis l'interface ---------- */

    static JSONArray config(Context c) {
        try {
            return new JSONArray(prefs(c).getString(KEY_CONF, "[]"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    static void saveConfig(Context c, String json) {
        prefs(c).edit().putString(KEY_CONF, json).apply();
    }

    /* ---------- dernier état connu, lu par l'interface ---------- */

    static JSONObject states(Context c) {
        try {
            return new JSONObject(prefs(c).getString(KEY_STATE, "{}"));
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    static void putState(Context c, String machineId, JSONObject st) {
        try {
            JSONObject all = states(c);
            st.put("at", System.currentTimeMillis());
            all.put(machineId, st);
            prefs(c).edit().putString(KEY_STATE, all.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    /**
     * Enregistre le résultat d'une relève. Un échec (hors du wifi de
     * l'atelier, machine éteinte) n'efface pas le dernier bon relevé : on le
     * garde tel quel, avec l'heure où il a été pris, et on note seulement
     * que la machine ne répond plus. L'interface continue d'afficher
     * l'impression et d'en estimer la fin à partir de ce relevé.
     */
    static void record(Context c, String machineId, JSONObject st) {
        if (st.optBoolean("ok", false)) {
            putState(c, machineId, st);
            return;
        }
        try {
            JSONObject all = states(c);
            JSONObject prev = all.optJSONObject(machineId);
            if (prev != null && prev.optBoolean("ok", false)) {
                prev.put("stale", true);
                prev.put("staleError", st.optString("error", ""));
                prev.put("staleReglage", st.optBoolean("reglage", false));
                prev.put("staleAt", System.currentTimeMillis());
                all.put(machineId, prev);
                prefs(c).edit().putString(KEY_STATE, all.toString()).apply();
                return;
            }
        } catch (Exception ignored) {
        }
        putState(c, machineId, st);
    }

    /* ---------- interrogation d'une machine ---------- */

    /**
     * Renvoie un état normalisé, quelle que soit la marque :
     * { ok, kind, state, file, percent, remaining (min), nozzle, bed, ams:[{slot,type,color}] }
     */
    static JSONObject poll(JSONObject conf) {
        JSONObject out = new JSONObject();
        String kind = conf.optString("kind");
        try {
            out.put("kind", kind);
            String manque = manquant(conf, kind);
            if (manque != null) {
                out.put("ok", false);
                out.put("reglage", true);
                out.put("error", manque);
                return out;
            }
            if ("moonraker".equals(kind)) {
                pollMoonraker(conf, out);
            } else if ("bambu".equals(kind)) {
                pollBambu(conf, out);
            } else {
                out.put("ok", false);
                out.put("error", "type inconnu");
                return out;
            }
            out.put("ok", true);
        } catch (Throwable t) {
            try {
                out.put("ok", false);
                out.put("error", lisible(t, conf.optString("host", "")));
            } catch (Exception ignored) {
            }
        }
        return out;
    }

    /**
     * Ce qui manque dans la fiche, avant même d'essayer le réseau : mieux vaut
     * dire « il manque le code » que « injoignable ».
     */
    private static String manquant(JSONObject conf, String kind) {
        if (conf.optString("host", "").trim().length() == 0) {
            return "adresse IP à renseigner dans la fiche machine";
        }
        if ("bambu".equals(kind)) {
            if (conf.optString("serial", "").trim().length() == 0) {
                return "numéro de série à renseigner dans la fiche machine";
            }
            if (conf.optString("code", "").trim().length() == 0) {
                return "code d'accès LAN à saisir dans la fiche machine";
            }
        }
        return null;
    }

    private static String short_(String s) {
        if (s == null) return "erreur";
        s = s.replaceAll("\\s+", " ").trim();
        return s.length() > 120 ? s.substring(0, 120) + "…" : s;
    }

    /**
     * Traduit les pannes courantes. Le message brut de Java ne dit rien à
     * personne : ici on nomme la cause et, quand c'est utile, le remède.
     */
    private static String lisible(Throwable t, String host) {
        String brut = short_(String.valueOf(t.getMessage()));
        String b = brut.toLowerCase();
        if (b.contains("cleartext")) {
            return "trafic HTTP bloqué par Android — mets l'application à jour";
        }
        if (b.contains("econnrefused") || b.contains("connection refused")) {
            return host + " répond mais refuse la connexion — machine allumée, service coupé ?";
        }
        if (b.contains("ehostunreach") || b.contains("enetunreach") || b.contains("network is unreachable")) {
            return "réseau inaccessible — le téléphone est-il sur le wifi de l'atelier ?";
        }
        if (b.contains("timed out") || b.contains("timeout") || b.contains("etimedout")) {
            return "pas de réponse de " + host + " — machine éteinte, ou téléphone hors du wifi de l'atelier";
        }
        if (b.contains("unauthorized") || b.contains("not authorized") || b.contains("bad user name")) {
            return "refusé par la machine — code d'accès LAN ou numéro de série erroné";
        }
        return brut;
    }

    /* ---------- Creality / Klipper ---------- */

    private static void pollMoonraker(JSONObject conf, JSONObject out) throws Exception {
        String host = conf.getString("host");
        int port = conf.optInt("port", 7125);
        String base = "http://" + host + ":" + port;

        JSONObject d = getJson(base
                + "/printer/objects/query?print_stats&virtual_sdcard&display_status");
        JSONObject st = d.getJSONObject("result").getJSONObject("status");
        JSONObject ps = st.optJSONObject("print_stats");
        JSONObject vs = st.optJSONObject("virtual_sdcard");

        String state = ps == null ? "" : ps.optString("state", "");
        String file = ps == null ? "" : ps.optString("filename", "");
        double elapsed = ps == null ? 0 : ps.optDouble("print_duration", 0);
        double progress = vs == null ? 0 : vs.optDouble("progress", 0);

        out.put("state", normalise(state));
        out.put("file", file);
        out.put("percent", (int) Math.round(progress * 100));

        long remaining = -1;
        /* le plus fiable : la durée estimée par le trancheur, dans les
           métadonnées du fichier */
        if (file != null && file.length() > 0) {
            try {
                JSONObject m = getJson(base + "/server/files/metadata?filename="
                        + URLEncoder.encode(file, "UTF-8"));
                double est = m.getJSONObject("result").optDouble("estimated_time", 0);
                if (est > 0 && elapsed > 0) remaining = Math.round((est - elapsed) / 60.0);
            } catch (Exception ignored) {
            }
        }
        /* sinon, règle de trois sur l'avancement */
        if (remaining < 0 && progress > 0.01 && elapsed > 0) {
            remaining = Math.round((elapsed * (1 - progress) / progress) / 60.0);
        }
        out.put("remaining", Math.max(0, remaining));

        /* bobines du CFS : requête à part, une machine sans CFS n'a pas
           d'objet « box » et ne doit pas faire échouer tout le relevé */
        JSONArray slots = new JSONArray();
        try {
            JSONObject b = getJson(base + "/printer/objects/query?box")
                    .getJSONObject("result").getJSONObject("status").optJSONObject("box");
            if (b != null) cfsSlots(b, slots);
        } catch (Exception ignored) {
        }
        out.put("ams", slots);
    }

    /**
     * Le CFS range ses bobines par module (T1 à T4), quatre emplacements
     * chacun, en tableaux parallèles : couleur « 0RRGGBB », code matière
     * « 1XXXXX », fabricant « none » quand l'emplacement est vide.
     */
    private static void cfsSlots(JSONObject box, JSONArray slots) throws Exception {
        String lettres = "ABCD";
        for (int u = 1; u <= 4; u++) {
            JSONObject mod = box.optJSONObject("T" + u);
            if (mod == null) continue;
            if (!"connect".equalsIgnoreCase(mod.optString("state", ""))) continue;
            JSONArray couleurs = mod.optJSONArray("color_value");
            JSONArray matieres = mod.optJSONArray("material_type");
            JSONArray fabricants = mod.optJSONArray("vender");
            if (couleurs == null) continue;
            for (int i = 0; i < couleurs.length() && i < 4; i++) {
                String fab = fabricants == null ? "" : fabricants.optString(i).trim();
                if ("none".equalsIgnoreCase(fab)) continue;
                String c = couleurs.optString(i).trim();
                String code = matieres == null ? "" : matieres.optString(i).trim();
                String couleur = c.length() >= 6 && !c.startsWith("-") ? "#" + c.substring(c.length() - 6) : "";
                String type = matiereCreality(code);
                if (couleur.length() == 0 && type.length() == 0) continue;
                JSONObject s = new JSONObject();
                s.put("slot", "T" + u + lettres.charAt(i));
                s.put("type", type.length() > 0 ? type : "?");
                s.put("color", couleur);
                slots.put(s);
            }
        }
    }

    /**
     * Codes matière des étiquettes RFID Creality. Le « 1 » de tête est
     * retiré ; au-delà de la liste, on se contente de ne pas nommer.
     */
    private static String matiereCreality(String code) {
        if (code == null) return "";
        code = code.trim();
        if (code.length() == 6 && code.charAt(0) == '1') code = code.substring(1);
        if (code.length() != 5) return "";
        switch (code) {
            case "02001": case "00006": return "PLA-CF";
            case "03001": case "07001": case "00004": return "ABS";
            case "06001": case "06002": case "00003": return "PETG";
            case "06003": case "00014": return "PETG-CF";
            case "07002": case "00021": return "PC";
            case "10001": case "16001": case "00005": case "00026": return "TPU";
            case "11001": case "00008": case "00023": return "PA";
            case "12002": case "12003": case "12004": case "12005": case "00009":
            case "00015": case "00016": case "00022": case "00025": return "PA-CF";
            case "19001": case "00007": return "ASA";
            case "00033": return "ASA-CF";
            case "00011": return "PVA";
            case "00012": return "HIPS";
            case "00020": return "PET";
            case "00032": return "PCTG";
            default: break;
        }
        /* le reste de la gamme Creality est du PLA sous divers noms */
        String[] pla = {"01001", "01002", "01004", "01601", "04001", "05001", "08001", "09001",
                "09002", "13001", "14001", "15001", "17001", "18001", "29001", "00001", "00002",
                "00024", "00035"};
        for (String x : pla) if (x.equals(code)) return "PLA";
        return "";
    }

    /* ---------- Bambu ---------- */

    private static void pollBambu(JSONObject conf, JSONObject out) throws Exception {
        JSONObject p = BambuClient.fetch(
                conf.getString("host"),
                conf.getString("serial"),
                conf.getString("code"),
                8);

        out.put("state", normalise(p.optString("gcode_state", "")));
        String file = p.optString("subtask_name", "");
        if (file.length() == 0) file = p.optString("gcode_file", "");
        out.put("file", file);
        out.put("percent", p.optInt("mc_percent", -1));
        out.put("remaining", p.optInt("mc_remaining_time", -1));
        out.put("nozzle", p.optDouble("nozzle_temper", 0));
        out.put("bed", p.optDouble("bed_temper", 0));

        JSONArray slots = new JSONArray();
        JSONObject ams = p.optJSONObject("ams");
        if (ams != null) {
            JSONArray units = ams.optJSONArray("ams");
            /* un bit par emplacement occupé, même quand la bobine n'est pas
               identifiée (pas de puce, et rien de saisi dans Bambu Studio) */
            long presentes = 0;
            try {
                presentes = Long.parseLong(ams.optString("tray_exist_bits", "0"), 16);
            } catch (Exception ignored) {
            }
            if (units != null) {
                for (int i = 0; i < units.length(); i++) {
                    JSONObject unit = units.getJSONObject(i);
                    JSONArray trays = unit.optJSONArray("tray");
                    if (trays == null) continue;
                    int numAms = unit.optInt("id", i);
                    for (int j = 0; j < trays.length(); j++) {
                        JSONObject t = trays.getJSONObject(j);
                        String type = t.optString("tray_type", "");
                        int idx = t.optInt("id", j);
                        boolean occupe = ((presentes >> (numAms * 4 + idx)) & 1L) == 1L;
                        if (type.length() == 0 && occupe) {
                            JSONObject s = new JSONObject();
                            s.put("slot", String.valueOf(idx));
                            s.put("type", "?");
                            s.put("color", "");
                            s.put("inconnue", true);
                            slots.put(s);
                            continue;
                        }
                        if (type.length() == 0) continue;
                        JSONObject s = new JSONObject();
                        s.put("slot", t.optString("id", String.valueOf(j)));
                        s.put("type", type);
                        s.put("color", cleanColor(t.optString("tray_color", "")));
                        slots.put(s);
                    }
                }
            }
        }
        /* bobine externe, sur le support à l'arrière : c'est la seule
           qu'une machine sans AMS déclare, sous « vt_tray » */
        JSONObject ext = p.optJSONObject("vt_tray");
        if (ext != null) {
            String type = ext.optString("tray_type", "");
            if (type.length() > 0) {
                JSONObject s = new JSONObject();
                s.put("slot", "ext");
                s.put("type", type);
                s.put("color", cleanColor(ext.optString("tray_color", "")));
                slots.put(s);
            }
        }
        out.put("ams", slots);
    }

    /** Bambu renvoie du RGBA en hexa (000000FF) ; on garde le RGB. */
    private static String cleanColor(String c) {
        if (c == null) return "";
        c = c.trim();
        if (c.length() >= 6) return "#" + c.substring(0, 6);
        return "";
    }

    /** Vocabulaire commun aux deux marques. */
    private static String normalise(String s) {
        if (s == null) return "unknown";
        String v = s.toLowerCase();
        if (v.contains("running") || v.contains("printing")) return "printing";
        if (v.contains("pause")) return "paused";
        if (v.contains("finish") || v.contains("complete")) return "finished";
        if (v.contains("fail") || v.contains("error")) return "failed";
        if (v.contains("prepare") || v.contains("slicing")) return "preparing";
        if (v.contains("idle") || v.contains("standby") || v.contains("ready")) return "idle";
        return v.length() == 0 ? "unknown" : v;
    }

    /* ---------- HTTP ---------- */

    private static JSONObject getJson(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(6000);
        c.setReadTimeout(10000);
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
        return new JSONObject(new String(bos.toByteArray(), "UTF-8"));
    }
}
