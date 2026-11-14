// Atelier NMT — l'ecran de l'atelier.
//
// Une extension de l'app sur un Panda Touch : les memes machines, la meme
// charte, la meme source. L'ecran ne parle a aucune imprimante. Il interroge
// le serveur, qui sait deja parler a chacune et qui agrege tout dans
// GET /etat. Donc aucun code LAN Bambu ici, aucun protocole a maintenir, et
// le jour ou une marque casse son API, c'est le serveur qu'on repare.
//
// Tout tourne sur la boucle Arduino, sans deuxieme tache : LVGL n'est pas
// protege par un verrou dans le support BigTreeTech, et un releve toutes les
// cinq secondes ne justifie pas d'en inventer un.

#include <Arduino.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <ArduinoJson.h>
#include <lvgl.h>

#include <algorithm>
#include <string>
#include <vector>

#include "pt/pt_display.h"   // BigTreeTech : dalle RGB, tactile, LVGL
#include "nmt_lecture.h"
#include "nmt_modele.h"
#include "nmt_vue.h"

// Les identifiants wifi sont injectes a la compilation par
// ecran-flash.ps1, qui les lit sur le PC. Ils ne sont pas dans ce depot, qui
// est public, et ils ne transitent nulle part : le fichier reste chez toi.
// Sans ce fichier, l'ecran retombe sur le portail wifi.
#if __has_include("nmt_secrets.h")
#include "nmt_secrets.h"
#endif

static const char* PORTAIL = "Atelier NMT";
static const uint32_t PERIODE_MS = 5000;

// Le fuseau de l'atelier, avec sa regle d'heure d'ete. L'heure vient du
// serveur ; cette chaine ne sert qu'a l'ecrire en heure locale.
static const char* FUSEAU = "CET-1CEST,M3.5.0/2,M10.5.0/3";

static nmt::Vue vue;
static WiFiManager wm;
static Preferences reglages;

static String hote;
static String port;
static String jeton;

static WiFiManagerParameter* pHote;
static WiFiManagerParameter* pPort;
static WiFiManagerParameter* pJeton;

static uint32_t prochain = 0;
static bool portailOuvert = false;

// --- reglages ----------------------------------------------------------

static void lireReglages() {
    reglages.begin("nmt", true);
#ifdef NMT_SERVEUR
    hote = reglages.getString("hote", NMT_SERVEUR);
#else
    hote = reglages.getString("hote", "10.1.2.60");
#endif
    port = reglages.getString("port", "8765");
    jeton = reglages.getString("jeton", "");
    reglages.end();
}

static void enregistrerReglages() {
    reglages.begin("nmt", false);
    reglages.putString("hote", pHote->getValue());
    reglages.putString("port", pPort->getValue());
    reglages.putString("jeton", pJeton->getValue());
    reglages.end();
    lireReglages();
    prochain = 0;   // on relit tout de suite avec les nouveaux reglages
}

// --- lecture du serveur ------------------------------------------------

static bool relever(std::vector<nmt::Etat>& out, long long& atReleve,
                    std::string& dit) {
    if (WiFi.status() != WL_CONNECTED) {
        dit = "pas de wifi";
        return false;
    }

    String url = "http://" + hote + ":" + port + "/etat";
    HTTPClient http;
    http.setConnectTimeout(3000);
    http.setTimeout(4000);
    if (!http.begin(url)) {
        dit = "adresse du serveur illisible";
        return false;
    }
    if (jeton.length()) http.addHeader("Authorization", "Bearer " + jeton);

    int code = http.GET();
    if (code != 200) {
        dit = code > 0 ? ("serveur : HTTP " + std::to_string(code))
                       : std::string("serveur injoignable");
        http.end();
        return false;
    }

    JsonDocument filtre;
    nmt::remplirFiltre(filtre);
    JsonDocument doc;
    DeserializationError err = deserializeJson(
        doc, http.getStream(), DeserializationOption::Filter(filtre));
    http.end();

    if (err) {
        dit = std::string("reponse illisible : ") + err.c_str();
        return false;
    }

    atReleve = nmt::extraire(doc, out);
    dit = "serveur " + std::string(hote.c_str());
    return true;
}

// --- cycle -------------------------------------------------------------

