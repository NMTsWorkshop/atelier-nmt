// Relit nmt_vue.h avec un compilateur, contre les signatures de LVGL 9.3.
//   g++ -std=c++17 -fsyntax-only -I stubs -I ../src vue_syntaxe.cpp
#include "nmt_vue.h"

// Appelle tout, pour qu'aucune fonction ne passe inapercue.
void relire() {
    nmt::Vue v;
    nmt::construire(v);

    std::vector<nmt::Etat> m;
    nmt::Etat e;
    e.nom = "K2 Plus 1";
    e.ok = true;
    e.state = "printing";
    e.fichier = "casque.gcode";
    e.pourcent = 42;
    e.reste = 84;
    e.at = 1763128800000LL;
    m.push_back(e);

    nmt::majMachines(v, m, e.at);
    nmt::majMachines(v, std::vector<nmt::Etat>(), e.at);
    nmt::majServeur(v, true, "serveur 10.1.2.60", e.at);
    nmt::plageTexte(v, "Demarrage", "Connexion au wifi.");
    nmt::carte(v.liste, e, e.at);
}
