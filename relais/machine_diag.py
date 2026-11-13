# -*- coding: utf-8 -*-
"""Qu'est-ce que cette machine expose, au juste ?

    python3 machine_diag.py 10.1.3.24

Le relais sait parler à deux choses : Moonraker, sur le port 7125, et le
MQTT local des Bambu, sur 8883. Quand une machine neuve ne répond ni à
l'un ni à l'autre, « injoignable » ne dit pas si elle est éteinte, sur un
autre réseau, derrière un pare-feu, ou simplement en train de servir son
interface ailleurs — les Creality récentes n'exposent pas toutes Moonraker
de la même façon.

Ce script ne suppose rien : il frappe à toutes les portes connues et
raconte qui répond. Il ne modifie rien, ni ici ni sur la machine.
"""

import json
import socket
import ssl
import sys
import urllib.error
import urllib.request

DELAI = 3

# Les ports qu'on a déjà vus servir à quelque chose sur une imprimante.
PORTES = [
    (80, "interface web"),
    (443, "interface web en TLS"),
    (4408, "interface web Creality (K1 et suivantes)"),
    (7125, "Moonraker — ce que le relais sait lire"),
    (7126, "Moonraker, variante"),
    (8080, "interface web, variante"),
    (8081, "flux caméra"),
    (8000, "flux caméra, variante"),
    (8883, "MQTT en TLS — les Bambu"),
    (1883, "MQTT en clair"),
    (3031, "service d'impression Creality"),
    (9999, "API locale Creality"),
    (22, "SSH"),
]

# Ce qu'on demande à un port qui parle HTTP, pour savoir qui il est.
CHEMINS = [
    ("/printer/info", "Moonraker"),
    ("/server/info", "Moonraker"),
    ("/machine/system_info", "Moonraker"),
    ("/", "une interface web"),
]


def ouvert(hote, port):
    s = socket.socket()
    s.settimeout(DELAI)
    try:
        s.connect((hote, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def interroger(hote, port, chemin, tls=False):
    """Renvoie (code, début de la réponse) ou None."""
    url = "%s://%s:%d%s" % ("https" if tls else "http", hote, port, chemin)
    ctx = None
    if tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=DELAI, context=ctx) as r:
            return r.status, r.read(600).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            corps = e.read(300).decode("utf-8", "replace")
        except Exception:
            corps = ""
        return e.code, corps
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage : python3 machine_diag.py <adresse IP>", file=sys.stderr)
        return 2
    hote = sys.argv[1].strip()

    print("")
    print("=== Que répond %s ? ===" % hote)
    print("")
    print("Rien n'est modifié, ni ici ni sur la machine.")
    print("")

    trouves = []
    for port, quoi in PORTES:
        if ouvert(hote, port):
            trouves.append((port, quoi))
            print("  %-6d ouvert    %s" % (port, quoi))
        else:
            print("  %-6d ferme" % port)

    if not trouves:
        print("")
        print("Aucun port ouvert. Trois causes possibles, dans cet ordre :")
        print("  - la machine est eteinte ou pas encore sur le reseau ;")
        print("  - l'adresse n'est pas la bonne, ou elle a change en DHCP ;")
        print("  - un pare-feu separe ce serveur du reseau de la machine.")
        print("")
        print("Le ping dira laquelle : ping %s" % hote)
        return 1

    print("")
    print("--- Ce que disent les ports qui parlent HTTP ---")
    for port, _quoi in trouves:
        if port in (22, 8883, 1883):
            continue
        tls = port == 443
        for chemin, qui in CHEMINS:
            dit = interroger(hote, port, chemin, tls)
            if dit is None:
                continue
            code, corps = dit
            apercu = " ".join(corps.split())[:140]
            print("")
            print("  %d%s  ->  %s" % (port, chemin, code))
            if apercu:
                print("    %s" % apercu)
            if code == 200 and chemin.startswith("/printer/info"):
                try:
                    info = (json.loads(corps).get("result") or {})
                    print("")
                    print("    C'est Moonraker : %s, Klipper %s"
                          % (info.get("hostname") or "?",
                             info.get("software_version") or "?"))
                    print("    Le relais sait lire cette machine. Declare-la en")
                    print("    type « moonraker » sur le port %d." % port)
                except ValueError:
                    pass
                break
            if code == 200:
                break

    print("")
    print("--- Lecture ---")
    ports = [p for p, _ in trouves]
    if 7125 in ports:
        print("  Moonraker est la : rien de special a faire.")
    elif 8883 in ports:
        print("  C'est une Bambu : type « bambu », avec son numero de serie et")
        print("  son code d'acces LAN.")
    elif 4408 in ports or 80 in ports or 8080 in ports:
        print("  Elle sert une interface web mais pas Moonraker sur 7125.")
        print("  Sur les Creality recentes, Moonraker n'est parfois accessible")
        print("  qu'apres avoir active le mode developpeur ou root sur l'ecran")
        print("  de la machine. Cherche ca dans ses reglages reseau.")
        print("  Copie cette sortie a Claude : les reponses ci-dessus disent")
        print("  quelle API elle expose, et il verra si le relais peut l'apprendre.")
    else:
        print("  Des ports ouverts, mais aucun que le relais sache lire.")
        print("  Copie cette sortie a Claude.")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
