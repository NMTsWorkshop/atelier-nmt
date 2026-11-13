# -*- coding: utf-8 -*-
"""Le parc de machines dans relais.json, sans éditeur de texte.

    python3 machines_regler.py            # liste et propose d'ajouter
    python3 machines_regler.py --lister    # liste seulement

Pourquoi un script : relais.json contient la clé Meross et le jeton de la
boutique. Chaque ouverture dans nano est une occasion de casser le JSON ou
d'élargir les droits du fichier. Et surtout, il interroge la machine au
lieu de supposer — une Creality récente parle Moonraker, mais c'est à elle
de le dire, pas à nous de le parier.

La famille décide quels fichiers vont à cette machine. Deux machines de la
même famille se partagent les gcodes, et deux machines différentes ne
doivent surtout pas : une H2S parle Moonraker comme une K2 Plus, et son
gcode n'a rien à voir — volume, buses, plateau.
"""

import json
import os
import socket
import sys
import urllib.error
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.environ.get("RELAIS_JSON", os.path.join(ICI, "relais.json"))
DELAI = 5


def lire():
    with open(CHEMIN, encoding="utf-8-sig") as f:
        return json.load(f)


def ecrire(c):
    """Écriture atomique, et les droits d'origine."""
    provisoire = CHEMIN + ".tmp"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
        f.write("\n")
    try:
        os.chmod(provisoire, 0o600)
    except OSError:
        pass
    os.replace(provisoire, CHEMIN)


def famille_de(m):
    f = str(m.get("famille") or "").strip().lower()
    if f:
        return f
    return "k2" if m.get("type") == "moonraker" else "p1s"


def lister(c):
    machines = c.get("machines") or []
    if not machines:
        print("Aucune machine déclarée.")
        return
    print("Machines déclarées :")
    for i, m in enumerate(machines, 1):
        print("  %d. %-16s %-10s %-15s famille %s"
              % (i, m.get("nom") or "?", m.get("type") or "?",
                 m.get("hote") or "?", famille_de(m)))
    familles = []
    for m in machines:
        f = famille_de(m)
        if f not in familles:
            familles.append(f)
    print("")
    print("Dossiers de gcodes utilisés : %s" % ", ".join(familles))


def sonder_moonraker(hote):
    """Ce que la machine répond sur le port de Moonraker, ou None."""
    url = "http://%s:7125/printer/info" % hote
    try:
        with urllib.request.urlopen(url, timeout=DELAI) as r:
            dit = json.loads(r.read().decode("utf-8", "replace"))
        return dit.get("result") or {}
    except (urllib.error.URLError, socket.timeout, ValueError, OSError):
        return None


def sonder_port(hote, port):
    s = socket.socket()
    s.settimeout(DELAI)
    try:
        s.connect((hote, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def sonder(hote):
    """Demande à la machine ce qu'elle est. Renvoie (type, ce qu'elle dit)."""
    print("")
    print("On demande à %s..." % hote)

    info = sonder_moonraker(hote)
    if info is not None:
        quoi = info.get("hostname") or "?"
        version = info.get("software_version") or "?"
        print("  Moonraker répond : %s, Klipper %s" % (quoi, version))
        return "moonraker", info

    if sonder_port(hote, 8883):
        print("  Le port MQTT 8883 est ouvert : c'est une Bambu.")
        print("  Il faudra son numéro de série et son code d'accès LAN")
        print("  (écran de l'imprimante : Réglages → Réseau).")
        return "bambu", {}

    if sonder_port(hote, 80):
        print("  Elle répond en HTTP mais pas sur le port 7125 de Moonraker.")
        print("  Son interface web marche peut-être quand même ; le relais,")
        print("  lui, ne saura pas la lire.")
    else:
        print("  Pas de réponse. Vérifie l'adresse, et que la machine est")
        print("  allumée et sur le réseau.")
    return "", {}


def demander(question, defaut=""):
    rep = input("%s%s : " % (question, " [%s]" % defaut if defaut else "")).strip()
    return rep or defaut


def ajouter(c):
    machines = c.setdefault("machines", [])

    hote = demander("Adresse IP de la machine")
    if not hote:
        print("Rien de changé.")
        return False

    deja = [m for m in machines if (m.get("hote") or "") == hote]
    if deja:
        print("")
        print("Cette adresse est déjà déclarée : %s." % (deja[0].get("nom") or "?"))
        if demander("La remplacer ? (o/N)").lower() not in ("o", "oui", "y"):
            return False
        machines[:] = [m for m in machines if (m.get("hote") or "") != hote]

    type_, _info = sonder(hote)
    if not type_:
        print("")
        if demander("L'ajouter quand même, en Moonraker ? (o/N)").lower() \
                not in ("o", "oui", "y"):
            print("Rien de changé.")
            return False
        type_ = "moonraker"

    print("")
    nom = demander("Nom de la machine, tel qu'il apparaîtra dans l'app")
    if not nom:
        print("Rien de changé.")
        return False

    familles = sorted({famille_de(m) for m in machines})
    print("")
    print("La famille décide quels fichiers vont à cette machine.")
    print("Familles existantes : %s" % (", ".join(familles) or "aucune"))
    print("Mets la même qu'une autre machine seulement si leurs gcodes sont")
    print("vraiment interchangeables. Sinon, un nom à toi : il deviendra un")
    print("dossier de la bibliothèque.")
    famille = demander("Famille", nom.split()[0].lower()).strip().lower()

    neuve = {"nom": nom, "type": type_, "hote": hote, "famille": famille}
    if type_ == "bambu":
        serie = demander("Numéro de série")
        code = demander("Code d'accès LAN")
        if serie:
            neuve["serie"] = serie
        if code:
            neuve["code"] = code

    machines.append(neuve)
    ecrire(c)

    print("")
    print("Fait. %s ajoutée, famille « %s »." % (nom, famille))
    print("")
    print("À prendre en compte au prochain démarrage du relais :")
    print("  sudo systemctl restart relais-atelier@nmtsworkshop")
    print("")
    print("Le dossier de la bibliothèque se crée tout seul au démarrage.")
    print("Pense à déclarer la même machine dans l'app, avec la même")
    print("famille — sinon elle ne saura pas à qui envoyer les fichiers.")
    return True


def main():
    if not os.path.exists(CHEMIN):
        print("relais.json introuvable (%s)." % CHEMIN, file=sys.stderr)
        return 2
    c = lire()
    lister(c)
    if "--lister" in sys.argv:
        return 0
    print("")
    if demander("Ajouter une machine ? (o/N)").lower() in ("o", "oui", "y"):
        ajouter(c)
    else:
        print("Rien de changé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
