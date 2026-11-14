// Lire GET /etat du serveur et en tirer une liste de machines.
//
// Separe de main.cpp pour une raison precise : ce fichier se compile sur un
// PC avec ArduinoJson, donc test/lecture_test.cpp peut lui donner un vrai
// relevé et verifier ce qui en sort. C'est la partie la plus facile a avoir
// subtilement fausse — un nom de champ, une valeur par defaut — et la plus
// penible a debusquer en flashant.
#pragma once

#include <ArduinoJson.h>

#include <algorithm>
#include <string>
#include <vector>

#include "nmt_modele.h"

namespace nmt {

// Le relevé local sert aussi la charge brute des Bambu, qui pese plusieurs
// kilo-octets par machine. On ne garde que ce qu'on affiche : sans ce
// filtre, une Bambu bavarde suffit a epuiser la memoire de l'ESP32.
inline void remplirFiltre(JsonDocument& filtre) {
    filtre["ok"] = true;
    filtre["at"] = true;
    JsonObject m = filtre["machines"]["*"].to<JsonObject>();
    m["nom"] = true;
    m["ok"] = true;
    m["state"] = true;
    m["file"] = true;
    m["percent"] = true;
    m["remaining"] = true;
    m["erreur"] = true;
    m["error"] = true;
    m["staleError"] = true;
    m["stale"] = true;
    m["at"] = true;
}

// Rend l'heure du relevé, et remplit la liste des machines, triee par nom.
inline long long extraire(JsonDocument& doc, std::vector<Etat>& out) {
    long long at = doc["at"] | 0LL;

    JsonObject machines = doc["machines"].as<JsonObject>();
    for (JsonPair kv : machines) {
        JsonObject o = kv.value().as<JsonObject>();
        Etat e;
        e.nom = (const char*)(o["nom"] | kv.key().c_str());
        e.ok = o["ok"] | false;
        e.state = (const char*)(o["state"] | "");
        e.fichier = (const char*)(o["file"] | "");
        e.stale = o["stale"] | false;
        e.pourcent = o["percent"] | -1;
        e.reste = o["remaining"] | -1;
        e.at = o["at"] | 0LL;
        // Le serveur nomme « erreur » ce qui vient de la machine, « error »
        // ce qui vient de la lecture, et « staleError » la raison pour
        // laquelle il republie une lecture datee.
        const char* er = o["erreur"] | o["error"] | o["staleError"] | "";
        e.erreur = er;
        out.push_back(e);
    }

    // Un ecran mural ou les machines changent de place est illisible. Le tri
    // par nom rend l'ordre independant de l'ordre de reponse du serveur.
    std::sort(out.begin(), out.end(),
              [](const Etat& a, const Etat& b) { return a.nom < b.nom; });
    return at;
}

}  // namespace nmt
