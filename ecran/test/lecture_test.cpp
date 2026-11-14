// Donne a l'ecran un vrai relevé de serveur et verifie ce qu'il en tire.
//   g++ -std=c++17 -I stubs -I ../src lecture_test.cpp -o lecture_test && ./lecture_test
#include "nmt_lecture.h"

#include <cstdio>
#include <string>

static int rates = 0, faits = 0;

static void dire(bool bon, const std::string& quoi, const std::string& eu = "") {
    faits++;
    if (bon) printf("  ok   %s\n", quoi.c_str());
    else { rates++; printf("  RATE %s%s%s\n", quoi.c_str(),
                           eu.size() ? "  -> " : "", eu.c_str()); }
}
static void egal(const std::string& eu, const std::string& voulu,
                 const std::string& quoi) {
    dire(eu == voulu, quoi, "« " + eu + " »");
}

// Un relevé comme le serveur le sert vraiment : les Bambu y trainent leur
// charge brute, une machine est injoignable, une autre republie une lecture
// datee, et les cles ne sont pas dans l'ordre d'affichage.
static const char* RELEVE = R"({
  "ok": true,
  "at": 1763128800000,
  "machines": {
    "10.1.3.10": {
      "ok": true, "kind": "bambu", "state": "printing", "file": "pauldron.3mf",
      "percent": 42, "remaining": 84, "nom": "P1S 1", "at": 1763128799000,
      "nozzle": 220, "bed": 60, "slot": 1,
      "brut": {"print": {"mc_percent": 42, "mc_remaining_time": 84,
               "gcode_state": "RUNNING", "ams": {"tray_now": "1"},
               "bidon": "des kilo-octets de charge brute qu'on ne veut pas"}},
      "ams": [{"slot": 1, "type": "PLA", "color": "FF0000"}]
    },
    "10.1.2.57": {
      "ok": true, "kind": "moonraker", "state": "idle", "file": "",
      "percent": 0, "remaining": 0, "nom": "K2 Plus 1", "at": 1763128799500,
      "prevu": {}, "ams": []
    },
    "10.1.3.24": {
      "ok": false, "kind": "moonraker", "nom": "H2S",
      "error": "connexion refusee", "at": 1763128799800
    },
    "10.1.3.11": {
      "ok": true, "kind": "bambu", "state": "paused", "file": "visiere.3mf",
      "percent": 71, "remaining": 19, "nom": "P1S 2", "at": 1763128200000,
      "stale": true, "staleError": "la machine a mis trop longtemps"
    },
    "10.1.2.59": {
      "ok": true, "kind": "moonraker", "state": "failed", "file": "plastron.gcode",
      "percent": 12, "remaining": -1, "nom": "K2 Plus 2", "at": 1763128799900,
      "erreur": "thermistance debranchee"
    }
  },
  "envois": [{"ident": "abc", "etat": "fini", "fichier": "truc.gcode"}]
})";

