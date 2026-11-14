// Ce que l'ecran doit savoir calculer, sans rien connaitre de LVGL ni du
// reseau : a quoi ressemble un etat, combien de temps il reste, a quelle
// heure ca finit, et si ce qu'on affiche est encore frais.
//
// Tout est ici pour une raison : ce fichier se compile aussi sur un PC, et
// test/modele_test.cpp le verifie. C'est la seule partie du firmware qu'on
// peut prouver sans brancher l'ecran.
#pragma once

#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>

namespace nmt {

// La charte de l'app, telle quelle : web/css/app.css
struct Couleurs {
    static const unsigned long bg      = 0x0f131b;
    static const unsigned long card    = 0x1a202b;
    static const unsigned long line    = 0x2e3542;
    static const unsigned long txt     = 0xe9edf3;
    static const unsigned long txt2    = 0x98a3b5;
    static const unsigned long txt3    = 0x6a7488;
    static const unsigned long acc     = 0x2cb2ff;
    static const unsigned long ok      = 0x3ecf8e;
    static const unsigned long warn    = 0xffc043;
    static const unsigned long bad     = 0xff5f56;
    static const unsigned long info    = 0x9d8cff;
};

// Un etat de machine, tel que GET /etat du serveur le donne.
struct Etat {
    std::string nom;
    std::string state;        // printing, paused, finished, failed, preparing, idle, unknown
    std::string fichier;
    std::string erreur;
    bool ok = false;
    bool stale = false;
    int pourcent = -1;        // -1 = inconnu
    int reste = -1;           // minutes, -1 = inconnu
    long long at = 0;         // ms epoch, heure de la lecture de CETTE machine
};

// --- etats -------------------------------------------------------------

// Ce qu'on ecrit sous le nom de la machine quand il n'y a pas de fichier.
inline std::string etatTexte(const Etat& e) {
    if (!e.ok && e.erreur.size()) return e.erreur;
    if (!e.ok)                    return "injoignable";
    if (e.state == "printing")    return "en cours";
    if (e.state == "paused")      return "en pause";
    if (e.state == "finished")    return "terminee";
    if (e.state == "failed")      return "echec";
    if (e.state == "preparing")   return "preparation";
    if (e.state == "idle")        return "libre";
    return e.state.size() ? e.state : "inconnu";
}

// La couleur de la pastille. Une machine injoignable n'est pas en panne :
// c'est nous qui ne savons pas. D'ou le jaune, pas le rouge.
inline unsigned long etatCouleur(const Etat& e) {
    if (!e.ok)                  return Couleurs::warn;
    if (e.state == "failed")    return Couleurs::bad;
    if (e.state == "paused")    return Couleurs::warn;
    if (e.state == "printing")  return Couleurs::acc;
    if (e.state == "preparing") return Couleurs::info;
    if (e.state == "finished")  return Couleurs::ok;
    return Couleurs::txt3;
}

// Un etat qui demande qu'on aille voir la machine.
inline bool demandeAttention(const Etat& e) {
    return (!e.ok) || e.state == "failed" || e.state == "paused"
           || e.state == "finished";
}

// --- durees ------------------------------------------------------------

// Les minutes telles qu'on les lit de loin : « 1 h 24 », « 24 min ».
inline std::string dureeTexte(int minutes) {
    if (minutes < 0) return "--";
    if (minutes == 0) return "fini";
    if (minutes < 60) {
        char b[16];
        snprintf(b, sizeof b, "%d min", minutes);
        return b;
    }
    char b[24];
    snprintf(b, sizeof b, "%d h %02d", minutes / 60, minutes % 60);
    return b;
}

// L'heure a laquelle ca se termine, dans le fuseau de l'atelier. L'heure de
// depart vient du serveur (champ « at »), pas d'un NTP : l'ecran n'a donc
// pas besoin d'Internet, et il ne peut pas afficher une heure fausse parce
// qu'il n'a pas reussi a se synchroniser.
inline std::string heureFin(long long atMs, int resteMinutes) {
    if (atMs <= 0 || resteMinutes < 0) return "";
    time_t t = (time_t)(atMs / 1000) + (time_t)resteMinutes * 60;
    struct tm tm;
    localtime_r(&t, &tm);
    char b[16];
    snprintf(b, sizeof b, "%02d:%02d", tm.tm_hour, tm.tm_min);
    return b;
}

inline std::string heureDe(long long atMs) {
    if (atMs <= 0) return "--:--";
    time_t t = (time_t)(atMs / 1000);
    struct tm tm;
    localtime_r(&t, &tm);
    char b[16];
    snprintf(b, sizeof b, "%02d:%02d", tm.tm_hour, tm.tm_min);
    return b;
}

// --- fraicheur ---------------------------------------------------------

// Un moniteur qui a parfois tort est pire que pas de moniteur. Donc quand
// la lecture date, on le dit en clair plutot que de montrer un chiffre qui
// a l'air frais.
inline std::string fraicheurTexte(long long maintenantMs, long long atMs) {
    if (atMs <= 0) return "jamais lu";
    long long d = (maintenantMs - atMs) / 1000;
    if (d < 0) d = 0;
    if (d < 90) return "a l'instant";
    long long min = (d + 30) / 60;
    if (min < 60) {
        char b[32];
        snprintf(b, sizeof b, "lu il y a %lld min", min);
        return b;
    }
    char b[32];
    snprintf(b, sizeof b, "lu il y a %lld h", (min + 30) / 60);
    return b;
}

// Au-dela, ce qu'on affiche n'est plus un etat, c'est un souvenir.
//
// Le serveur releve chaque machine toutes les minutes et pose lui-meme un
// drapeau « stale » quand il republie une lecture datee. Ceci n'est donc
// qu'un garde-fou, pour le cas ou il servirait du vieux sans le dire — et un
// garde-fou qui se declenche apres ce qu'il double ne sert a rien. Cinq
// minutes : tolerant pour un cycle qui traine, intransigeant pour du perime.
const long long PERIME_MS = 5LL * 60 * 1000;

inline bool perime(long long maintenantMs, long long atMs) {
    return atMs <= 0 || (maintenantMs - atMs) > PERIME_MS;
}

}  // namespace nmt
