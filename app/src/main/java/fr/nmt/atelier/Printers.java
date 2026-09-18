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
                out.put("error", short_(String.valueOf(t.getMessage())));
            } catch (Exception ignored) {
            }
        }
        return out;
    }

    private static String short_(String s) {
        if (s == null) return "erreur";
        s = s.replaceAll("\\s+", " ").trim();
        return s.length() > 120 ? s.substring(0, 120) + "…" : s;
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
    }

    /* ---------- Bambu ---------- */

    private static void pollBambu(JSONObject conf, JSONObject out) throws Exception {
        JSONObject p = BambuClient.fetch(
                conf.getString("host"),
                conf.getString("serial"),
                conf.getString("code"),
                20);

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
            if (units != null) {
                for (int i = 0; i < units.length(); i++) {
                    JSONArray trays = units.getJSONObject(i).optJSONArray("tray");
                    if (trays == null) continue;
                    for (int j = 0; j < trays.length(); j++) {
                        JSONObject t = trays.getJSONObject(j);
                        String type = t.optString("tray_type", "");
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