static void cycle() {
    std::vector<nmt::Etat> machines;
    long long atReleve = 0;
    std::string dit;
    bool bon = relever(machines, atReleve, dit);

    long long maintenant = atReleve > 0 ? atReleve : 0;
    nmt::majServeur(vue, bon, dit, atReleve);

    if (bon) {
        nmt::majMachines(vue, machines, maintenant);
    } else if (machines.empty()) {
        nmt::plageTexte(vue, "Serveur injoignable", dit +
            ".\n\nL'ecran n'invente rien : tant qu'il ne lit pas le serveur, "
            "il n'affiche aucun etat de machine. Verifie que le serveur est "
            "allume et que son adresse est la bonne.");
    }
}

static void surToucher(lv_event_t*) { prochain = 0; }

void setup() {
    Serial.begin(115200);

    setenv("TZ", FUSEAU, 1);
    tzset();

    pt_setup_display(PT_LVGL_RENDER_PARTIAL_2);
    nmt::construire(vue);
    lv_obj_add_flag(vue.racine, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(vue.racine, surToucher, LV_EVENT_CLICKED, nullptr);
    // Les cartes font remonter leurs appuis jusqu'ici : sans ca, seul le
    // vide entre les cartes reagirait au doigt.
    lv_obj_add_event_cb(vue.liste, surToucher, LV_EVENT_CLICKED, nullptr);

    nmt::plageTexte(vue, "Demarrage", "Connexion au wifi de l'atelier.");
    lv_timer_handler();

    lireReglages();

    pHote = new WiFiManagerParameter("hote", "Adresse du serveur",
                                     hote.c_str(), 40);
    pPort = new WiFiManagerParameter("port", "Port", port.c_str(), 8);
    pJeton = new WiFiManagerParameter("jeton", "Jeton (vide si aucun)",
                                      jeton.c_str(), 64);
    wm.addParameter(pHote);
    wm.addParameter(pPort);
    wm.addParameter(pJeton);
    wm.setSaveParamsCallback(enregistrerReglages);
    wm.setConfigPortalBlocking(false);
    wm.setConfigPortalTimeout(0);

    // Rien n'est code en dur : ni le wifi, ni l'adresse du serveur. Le
    // binaire ne contient donc aucun secret, et peut vivre dans un depot
    // public sans precaution.
    bool relie = false;
#ifdef NMT_WIFI_SSID
    // Connexion directe, sans rien demander a personne. L'ecran reste vivant
    // pendant l'attente : une barre figee vingt secondes ressemble a une
    // panne, et c'est ce qu'on cherche justement a ne jamais donner a voir.
    nmt::plageTexte(vue, "Wifi", "Connexion a " NMT_WIFI_SSID "...");
    lv_timer_handler();
    WiFi.mode(WIFI_STA);
    WiFi.begin(NMT_WIFI_SSID, NMT_WIFI_PASS);
    uint32_t limite = millis() + 20000;
    while ((int32_t)(millis() - limite) < 0 && WiFi.status() != WL_CONNECTED) {
        pt_loop_display();
    }
    relie = (WiFi.status() == WL_CONNECTED);
    if (!relie) {
        // Le mot de passe a change, ou la box est eteinte : on ne reste pas
        // bloque la, le portail reprend la main.
        nmt::plageTexte(vue, "Wifi introuvable",
            "Impossible de joindre " NMT_WIFI_SSID ". On passe par le portail.");
        lv_timer_handler();
    }
#endif

    if (!relie && !wm.autoConnect(PORTAIL)) {
        portailOuvert = true;
        nmt::plageTexte(vue, "A regler",
            std::string("Connecte ton telephone au wifi « ") + PORTAIL +
            " », puis ouvre http://192.168.4.1\n\n"
            "Tu y donnes le wifi de l'atelier, l'adresse du serveur et son "
            "port. L'ecran garde tout et redemarre dessus.");
    }
}

void loop() {
    pt_loop_display();
    wm.process();

    if (portailOuvert && WiFi.status() == WL_CONNECTED) {
        portailOuvert = false;
        prochain = 0;
    }

    uint32_t m = millis();
    if (!portailOuvert && (prochain == 0 || (int32_t)(m - prochain) >= 0)) {
        cycle();
        prochain = millis() + PERIODE_MS;
    }
}
