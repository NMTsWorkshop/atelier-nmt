# -*- coding: utf-8 -*-
"""Remettre d'aplomb ce qui s'est coincé, sans aller débrancher.

Le symptôme le plus courant n'est pas une panne : le Pi répond, il est
allumé, mais le partage de fichiers ne répond plus depuis Windows. Couper
le courant règle ça — c'est aussi le seul geste qu'on ne peut pas annuler à
distance, et il tombe à l'aveugle sur un disque qui est peut-être en train
d'écrire. Alors on commence par le plus petit geste qui règle le cas, et le
redémarrage complet reste en dernier.

Trois gestes, du plus doux au plus brutal :

    partage   relance smbd — celui qui règle « je ne vois plus les fichiers »
    relais    relance le service du relais lui-même
    pi        redémarre la machine entière

Les deux derniers coupent le relais en route, et c'est lui qui répond à
l'app. L'accusé de réception doit donc partir AVANT : sinon l'app conclut
au silence et annonce que l'ordre n'est pas passé, alors qu'il est passé.
D'où le mécanisme en deux temps — on note ce qu'il y a à faire, la relève
publie, et seulement après la machine s'en va.

Le relais n'a pas besoin des droits root pour se relancer lui-même : son
service est en Restart=always, il lui suffit de sortir. Les deux autres
gestes passent par sudo, sur une règle qui ne permet que ces commandes-là.
"""

import os
import subprocess
import threading
import time

VERROU = threading.RLock()

# La sortie du programme, remplaçable : le test de bout en bout vérifie que
# le relais s'en va bien au bon moment, et il ne peut pas le faire s'il s'en
# va vraiment.
def _sortir(code):
    os._exit(code)


SORTIE = _sortir

# Ce qui reste à faire une fois la relève publiée. Un seul geste à la fois :
# deux redémarrages demandés coup sur coup, c'est le même redémarrage.
EN_ATTENTE = {}

SERVICE_PARTAGE = "smbd"

AIDE_SUDO = ("le Pi demande un mot de passe pour ça — lance pi-13-sans-mdp.bat "
             "sur le PC, il autorise ces commandes-là et rien d'autre")


def _courir(commande, delai=25):
    """(ok, ce qu'il faut en dire). Jamais d'exception : un geste
    d'entretien qui échoue doit se raconter, pas faire tomber la boucle."""
    try:
        r = subprocess.run(commande, capture_output=True, text=True, timeout=delai)
    except FileNotFoundError:
        return False, "commande introuvable sur le Pi : %s" % commande[0]
    except subprocess.TimeoutExpired:
        return False, "pas de réponse au bout de %d s" % delai
    except Exception as e:
        return False, str(e)[:120]
    if r.returncode == 0:
        return True, ""
    sortie = ((r.stderr or "") + " " + (r.stdout or "")).strip()
    if "password" in sortie.lower() or "mot de passe" in sortie.lower():
        return False, AIDE_SUDO
    return False, sortie[:150] or "code de retour %d" % r.returncode


def partage_actif():
    """« actif », « arrêté », ou « inconnu » si systemd ne répond pas."""
    try:
        r = subprocess.run(["systemctl", "is-active", SERVICE_PARTAGE],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return "inconnu"
    etat = (r.stdout or "").strip()
    if etat == "active":
        return "actif"
    if etat in ("inactive", "failed", "deactivating"):
        return "arrêté"
    return "inconnu"


def depuis_quand():
    """Secondes depuis le démarrage du Pi. Sert à distinguer « il vient de
    redémarrer, c'est normal qu'il soit lent » de « il est là depuis trois
    semaines et il a fini par se coincer »."""
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except Exception:
        return 0


def etat():
    return {"partage": partage_actif(), "debout": depuis_quand()}


# ----------------------------------------------------------------------
# les gestes
# ----------------------------------------------------------------------

def relancer_partage():
    ok, dit = _courir(["sudo", "-n", "systemctl", "restart", SERVICE_PARTAGE])
    if not ok:
        return False, "partage non relancé — %s" % dit
    # on vérifie plutôt que de croire le code de retour : systemctl rend la
    # main avant que smbd soit vraiment reparti
    for _ in range(6):
        time.sleep(0.5)
        if partage_actif() == "actif":
            return True, "partage relancé — les fichiers redeviennent visibles"
    return False, ("partage relancé mais il ne tient pas — regarde "
                   "journalctl -u %s sur le Pi" % SERVICE_PARTAGE)


def demander(geste):
    """Note un geste différé. (ok, ce qu'on en dit à l'app)."""
    with VERROU:
        if EN_ATTENTE:
            return True, "déjà demandé, ça arrive"
        EN_ATTENTE["geste"] = geste
        EN_ATTENTE["at"] = time.time()
    if geste == "relais":
        return True, ("relais relancé dans un instant — il revient tout seul "
                      "dans la demi-minute")
    return True, ("Pi redémarré dans un instant — compte une minute avant "
                  "qu'il réponde à nouveau")


def executer_si_demande(journal=None):
    """À appeler APRÈS la publication de la relève, jamais avant.

    Renvoie une phrase pour le journal, ou None. Le relais peut ne pas
    revenir de cet appel : c'est le but."""
    with VERROU:
        geste = EN_ATTENTE.pop("geste", None)
        EN_ATTENTE.clear()
    if not geste:
        return None

    if geste == "relais":
        if journal:
            journal("relais relancé à la demande de l'app")
        # Restart=always dans l'unité : sortir suffit, et ça n'a besoin
        # d'aucun droit. os._exit saute les atexit, ce qui est voulu — on
        # ne veut rien finir proprement, on veut repartir de zéro.
        SORTIE(0)
        return "relais relancé"

    if geste == "pi":
        ok, dit = _courir(["sudo", "-n", "systemctl", "reboot"])
        if ok:
            if journal:
                journal("Pi redémarré à la demande de l'app")
            return "redémarrage en cours"
        return "redémarrage refusé — %s" % dit

    return None


GESTES = ("partage", "relais", "pi")
PHRASES = {
    "partage": "relancer le partage de fichiers",
    "relais": "relancer le relais",
    "pi": "redémarrer le Pi",
}
