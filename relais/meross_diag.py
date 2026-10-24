#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Les multiprises répondent-elles au relais, et laquelle pilote quoi ?

Se lance sur le Pi, ne demande aucun droit particulier, ne change rien :

    python3 /opt/relais-atelier/meross_diag.py            # relais.json
    python3 /opt/relais-atelier/meross_diag.py --chercher # balaye le réseau

Il répond à trois questions, dans l'ordre où elles se posent vraiment :

 1. où sont les multiprises sur le réseau
 2. est-ce que la clé de relais.json leur convient
 3. quelle sortie commande quoi — et on le montre en le faisant clignoter
    plutôt qu'en le devinant

La troisième est la seule qui agit, et seulement si on la demande.
"""

import json
import os
import socket
import sys
import threading
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import prises                                              # noqa: E402

PORT = 80
DELAI_SCAN = 0.35


def reglages():
    chemin = os.path.join(ICI, "relais.json")
    try:
        with open(chemin, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print("relais.json illisible : %s" % e)
        return {}


def mon_reseau():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip.rsplit(".", 1)[0], ip


def reseaux_a_voir(c):
    """Tous les /24 où une multiprise peut se trouver.

    Celui du Pi, et ceux des machines : l'atelier n'est pas forcément sur un
    seul sous-réseau, et les objets connectés sont souvent mis à part. Ne
    chercher que là où on est, c'est trouver seulement ce qui est déjà sous
    la main."""
    base, moi = mon_reseau()
    vus = [base]
    for m in (c.get("machines") or []):
        h = str(m.get("hote") or "")
        if h.count(".") == 3:
            b = h.rsplit(".", 1)[0]
            if b not in vus:
                vus.append(b)
    for b in (c.get("prises") or {}).get("reseaux") or []:
        if b not in vus:
            vus.append(b)
    return vus, moi


def repond(hote, delai=DELAI_SCAN):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(delai)
    try:
        return s.connect_ex((hote, PORT)) == 0
    finally:
        s.close()


def chercher(cle, c=None):
    """Balaye les sous-réseaux plausibles et garde ce qui parle Meross."""
    reseaux, moi = reseaux_a_voir(c or {})
    print("Le Pi est en %s. Je balaye : %s"
          % (moi, ", ".join("%s.0/24" % b for b in reseaux)))
    trouvees, refus = [], []
    for base in reseaux:
        t, r = chercher_un(base, cle)
        trouvees.extend(t)
        refus.extend(r)
    if refus:
        print()
        print("  %d appareil(s) parlent Meross mais refusent la signature :"
              % len(refus))
        for hote in refus:
            print("     %s" % hote)
        print("  C'est le signe que la clé manque ou ne correspond pas.")
        print("  Lance meross_cle.py, puis reviens ici : ils se présenteront.")
    if not trouvees and not refus:
        print()
        print("  Aucune multiprise trouvée sur ces sous-réseaux.")
        print("  Si elles sont sur un autre Wi-Fi que le Pi (un réseau IoT")
        print("  séparé, par exemple), ajoute son préfixe dans relais.json :")
        print('     "prises": { "reseaux": ["10.1.4"], ... }')
    return trouvees


def chercher_un(base, cle):
    print()
    print("  %s.0/24 …" % base)
    ouverts = []
    verrou = threading.Lock()

    def essayer(n):
        hote = "%s.%d" % (base, n)
        if repond(hote):
            with verrou:
                ouverts.append(hote)

    fils = []
    for n in range(1, 255):
        f = threading.Thread(target=essayer, args=(n,), daemon=True)
        f.start()
        fils.append(f)
        if len(fils) >= 64:
            for x in fils:
                x.join()
            fils = []
    for x in fils:
        x.join()

    print("     %d appareil(s) écoutent sur le port 80." % len(ouverts))
    trouvees, refus = [], []
    for hote in sorted(ouverts, key=lambda a: int(a.rsplit(".", 1)[1])):
        genre, d = prises.sonder(hote, cle)
        if genre == "meross":
            trouvees.append(d)
            print("     %-15s %-10s %d sortie(s)  firmware %s"
                  % (hote, d["modele"], len(d["sorties"]), d["firmware"]))
        elif genre == "sans-cle":
            refus.append(hote)
    return trouvees, refus


def montrer(barrettes, cle):
    """Fait clignoter chaque sortie l'une après l'autre.

    C'est la seule façon honnête de savoir quelle prise porte quelle
    machine : on la coupe une seconde et on regarde ce qui s'éteint."""
    print()
    print("ATTENTION : chaque sortie va être coupée une seconde, l'une après")
    print("l'autre. Ne lance pas ça pendant une impression.")
    rep = input("Continuer ? (o/N) ").strip().lower()
    if rep not in ("o", "oui", "y"):
        print("Rien touché.")
        return
    for b in barrettes:
        for s in b.get("sorties") or []:
            canal = int(s.get("canal", 0))
            quoi = s.get("machine") or s.get("role") or "?"
            if str(s.get("role") or "").lower() in prises.VERROUS:
                print("  canal %d (%s) : verrouillé, on n'y touche pas" % (canal, quoi))
                continue
            print("  canal %d (%s) — regarde ce qui s'éteint…" % (canal, quoi))
            try:
                prises.basculer(b["hote"], canal, False, cle)
                time.sleep(1.2)
                prises.basculer(b["hote"], canal, True, cle)
            except Exception as e:
                print("    raté : %s" % e)
            time.sleep(0.8)


