# -*- coding: utf-8 -*-
"""Le verrou général du courant, dans relais.json.

    python3 courant.py            # dit dans quel sens il est
    python3 courant.py --fermer   # le relais ne commandera plus aucune prise
    python3 courant.py --ouvrir   # il les commande à nouveau

Pourquoi ce verrou existe : deux soirs de suite, une mise à jour du relais
a coupé des machines en train d'imprimer. Tant qu'on ne sait pas exactement
ce qui les a coupées, il faut pouvoir remettre le relais en service sans
lui laisser la main sur le courant — le délai de fabrication, la boutique,
la bibliothèque et les lumières continuent, les prises sont lues et
affichées, et rien ne les commande.

Fermer le verrou n'efface aucun réglage : la correspondance prise par
prise reste écrite dans relais.json, intacte, et l'ouvrir la remet en
service telle quelle.
"""

import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.environ.get("RELAIS_JSON", os.path.join(ICI, "relais.json"))


def lire():
    with open(CHEMIN, encoding="utf-8-sig") as f:
        return json.load(f)


def ecrire(c):
    """Écriture atomique, et les droits d'origine. Le fichier contient la
    clé Meross et le jeton de la boutique : il ne s'ouvre pas en grand
    parce qu'on a touché à un booléen."""
    provisoire = CHEMIN + ".tmp"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
        f.write("\n")
    try:
        os.chmod(provisoire, 0o600)
    except OSError:
        pass
    os.replace(provisoire, CHEMIN)


def etat(c):
    prises = c.get("prises") or {}
    if not prises.get("barrettes"):
        return None          # aucune multiprise déclarée : rien à verrouiller
    return prises.get("courant") is not False


def dire(ouvert):
    if ouvert is None:
        print("Aucune multiprise n'est déclarée dans relais.json :")
        print("il n'y a pas de courant à verrouiller.")
        return
    if ouvert:
        print("Le courant est COMMANDABLE depuis l'app.")
        print("Les boutons « Tout couper » et « Couper le courant » répondent.")
    else:
        print("Le courant est VERROUILLÉ.")
        print("Le relais lit l'état des prises et l'app l'affiche,")
        print("mais aucun ordre de courant ne sera exécuté.")
        print("Les lumières, le délai de fabrication, la boutique et la")
        print("bibliothèque marchent normalement.")


def main():
    if not os.path.exists(CHEMIN):
        print("relais.json introuvable (%s)." % CHEMIN, file=sys.stderr)
        return 2
    c = lire()
    ouvert = etat(c)

    if "--fermer" not in sys.argv and "--ouvrir" not in sys.argv:
        dire(ouvert)
        return 0

    if ouvert is None:
        dire(None)
        return 0

    voulu = "--ouvrir" in sys.argv
    if voulu == ouvert:
        print("C'était déjà le cas, rien n'a été touché.")
        dire(ouvert)
        return 0

    c.setdefault("prises", {})["courant"] = bool(voulu)
    ecrire(c)

    # on relit le fichier écrit, plutôt que de faire confiance à la variable :
    # un verrou qu'on croit fermé et qui ne l'est pas serait pire que rien
    relu = etat(lire())
    if relu != voulu:
        print("Le fichier n'a pas pris la valeur attendue — rien de sûr ici.",
              file=sys.stderr)
        return 1
    print("Fait.")
    dire(relu)
    print("")
    print("À prendre en compte au prochain démarrage du relais :")
    print("  sudo systemctl restart relais-atelier@nmtsworkshop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
