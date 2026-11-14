// Verifie la logique pure du firmware de l'ecran, sur un PC, sans ecran.
//   g++ -std=c++17 -I ../src modele_test.cpp -o modele_test && ./modele_test
#include "nmt_modele.h"

#include <cstdio>
#include <cstdlib>
#include <string>

static int rates = 0;
static int faits = 0;

static void dire(bool bon, const std::string& quoi, const std::string& eu = "") {
    faits++;
    if (bon) {
        printf("  ok   %s\n", quoi.c_str());
    } else {
        rates++;
        printf("  RATE %s%s%s\n", quoi.c_str(),
               eu.size() ? "  -> " : "", eu.c_str());
    }
}

static void egal(const std::string& eu, const std::string& voulu,
                 const std::string& quoi) {
    dire(eu == voulu, quoi, eu.size() ? ("« " + eu + " »") : "« »");
}

int main() {
    // L'atelier est a Lyon. Les heures affichees doivent etre les siennes.
    setenv("TZ", "CET-1CEST,M3.5.0/2,M10.5.0/3", 1);
    tzset();

    printf("\n--- les durees se lisent de loin ---\n");
    egal(nmt::dureeTexte(-1), "--", "une duree inconnue ne s'invente pas");
    egal(nmt::dureeTexte(0), "fini", "zero minute, c'est fini");
    egal(nmt::dureeTexte(24), "24 min", "moins d'une heure reste en minutes");
    egal(nmt::dureeTexte(59), "59 min", "cinquante-neuf minutes aussi");
    egal(nmt::dureeTexte(60), "1 h 00", "une heure juste");
    egal(nmt::dureeTexte(84), "1 h 24", "une heure vingt-quatre");
    egal(nmt::dureeTexte(605), "10 h 05", "les minutes gardent leur zero");

    printf("\n--- l'heure de fin vient du serveur, pas d'un NTP ---\n");
    // 2026-11-14 15:00:00 heure de Lyon = 14:00:00 UTC
    long long midi = 1763128800000LL;  // 2026-11-14T14:00:00Z
    egal(nmt::heureDe(midi), "15:00", "l'heure du releve est locale");
    egal(nmt::heureFin(midi, 84), "16:24", "une heure vingt-quatre plus tard");
    egal(nmt::heureFin(midi, 600), "01:00", "une fin qui passe minuit");
    egal(nmt::heureFin(midi, -1), "", "sans temps restant, pas d'heure de fin");
    egal(nmt::heureFin(0, 84), "", "sans releve, pas d'heure de fin");
    // L'heure d'ete doit decaler de deux heures, pas d'une.
    long long juillet = 1752498000000LL;  // 2025-07-14T13:00:00Z
    egal(nmt::heureDe(juillet), "15:00", "l'heure d'ete est prise en compte");

    printf("\n--- la fraicheur se dit en clair ---\n");
    long long t = midi;
    egal(nmt::fraicheurTexte(t, t), "a l'instant", "une lecture a la seconde");
    egal(nmt::fraicheurTexte(t + 60000, t), "a l'instant",
         "une minute, c'est encore l'instant");
    egal(nmt::fraicheurTexte(t + 14 * 60000, t), "lu il y a 14 min",
         "quatorze minutes se disent");
    egal(nmt::fraicheurTexte(t + 3 * 3600000LL, t), "lu il y a 3 h",
         "au-dela de l'heure on compte en heures");
    egal(nmt::fraicheurTexte(t, 0), "jamais lu", "une machine jamais lue");
    dire(!nmt::perime(t, t), "une lecture fraiche n'est pas perimee");
    dire(!nmt::perime(t + 4 * 60000, t),
         "a quatre minutes, un cycle qui traine reste acceptable");
    dire(nmt::perime(t + 6 * 60000, t), "a six minutes, c'est un souvenir");
    dire(nmt::perime(t, 0), "jamais lu, c'est perime");

    printf("\n--- les etats disent ce qu'ils sont ---\n");
    nmt::Etat e;
    e.ok = true;
    e.state = "printing";
    egal(nmt::etatTexte(e), "en cours", "une impression en cours");
    dire(nmt::etatCouleur(e) == nmt::Couleurs::acc, "elle est a l'accent");
    dire(!nmt::demandeAttention(e), "et elle ne demande rien");

    e.state = "failed";
    egal(nmt::etatTexte(e), "echec", "un echec");
    dire(nmt::etatCouleur(e) == nmt::Couleurs::bad, "il est en rouge");
    dire(nmt::demandeAttention(e), "et il demande d'aller voir");

    e.state = "finished";
    dire(nmt::etatCouleur(e) == nmt::Couleurs::ok, "une fin est en vert");
    dire(nmt::demandeAttention(e),
         "une impression terminee demande d'aller la chercher");

    e.state = "idle";
    egal(nmt::etatTexte(e), "libre", "une machine libre");
    dire(nmt::etatCouleur(e) == nmt::Couleurs::txt3, "elle est eteinte visuellement");
    dire(!nmt::demandeAttention(e), "et elle ne demande rien");

    e.state = "paused";
    dire(nmt::etatCouleur(e) == nmt::Couleurs::warn, "une pause est en jaune");
    dire(nmt::demandeAttention(e), "et elle demande d'aller voir");

    printf("\n--- une machine injoignable n'est pas une machine en panne ---\n");
    nmt::Etat mort;
    mort.ok = false;
    egal(nmt::etatTexte(mort), "injoignable", "sans raison, on dit injoignable");
    dire(nmt::etatCouleur(mort) == nmt::Couleurs::warn,
         "en jaune : c'est nous qui ne savons pas, pas elle qui a echoue");
    dire(nmt::demandeAttention(mort), "et ca demande d'aller voir");
    mort.erreur = "connexion refusee";
    egal(nmt::etatTexte(mort), "connexion refusee",
         "quand on sait pourquoi, on le dit");

    printf("\n--- un etat inconnu ne devient pas un etat connu ---\n");
    nmt::Etat bizarre;
    bizarre.ok = true;
    bizarre.state = "";
    egal(nmt::etatTexte(bizarre), "inconnu", "un etat vide reste inconnu");
    bizarre.state = "calibrating";
    egal(nmt::etatTexte(bizarre), "calibrating",
         "un etat qu'on ne connait pas s'affiche tel quel");
    dire(nmt::etatCouleur(bizarre) == nmt::Couleurs::txt3,
         "et il ne se peint pas en couleur rassurante");

    printf("\n==============================\n");
    if (rates) {
        printf("%d rate(s) sur %d verifications.\n", rates, faits);
        return 1;
    }
    printf("Tout est passe (%d verifications).\n\n", faits);
    return 0;
}
