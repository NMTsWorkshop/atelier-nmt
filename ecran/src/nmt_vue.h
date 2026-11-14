// L'ecran, dessine a la charte de l'app : meme palette, memes rayons, meme
// facon de ne rien affirmer qu'on ne sache pas.
//
// Un ecran de 800x480, une seule page, aucun menu. Un bandeau en haut pour
// le serveur, et une carte par machine en dessous. On ne peut pas se perdre
// dedans parce qu'il n'y a nulle part ou aller.
#pragma once

#include <lvgl.h>

#include <string>
#include <vector>

#include "nmt_modele.h"

namespace nmt {

// 800x480 : un bandeau de 44, puis cinq cartes de 80 espacees de 8.
const int LARGEUR = 800;
const int HAUTEUR = 480;
const int BANDEAU = 44;
const int CARTE_H = 80;

inline lv_color_t coul(unsigned long hex) { return lv_color_hex((uint32_t)hex); }

struct Vue {
    lv_obj_t* racine = nullptr;
    lv_obj_t* pastilleServeur = nullptr;
    lv_obj_t* texteServeur = nullptr;
    lv_obj_t* heure = nullptr;
    lv_obj_t* liste = nullptr;
};

inline void styleFond(lv_obj_t* o, unsigned long fond, unsigned long bord,
                      int rayon) {
    lv_obj_set_style_bg_color(o, coul(fond), 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(o, coul(bord), 0);
    lv_obj_set_style_border_width(o, bord ? 1 : 0, 0);
    lv_obj_set_style_radius(o, rayon, 0);
    lv_obj_set_style_pad_all(o, 0, 0);
}

inline lv_obj_t* libelle(lv_obj_t* parent, const char* txt,
                         const lv_font_t* police, unsigned long couleur) {
    lv_obj_t* l = lv_label_create(parent);
    lv_label_set_text(l, txt);
    lv_obj_set_style_text_font(l, police, 0);
    lv_obj_set_style_text_color(l, coul(couleur), 0);
    return l;
}

// --- construction ------------------------------------------------------

inline void construire(Vue& v) {
    lv_obj_t* ec = lv_screen_active();
    lv_obj_set_style_bg_color(ec, coul(Couleurs::bg), 0);
    lv_obj_set_style_bg_opa(ec, LV_OPA_COVER, 0);
    lv_obj_remove_flag(ec, LV_OBJ_FLAG_SCROLLABLE);

    v.racine = ec;

    // Le bandeau : l'etat du serveur, et l'heure du dernier releve. C'est la
    // seule chose qui dit si tout le reste est digne de foi.
    lv_obj_t* haut = lv_obj_create(ec);
    lv_obj_set_size(haut, LARGEUR, BANDEAU);
    lv_obj_set_pos(haut, 0, 0);
    styleFond(haut, Couleurs::bg, 0, 0);
    lv_obj_remove_flag(haut, LV_OBJ_FLAG_SCROLLABLE);

    v.pastilleServeur = lv_obj_create(haut);
    lv_obj_set_size(v.pastilleServeur, 10, 10);
    lv_obj_set_pos(v.pastilleServeur, 16, 17);
    styleFond(v.pastilleServeur, Couleurs::txt3, 0, 5);

    v.texteServeur = libelle(haut, "demarrage", &lv_font_montserrat_14,
                             Couleurs::txt2);
    lv_obj_set_pos(v.texteServeur, 34, 15);

    v.heure = libelle(haut, "--:--", &lv_font_montserrat_14, Couleurs::txt3);
    lv_obj_align(v.heure, LV_ALIGN_TOP_RIGHT, -16, 15);

    // La liste defile : cinq machines tiennent a l'ecran, une sixieme se
    // trouve en poussant. Mieux que de les retrecir toutes.
    v.liste = lv_obj_create(ec);
    lv_obj_set_size(v.liste, LARGEUR, HAUTEUR - BANDEAU);
    lv_obj_set_pos(v.liste, 0, BANDEAU);
    styleFond(v.liste, Couleurs::bg, 0, 0);
    lv_obj_set_style_pad_all(v.liste, 8, 0);
    lv_obj_set_style_pad_row(v.liste, 8, 0);
    lv_obj_set_flex_flow(v.liste, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_scroll_dir(v.liste, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(v.liste, LV_SCROLLBAR_MODE_OFF);
}

// --- une carte de machine ----------------------------------------------

inline void carte(lv_obj_t* parent, const Etat& e, long long maintenantMs) {
    const bool vieux = e.stale || perime(maintenantMs, e.at);
    const bool crie = demandeAttention(e);
    const unsigned long teinte = vieux ? Couleurs::warn : etatCouleur(e);

    lv_obj_t* c = lv_obj_create(parent);
    lv_obj_set_size(c, LARGEUR - 16, CARTE_H);
    styleFond(c, Couleurs::card, crie ? teinte : Couleurs::line, 14);
    if (crie) lv_obj_set_style_border_width(c, 2, 0);
    lv_obj_remove_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(c, LV_OBJ_FLAG_EVENT_BUBBLE);

    lv_obj_t* point = lv_obj_create(c);
    lv_obj_set_size(point, 14, 14);
    lv_obj_set_pos(point, 16, 15);
    styleFond(point, teinte, 0, 7);

    lv_obj_t* nom = libelle(c, e.nom.c_str(), &lv_font_montserrat_20,
                            Couleurs::txt);
    lv_obj_set_pos(nom, 40, 12);

    // Sous le nom : le fichier s'il imprime, sinon ce qu'elle fait. Et si la
    // lecture date, c'est ca qu'on dit a la place — un chiffre qui a l'air
    // frais alors qu'il a vingt minutes, c'est ce qui fait perdre confiance.
    std::string dessous;
    unsigned long couleurDessous = Couleurs::txt2;
    if (vieux) {
        dessous = fraicheurTexte(maintenantMs, e.at);
        couleurDessous = Couleurs::warn;
    } else if (!e.ok || e.state == "failed") {
        dessous = etatTexte(e);
        couleurDessous = e.ok ? Couleurs::bad : Couleurs::warn;
    } else if (e.fichier.size()) {
        dessous = e.fichier;
    } else {
        dessous = etatTexte(e);
        couleurDessous = Couleurs::txt3;
    }

    lv_obj_t* sous = libelle(c, dessous.c_str(), &lv_font_montserrat_14,
                             couleurDessous);
    lv_obj_set_width(sous, 430);
    lv_label_set_long_mode(sous, LV_LABEL_LONG_MODE_DOTS);
    lv_obj_set_pos(sous, 40, 42);

    // A droite : le temps restant en gros, l'heure de fin en dessous. C'est
    // ce qu'on vient lire de loin.
    const bool compte = e.ok && !vieux
                        && (e.state == "printing" || e.state == "paused")
                        && e.reste >= 0;

    lv_obj_t* gros = libelle(c, compte ? dureeTexte(e.reste).c_str()
                                       : etatTexte(e).c_str(),
                             compte ? &lv_font_montserrat_28
                                    : &lv_font_montserrat_20,
                             compte ? Couleurs::txt : teinte);
    lv_obj_align(gros, LV_ALIGN_TOP_RIGHT, -16, compte ? 10 : 16);

    if (compte) {
        std::string fin = heureFin(e.at, e.reste);
        if (fin.size()) {
            std::string t = "fin " + fin;
            lv_obj_t* f = libelle(c, t.c_str(), &lv_font_montserrat_14,
                                  Couleurs::txt3);
            lv_obj_align(f, LV_ALIGN_TOP_RIGHT, -16, 46);
        }
    }

    // La barre d'avancement ne se dessine que si on connait l'avancement.
    if (e.ok && !vieux && e.pourcent >= 0
        && (e.state == "printing" || e.state == "paused")) {
        lv_obj_t* fond = lv_obj_create(c);
        lv_obj_set_size(fond, LARGEUR - 48, 4);
        lv_obj_set_pos(fond, 16, CARTE_H - 16);
        styleFond(fond, Couleurs::line, 0, 2);
        lv_obj_remove_flag(fond, LV_OBJ_FLAG_SCROLLABLE);

        int l = (LARGEUR - 48) * (e.pourcent > 100 ? 100 : e.pourcent) / 100;
        if (l > 0) {
            lv_obj_t* barre = lv_obj_create(fond);
            lv_obj_set_size(barre, l, 4);
            lv_obj_set_pos(barre, 0, 0);
            styleFond(barre, teinte, 0, 2);
            lv_obj_remove_flag(barre, LV_OBJ_FLAG_SCROLLABLE);
        }
    }
}

// --- mise a jour -------------------------------------------------------

// On refait les cartes a chaque releve au lieu de les modifier. Cinq cartes
// toutes les cinq secondes, LVGL n'en souffre pas, et ca supprime d'un coup
// toute une famille de bugs ou l'affichage garde un morceau de l'etat
// precedent.
inline void majMachines(Vue& v, const std::vector<Etat>& machines,
                        long long maintenantMs) {
    lv_obj_clean(v.liste);
    if (machines.empty()) {
        lv_obj_t* rien = libelle(v.liste, "aucune machine declaree sur le serveur",
                                 &lv_font_montserrat_14, Couleurs::txt3);
        lv_obj_set_pos(rien, 8, 8);
        return;
    }
    for (size_t i = 0; i < machines.size(); i++) carte(v.liste, machines[i], maintenantMs);
}

inline void majServeur(Vue& v, bool joignable, const std::string& dit,
                       long long atReleve) {
    styleFond(v.pastilleServeur, joignable ? Couleurs::ok : Couleurs::bad, 0, 5);
    lv_label_set_text(v.texteServeur, dit.c_str());
    lv_obj_set_style_text_color(v.texteServeur,
                                coul(joignable ? Couleurs::txt2 : Couleurs::bad), 0);
    lv_label_set_text(v.heure, heureDe(atReleve).c_str());
}

// Le message du depart, et celui du portail de reglage.
inline void plageTexte(Vue& v, const std::string& titre,
                       const std::string& detail) {
    lv_obj_clean(v.liste);
    lv_obj_t* boite = lv_obj_create(v.liste);
    lv_obj_set_size(boite, LARGEUR - 16, 200);
    styleFond(boite, Couleurs::card, Couleurs::line, 14);
    lv_obj_remove_flag(boite, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* t = libelle(boite, titre.c_str(), &lv_font_montserrat_20,
                          Couleurs::txt);
    lv_obj_set_pos(t, 24, 24);

    lv_obj_t* d = libelle(boite, detail.c_str(), &lv_font_montserrat_14,
                          Couleurs::txt2);
    lv_obj_set_width(d, LARGEUR - 64);
    lv_label_set_long_mode(d, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_pos(d, 24, 60);
}

}  // namespace nmt
