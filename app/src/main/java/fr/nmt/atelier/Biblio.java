package fr.nmt.atelier;

import android.content.Context;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Bibliothèque de gcodes de l'atelier.
 *
 * Les fichiers tranchés ne vivent qu'à un seul endroit, sur le Pi, rangés
 * par famille de machines. Le Pi les sert sur le réseau local ; cette
 * classe l'interroge.
 *
 * Contrairement au relevé des machines, qui passe par ntfy et marche de
 * partout, la bibliothèque n'est joignable qu'à la maison : les fichiers
 * pèsent des dizaines de mégaoctets et n'ont rien à faire sur Internet.
 * Hors du réseau de l'atelier, l'écran le dit et s'arrête là.
 */
public class Biblio {

    private static final String PREFS = "nmt_printers";
    private static final String KEY_HOTE = "biblio_host";
    private static final String KEY_JETON = "biblio_token";

    /* Un dépôt de fichier peut durer : une K2 avale 60 Mo en quelques
       secondes sur le réseau, mais pas toujours. */
    private static final int DELAI_LECTURE = 20000;
    private static final int DELAI_ENVOI = 180000;

    static String hote(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_HOTE, "");
    }

    static String jeton(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_JETON, "");
    }

    static void regler(Context c, String hote, String jeton) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_HOTE, hote == null ? "" : hote.trim())
                .putString(KEY_JETON, jeton == null ? "" : jeton.trim())
                .apply();
    }

    static boolean actif(Context c) {
        return hote(c).length() > 0;
    }

    /** « 10.1.2.60 », « 10.1.2.60:8765 » ou une URL complète : tout marche. */
    private static String base(Context c) {
        String h = hote(c);
        if (h.length() == 0) throw new IllegalStateException("adresse du relais non réglée");
        if (!h.startsWith("http://") && !h.startsWith("https://")) h = "http://" + h;
        if (h.indexOf(':', h.indexOf("//") + 2) < 0) h = h + ":8765";
        while (h.endsWith("/")) h = h.substring(0, h.length() - 1);
        return h;
    }

    private static String corps(HttpURLConnection co) throws Exception {
        InputStream in = co.getResponseCode() >= 400 ? co.getErrorStream() : co.getInputStream();
        if (in == null) return "";
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] tampon = new byte[8192];
        int n;
        while ((n = in.read(tampon)) > 0) out.write(tampon, 0, n);
        in.close();
        return new String(out.toByteArray(), "UTF-8");
    }

    private static JSONObject appel(Context c, String route, JSONObject envoi, int delai) {
        HttpURLConnection co = null;
        try {
            co = (HttpURLConnection) new URL(base(c) + route).openConnection();
            co.setConnectTimeout(4000);
            co.setReadTimeout(delai);
            String j = jeton(c);
            if (j.length() > 0) co.setRequestProperty("Authorization", "Bearer " + j);
            if (envoi != null) {
                co.setRequestMethod("POST");
                co.setDoOutput(true);
                co.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                OutputStream os = co.getOutputStream();
                os.write(envoi.toString().getBytes("UTF-8"));
                os.close();
            }
            String texte = corps(co);
            int code = co.getResponseCode();
            JSONObject rep;
            try {
                rep = new JSONObject(texte);
            } catch (Exception malforme) {
                return erreur("réponse illisible du relais (HTTP " + code + ")");
            }
            if (code == 401) return erreur("jeton refusé par le relais");
            if (code >= 400 && !rep.has("error")) return erreur("relais : HTTP " + code);
            return rep;
        } catch (IllegalStateException e) {
            return erreur(String.valueOf(e.getMessage()));
        } catch (Throwable t) {
            return erreur(horsReseau(t));
        } finally {
            if (co != null) co.disconnect();
        }
    }

    /**
     * Le cas courant n'est pas une panne : c'est qu'il n'est pas à l'atelier.
     * Autant le dire comme ça plutôt que de recracher l'exception.
     */
    private static String horsReseau(Throwable t) {
        String m = String.valueOf(t.getMessage()).toLowerCase();
        if (m.contains("timeout") || m.contains("timed out") || m.contains("unreachable")
                || m.contains("refused") || m.contains("failed to connect")
                || m.contains("no route")) {
            return "relais injoignable — la bibliothèque n'est accessible qu'à l'atelier";
        }
        return String.valueOf(t.getMessage());
    }

    private static JSONObject erreur(String message) {
        JSONObject o = new JSONObject();
        try {
            o.put("ok", false);
            o.put("error", message);
        } catch (Exception ignored) {
        }
        return o;
    }

    /* ---------- ce que l'interface appelle ---------- */

    /**
     * L'index, par le chemin le plus direct qui réponde.
     *
     * À l'atelier, le service du relais : instantané et complet. Ailleurs,
     * ce que le relais a publié sur le canal : un peu moins frais, et sans
     * les aperçus de plateaux, mais lisible de n'importe où.
     */
    static JSONObject index(Context c) {
        if (actif(c)) {
            JSONObject direct = appel(c, "/biblio", null, DELAI_LECTURE);
            if (direct.optBoolean("ok")) return direct;
        }
        try {
            JSONObject canal = Relay.bibliotheque(c);
            if (canal.optBoolean("ok")) return canal;
            return erreur(Relay.actif(c)
                    ? "le relais n'a encore rien publié de la bibliothèque"
                    : "aucun relais configuré");
        } catch (Throwable t) {
            return erreur(String.valueOf(t.getMessage()));
        }
    }

    /** Vrai quand le service du relais répond ici et maintenant. */
    static boolean surPlace(Context c) {
        return actif(c) && appel(c, "/vivant", null, 3000).optBoolean("ok");
    }

    static JSONObject historique(Context c, int combien) {
        return appel(c, "/historique?n=" + Math.max(1, combien), null, DELAI_LECTURE);
    }

    static JSONObject exemplaires(Context c, String chemin, int combien) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "exemplaires");
            o.put("chemin", chemin);
            o.put("n", combien);
            if (surPlace(c)) return appel(c, "/exemplaires", o, DELAI_LECTURE);
            return parLeCanal(c, o);
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
    }

    /**
     * Une action qui ne déplace aucun fichier marche aussi hors de
     * l'atelier : on la publie, et le relais l'applique dans la minute.
     */
    private static JSONObject parLeCanal(Context c, JSONObject ordre) {
        try {
            if (!Relay.actif(c)) return erreur("aucun relais configuré");
            if (jeton(c).length() == 0) {
                // sans jeton l'ordre partirait et le relais le jetterait sans
                // que personne ne le sache : autant refuser tout de suite
                return erreur("il manque le jeton du relais — Réglages, "
                        + "Bibliothèque de gcodes");
            }
            String ident = Relay.ordre(c, ordre, jeton(c));
            JSONObject o = new JSONObject();
            o.put("ok", true);
            o.put("differe", true);
            o.put("id", ident);
            return o;
        } catch (Throwable t) {
            return erreur(String.valueOf(t.getMessage()));
        }
    }

    /** Un ordre sans effet, juste pour savoir si le jeton passe. */
    static JSONObject verifierJeton(Context c) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "ping");
            return parLeCanal(c, o);
        } catch (Throwable t) {
            return erreur(String.valueOf(t.getMessage()));
        }
    }

    static JSONObject exemplairesPlateau(Context c, String chemin, int plateau, int combien) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "exemplaires");
            o.put("chemin", chemin);
            o.put("plateau", plateau);
            o.put("n", combien);
            if (surPlace(c)) return appel(c, "/exemplaires", o, DELAI_LECTURE);
            return parLeCanal(c, o);
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
    }

    /** « Celui-là est sorti » — ou l'inverse quand on s'est trompé. */
    static JSONObject marquer(Context c, String chemin, int plateau,
                              boolean fait, String machine) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "marquer");
            o.put("chemin", chemin);
            o.put("plateau", plateau);
            o.put("fait", fait);
            o.put("machine", machine == null ? "" : machine);
            if (surPlace(c)) return appel(c, "/marquer", o, DELAI_LECTURE);
            return parLeCanal(c, o);
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
    }

    /**
     * Où en sont les envois. Sur place le relais répond tout de suite ;
     * de loin, c'est son dernier relevé qui le dit, à une minute près.
     */
    static JSONObject envois(Context c) {
        try {
            JSONObject out = new JSONObject();
            if (surPlace(c)) {
                JSONObject e = appel(c, "/etat", null, DELAI_LECTURE);
                out.put("ok", true);
                out.put("envois", e.optJSONArray("envois") == null
                        ? new org.json.JSONArray() : e.optJSONArray("envois"));
                out.put("direct", true);
                return out;
            }
            if (!Relay.actif(c)) return erreur("aucun relais configuré");
            out.put("ok", true);
            out.put("envois", Relay.envois(c));
            out.put("direct", false);
            return out;
        } catch (Throwable t) {
            return erreur(String.valueOf(t.getMessage()));
        }
    }

    /** « Celui-là est raté » — pour ne pas l'oublier au moment de relancer. */
    static JSONObject refaire(Context c, String chemin, int plateau, boolean refaire) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "refaire");
            o.put("chemin", chemin);
            o.put("plateau", plateau);
            o.put("refaire", refaire);
            if (surPlace(c)) return appel(c, "/refaire", o, DELAI_LECTURE);
            return parLeCanal(c, o);
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
    }

    static JSONObject commande(Context c, String chemin, String nom) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "commande");
            o.put("chemin", chemin);
            o.put("commande", nom == null ? "" : nom);
            if (surPlace(c)) return appel(c, "/commande", o, DELAI_LECTURE);
            return parLeCanal(c, o);
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
    }

    /**
     * L'aperçu d'un plateau, en base64 pour que la page l'affiche sans
     * refaire l'appel elle-même — le jeton ne quitte pas le Java.
     */
    static JSONObject apercu(Context c, String chemin, int plateau) {
        HttpURLConnection co = null;
        try {
            String url = base(c) + "/vignette?chemin="
                    + java.net.URLEncoder.encode(chemin, "UTF-8") + "&plateau=" + plateau;
            co = (HttpURLConnection) new URL(url).openConnection();
            co.setConnectTimeout(4000);
            co.setReadTimeout(DELAI_LECTURE);
            String j = jeton(c);
            if (j.length() > 0) co.setRequestProperty("Authorization", "Bearer " + j);
            if (co.getResponseCode() != 200) return erreur("pas d'aperçu");
            InputStream in = co.getInputStream();
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            byte[] tampon = new byte[8192];
            int n;
            while ((n = in.read(tampon)) > 0) out.write(tampon, 0, n);
            in.close();
            JSONObject o = new JSONObject();
            o.put("ok", true);
            o.put("png", android.util.Base64.encodeToString(
                    out.toByteArray(), android.util.Base64.NO_WRAP));
            return o;
        } catch (Throwable t) {
            return erreur(String.valueOf(t.getMessage()));
        } finally {
            if (co != null) co.disconnect();
        }
    }

    /**
     * Envoyer un fichier sur une machine marche aussi de loin : le fichier
     * est déjà sur le Pi, et le Pi est sur le réseau des machines. Le
     * téléphone ne transporte rien, il dit seulement lequel va où.
     */
    static JSONObject pousser(Context c, String chemin, String machine,
                              String hote, boolean lancer, int plateau) {
        try {
            JSONObject o = new JSONObject();
            o.put("quoi", "pousser");
            o.put("chemin", chemin);
            o.put("machine", machine);
            // le nom se renomme, l'adresse non : c'est elle qui fait le lien
            // avec la machine que le relais connaît
            o.put("hote", hote == null ? "" : hote);
            o.put("lancer", lancer);
            o.put("plateau", Math.max(1, plateau));
            if (surPlace(c)) return appel(c, "/pousser", o, DELAI_ENVOI);
            return parLeCanal(c, o);
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
    }

    /**
     * Pour l'écran des réglages. Il y a deux chemins et un jeton, et l'ancien
     * test ne regardait que le premier : hors du réseau de l'atelier il
     * annonçait un échec alors que tout marchait par le canal.
     */
    static JSONObject test(Context c) {
        JSONObject out = new JSONObject();
        try {
            boolean direct = actif(c) && appel(c, "/vivant", null, 5000).optBoolean("ok");
            out.put("direct", direct);
            out.put("adresse", hote(c));

            JSONObject index = index(c);
            out.put("lecture", index.optBoolean("ok"));
            out.put("canal", index.optBoolean("canal"));
            out.put("fichiers", index.optJSONArray("fichiers") == null
                    ? 0 : index.optJSONArray("fichiers").length());
            if (!index.optBoolean("ok")) out.put("error", index.optString("error"));

            out.put("jeton", jeton(c).length() > 0);
            if (jeton(c).length() > 0 && !direct) {
                // le jeton ne se vérifie qu'en faisant le tour : on publie un
                // ordre sans effet, le relais l'accusera à sa prochaine relève
                JSONObject ping = verifierJeton(c);
                out.put("ping", ping.optString("id"));
                if (!ping.optBoolean("ok")) out.put("error", ping.optString("error"));
            }
            out.put("ok", index.optBoolean("ok"));
        } catch (Exception e) {
            return erreur(String.valueOf(e.getMessage()));
        }
        return out;
    }

    /** L'accusé que le relais a joint à son index pour cet ordre, s'il est arrivé. */
    static JSONObject accuse(Context c, String ident) {
        JSONObject index = index(c);
        org.json.JSONArray liste = index.optJSONArray("accuses");
        if (liste == null) return new JSONObject();
        for (int i = liste.length() - 1; i >= 0; i--) {
            JSONObject a = liste.optJSONObject(i);
            if (a != null && ident.equals(a.optString("id"))) return a;
        }
        return new JSONObject();
    }
}
