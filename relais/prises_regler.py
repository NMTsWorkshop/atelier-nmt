#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remplir le bloc « prises » de relais.json sans ouvrir un éditeur.

On demande aux multiprises ce qu'elles ont comme sorties, on propose pour
chacune les machines que le relais connaît déjà, et on écrit le fichier.
Personne n'a à compter des accolades à minuit.

    python3 /opt/relais-atelier/prises_regler.py 10.1.3.5 10.1.3.6 10.1.3.22

Sans adresses, il reprend celles déjà dans relais.json.

Le verrou n'est pas négociable : une sortie qui ne porte pas un nom de
machine n'est pas commandable, et celle qui alimente le Pi encore moins.
Le but de cet écran est justement de ne pas se tromper sur ce point-là.
"""

import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import prises                                              # noqa: E402

CHEMIN = os.path.join(ICI, "relais.json")

ROLES = [
    ("pi", "le Raspberry Pi lui-même"),
    ("switch", "le switch réseau"),
    ("bloc", "le bloc qui alimente tout"),
    ("autre", "autre chose (verrouillé)"),
]


def lire():
    with open(CHEMIN, encoding="utf-8-sig") as f:
        return json.load(f)


def ecrire(c):
    with open(CHEMIN + ".tmp", "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    os.chmod(CHEMIN + ".tmp", 0o600)
    os.replace(CHEMIN + ".tmp", CHEMIN)


def demander(question, defaut=""):
    rep = input(question).strip()
    return rep or defaut


def choisir(sortie, machines, deja):
    """Ce qu'il y a au bout de cette sortie. Renvoie le dict à écrire."""
    print()
    print("   Sortie %d — %s"
          % (sortie["canal"], "allumée" if sortie["allumee"] else "éteinte"))
    # La liste ne bouge pas d'une sortie à l'autre : les numéros restent
    # les mêmes du début à la fin. Une liste qui rétrécit à mesure qu'on
    # choisit, c'est la garantie de taper 3 en pensant à autre chose.
    options = [("machine", m, m) for m in machines]
    options += [("role", cle, texte) for cle, texte in ROLES]
    for i, (genre, valeur, texte) in enumerate(options, 1):
        if genre == "machine":
            marque = "   (déjà prise)" if valeur in deja else ""
        else:
            marque = "   (verrouillée)"
        print("     %2d. %s%s" % (i, texte, marque))
    print("      0. laisser vide (verrouillée)")

    while True:
        rep = demander("     Qu'y a-t-il au bout ? [0] : ", "0")
        if rep == "0":
            return {"canal": sortie["canal"]}
        try:
            genre, valeur, _ = options[int(rep) - 1]
        except (ValueError, IndexError):
            print("     Réponds par un des numéros ci-dessus.")
            continue
        if genre == "machine":
            if valeur in deja:
                print("     %s est déjà sur une autre prise." % valeur)
                continue
            deja.add(valeur)
            return {"canal": sortie["canal"], "machine": valeur}
        return {"canal": sortie["canal"], "role": valeur}


def main():
    c = lire()
    p = c.get("prises")
    if not isinstance(p, dict):
        p = {}
    cle = p.get("cle") or ""
    if not cle or "A-REMPLIR" in cle:
        print("La clé Meross manque dans relais.json.")
        print("Lance d'abord :  python3 %s/meross_cle.py" % ICI)
        return 2

    hotes = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not hotes:
        hotes = [b.get("hote") for b in (p.get("barrettes") or []) if b.get("hote")]
    if not hotes:
        print("Aucune adresse de multiprise. Donne-les en argument :")
        print("   python3 %s 10.1.3.5 10.1.3.6" % os.path.basename(__file__))
        return 2

    machines = [m.get("nom") for m in (c.get("machines") or []) if m.get("nom")]
    deja = set()
    barrettes = []

    print("=" * 62)
    print("   Qui est au bout de quelle prise")
    print("=" * 62)

    for hote in hotes:
        print()
        print("%s …" % hote)
        try:
            d = prises.decrire(hote, cle)
        except Exception as e:
            print("   injoignable : %s" % str(e)[:120])
            print("   (je la garde dans le fichier, sans sorties)")
            barrettes.append({"nom": hote, "hote": hote, "sorties": []})
            continue
        print("   %s, firmware %s, %d sortie(s)"
              % (d["modele"], d["firmware"], len(d["sorties"])))
        nom = demander("   Comment l'appeler ? [%s] : " % hote, hote)
        sorties = [choisir(s, machines, deja) for s in d["sorties"]]
        barrettes.append({"nom": nom, "hote": hote, "sorties": sorties})

    p["barrettes"] = barrettes
    c["prises"] = p
    ecrire(c)

    print()
    print("=" * 62)
    commandables = [s for b in barrettes for s in b["sorties"]
                    if not prises.Parc.verrouillee(s)]
    print("Écrit. %d sortie(s) commandable(s) depuis l'app, le reste est "
          "verrouillé." % len(commandables))
    for b in barrettes:
        for s in b["sorties"]:
            quoi = s.get("machine") or s.get("role") or "—"
            print("   %-14s canal %-2d  %-18s %s"
                  % (b["nom"], s["canal"], quoi,
                     "" if not prises.Parc.verrouillee(s) else "verrouillée"))
    print()
    print("Pour que le relais le prenne en compte :")
    print("   sudo systemctl restart relais-atelier@$USER")
    return 0


if __name__ == "__main__":
    sys.exit(main())