def main():
    c = reglages()
    p = (c.get("prises") or {})
    cle = p.get("cle") or ""
    barrettes = p.get("barrettes") or []

    print("=" * 64)
    print("   Les multiprises et le relais")
    print("=" * 64)
    print()

    print("1. La clé")
    if not cle or "A-REMPLIR" in cle:
        print("   absente de relais.json (prises.cle).")
        print("   Sans elle les multiprises refuseront tout — voir le README,")
        print("   section « la clé Meross ».")
    else:
        print("   présente (%d caractères)." % len(cle))
    print()

    if "--chercher" in sys.argv:
        print("2. Qui est sur le réseau")
        if not cle or "A-REMPLIR" in cle:
            print("   Sans clé, aucune multiprise ne peut se présenter : elles")
            print("   répondent mais refusent de parler. Le balayage dira")
            print("   lesquelles refusent — c'est déjà les avoir trouvées.")
        trouvees = chercher(cle, c)
        print()
        if trouvees and not barrettes:
            print("   À recopier dans relais.json, sous \"prises\" :")
            modele = {"cle": cle or "A-REMPLIR", "barrettes": [
                {"nom": d["hote"], "hote": d["hote"],
                 "sorties": [{"canal": s["canal"], "machine": "A-REMPLIR"}
                             for s in d["sorties"]]}
                for d in trouvees]}
            print(json.dumps(modele, ensure_ascii=False, indent=2))
        return 0

    print("2. Ce que relais.json décrit")
    if not barrettes:
        print("   aucune multiprise. Relance avec --chercher pour les trouver.")
        return 0
    for b in barrettes:
        print("   %s (%s)" % (b.get("nom") or "?", b.get("hote")))
        try:
            d = prises.decrire(b["hote"], cle)
            vus = {s["canal"]: s["allumee"] for s in d["sorties"]}
            print("      %s, firmware %s, %d sortie(s) physiques"
                  % (d["modele"], d["firmware"], len(d["sorties"])))
        except Exception as e:
            print("      INJOIGNABLE : %s" % e)
            continue
        for s in b.get("sorties") or []:
            canal = int(s.get("canal", 0))
            quoi = s.get("machine") or s.get("role") or "?"
            etat = vus.get(canal)
            marque = " [verrouillée]" if str(s.get("role") or "").lower() in prises.VERROUS else ""
            print("      canal %-2d %-18s %s%s"
                  % (canal, quoi,
                     "allumée" if etat else ("éteinte" if etat is not None else "?"),
                     marque))
    print()

    if "--montrer" in sys.argv:
        montrer(barrettes, cle)
    else:
        print("Pour savoir quelle prise porte quelle machine :")
        print("   python3 %s --montrer" % os.path.basename(__file__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