int main() {
    setenv("TZ", "CET-1CEST,M3.5.0/2,M10.5.0/3", 1);
    tzset();

    JsonDocument filtre;
    nmt::remplirFiltre(filtre);
    JsonDocument doc;
    DeserializationError err = deserializeJson(
        doc, RELEVE, DeserializationOption::Filter(filtre));
    dire(!err, "le relevé se lit", err.c_str());

    std::vector<nmt::Etat> m;
    long long at = nmt::extraire(doc, m);

    printf("\n--- l'heure et le nombre de machines ---\n");
    dire(at == 1763128800000LL, "l'heure du relevé est reprise telle quelle");
    dire(m.size() == 5, "les cinq machines sont la",
         std::to_string(m.size()) + " trouvee(s)");
    if (m.size() != 5) { printf("\nIl manque des machines, on s'arrete.\n"); return 1; }

    printf("\n--- l'ordre ne depend pas du serveur ---\n");
    egal(m[0].nom, "H2S", "H2S en premier");
    egal(m[1].nom, "K2 Plus 1", "puis K2 Plus 1");
    egal(m[2].nom, "K2 Plus 2", "puis K2 Plus 2");
    egal(m[3].nom, "P1S 1", "puis P1S 1");
    egal(m[4].nom, "P1S 2", "puis P1S 2");

    printf("\n--- une impression en cours ---\n");
    const nmt::Etat& p1 = m[3];
    egal(p1.state, "printing", "elle imprime");
    egal(p1.fichier, "pauldron.3mf", "on sait quel fichier");
    dire(p1.pourcent == 42, "et a combien elle en est");
    dire(p1.reste == 84, "et combien de temps il reste");
    egal(nmt::dureeTexte(p1.reste), "1 h 24", "ce qui se lit « 1 h 24 »");
    egal(nmt::heureFin(p1.at, p1.reste), "16:23", "pour une fin a 16:23");
    dire(!p1.stale, "la lecture est fraiche");
    dire(!nmt::demandeAttention(p1), "elle ne demande rien");

    printf("\n--- la charge brute des Bambu est jetee ---\n");
    // C'est tout l'interet du filtre : sans lui, « brut » entre en memoire.
    dire(doc["machines"]["10.1.3.10"]["brut"].isNull(),
         "« brut » n'est jamais entre en memoire");
    dire(doc["machines"]["10.1.3.10"]["nozzle"].isNull(),
         "ni les temperatures, qu'on n'affiche pas");
    dire(doc["envois"].isNull(), "ni la liste des envois");

    printf("\n--- une machine injoignable ---\n");
    const nmt::Etat& h2s = m[0];
    dire(!h2s.ok, "elle n'est pas ok");
    egal(h2s.erreur, "connexion refusee", "et on sait pourquoi");
    egal(nmt::etatTexte(h2s), "connexion refusee", "c'est ce qui s'affiche");
    dire(nmt::etatCouleur(h2s) == nmt::Couleurs::warn,
         "en jaune, pas en rouge");
    dire(h2s.reste == -1, "elle n'annonce aucun temps restant");
    egal(nmt::dureeTexte(h2s.reste), "--", "donc aucun chiffre n'est invente");

    printf("\n--- une lecture datee se signale ---\n");
    const nmt::Etat& p2 = m[4];
    dire(p2.stale, "le drapeau stale est repris");
    egal(p2.erreur, "la machine a mis trop longtemps",
         "la raison de la republication aussi");
    dire(nmt::perime(at, p2.at), "et dix minutes, c'est perime");
    egal(nmt::fraicheurTexte(at, p2.at), "lu il y a 10 min",
         "ce qui s'affiche a la place du fichier");

    printf("\n--- un echec machine ---\n");
    const nmt::Etat& k2 = m[2];
    egal(k2.state, "failed", "l'etat est failed");
    egal(k2.erreur, "thermistance debranchee",
         "l'erreur de la machine passe avant celle de lecture");
    dire(nmt::etatCouleur(k2) == nmt::Couleurs::bad, "en rouge, lui");
    dire(nmt::demandeAttention(k2), "et il demande d'aller voir");

    printf("\n--- une machine libre ---\n");
    const nmt::Etat& k1 = m[1];
    egal(nmt::etatTexte(k1), "libre", "elle est libre");
    egal(k1.fichier, "", "sans fichier");
    egal(k1.erreur, "", "sans erreur");

    printf("\n--- un relevé vide ou casse ne fait pas tomber l'ecran ---\n");
    JsonDocument vide;
    deserializeJson(vide, "{\"ok\":true,\"at\":0,\"machines\":{}}",
                    DeserializationOption::Filter(filtre));
    std::vector<nmt::Etat> rien;
    dire(nmt::extraire(vide, rien) == 0 && rien.empty(),
         "aucune machine, aucune invention");

    JsonDocument casse;
    DeserializationError e2 = deserializeJson(casse, "{\"machines\":", 
                                              DeserializationOption::Filter(filtre));
    dire((bool)e2, "un JSON tronque est signale comme tel");

    JsonDocument sansNom;
    deserializeJson(sansNom,
        "{\"at\":1,\"machines\":{\"10.1.2.99\":{\"ok\":true,\"state\":\"idle\"}}}",
        DeserializationOption::Filter(filtre));
    std::vector<nmt::Etat> anon;
    nmt::extraire(sansNom, anon);
    dire(anon.size() == 1, "une machine sans nom est quand meme listee");
    egal(anon.empty() ? "" : anon[0].nom, "10.1.2.99",
         "et elle prend son adresse pour nom");

    printf("\n==============================\n");
    if (rates) { printf("%d rate(s) sur %d verifications.\n", rates, faits); return 1; }
    printf("Tout est passe (%d verifications).\n\n", faits);
    return 0;
}
