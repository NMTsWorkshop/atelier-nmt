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
import re
import subprocess
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


def voisins():
    """Les machines que le Pi a déjà vues sur le réseau.

    Le système tient cette liste tout seul : chaque appareil avec qui on a
    échangé un paquet y figure. La lire ne coûte rien et ne se remarque
    pas — à la différence d'un balayage, qui ouvre deux cent cinquante
    connexions d'affilée et ressemble à s'y méprendre à un scan de ports.
    Beaucoup de box en ont une détection, et bloquent la machine fautive
    pendant quelques minutes. On a appris ça à nos dépens."""
    vus = []
    for commande in (["ip", "neigh", "show"], ["arp", "-an"]):
        try:
            r = subprocess.run(commande, capture_output=True, text=True, timeout=8)
        except Exception:
            continue
        for ligne in (r.stdout or "").splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", ligne)
            if not m:
                continue
            if "FAILED" in ligne or "INCOMPLETE" in ligne:
                continue
            if m.group(1) not in vus:
                vus.append(m.group(1))
        if vus:
            break
    return vus


def reveiller(reseaux):
    """Un ping large pour que les voisins se fassent connaître.

    Une diffusion par sous-réseau, pas deux cent cinquante connexions :
    les appareils qui répondent entrent dans la table des voisins, et on
    les interroge ensuite un par un."""
    for base in reseaux:
        for adresse in ("%s.255" % base,):
            try:
                subprocess.run(["ping", "-b", "-c", "2", "-W", "1", adresse],
                               capture_output=True, timeout=8)
            except Exception:
                pass


def chercher(cle, c=None, balayer=False):
    """Trouve les multiprises sans se faire prendre pour un scanner."""
    reseaux, moi = reseaux_a_voir(c or {})
    trouvees, refus = [], []

    print("Le Pi est en %s." % moi)
    reveiller(reseaux)
    candidats = [a for a in voisins()
                 if a.rsplit(".", 1)[0] in reseaux and a != moi]
    print("  %d voisin(s) connu(s) sur %s."
          % (len(candidats), ", ".join("%s.0/24" % b for b in reseaux)))
    for hote in candidats:
        genre, d = prises.sonder(hote, cle)
        if genre == "meross":
            trouvees.append(d)
            print("     %-15s %-10s %d sortie(s)  firmware %s  MAC %s"
                  % (hote, d["modele"], len(d["sorties"]), d["firmware"],
                     d["serie"] or "?"))
        elif genre == "sans-cle":
            refus.append(hote)

    if not trouvees and not refus and balayer:
        print()
        print("  Rien parmi les voisins : je balaye, plus lentement.")
        for base in reseaux:
            t, r = chercher_un(base, cle)
            trouvees.extend(t)
            refus.extend(r)
    elif not trouvees and not refus:
        print()
        print("  Rien parmi les voisins connus du Pi.")
        print("  Si les multiprises sont sur un autre Wi-Fi que le Pi (un")
        print("  réseau IoT séparé), elles ne peuvent pas apparaître ici :")
        print('     "prises": { "reseaux": ["10.1.4"], ... } dans relais.json')
        print("  Sinon, pour insister :")
        print("     python3 %s --chercher --balayer"
              % os.path.basename(__file__))
        print("  (ça ouvre beaucoup de connexions d'un coup : certaines box")
        print("   le prennent pour un scan et bloquent le Pi un moment)")
    if refus:
        print()
        print("  %d appareil(s) parlent Meross mais refusent la signature :"
              % len(refus))
        for hote in refus:
            print("     %s" % hote)
        print("  C'est le signe que la clé manque ou ne correspond pas.")
        print("  Lance meross_cle.py, puis reviens ici : ils se présenteront.")
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
        time.sleep(0.02)          # doucement : un scan rapide se fait voir
        if len(fils) >= 16:
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
        trouvees = chercher(cle, c, balayer="--balayer" in sys.argv)
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
            print("      %s, firmware %s, %d sortie(s) physiques, MAC %s"
                  % (d["modele"], d["firmware"], len(d["sorties"]),
                     d["serie"] or "?"))
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
