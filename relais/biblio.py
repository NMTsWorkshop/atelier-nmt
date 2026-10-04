#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bibliothèque de gcodes et historique d'impression de l'atelier.

Le principe : les fichiers tranchés ne vivent qu'à un seul endroit, sur le
Pi, rangés par famille de machines. L'application les liste, voit lesquels
ont déjà été imprimés et par qui, et les envoie à une machine sans qu'on
ait à repasser par le PC.

    <racine>/k2/...      ce qui part sur les Creality K2 Plus
    <racine>/p1s/...     ce qui part sur les Bambu P1S

Les sous-dossiers sont libres : tout ce qui est sous une famille est
proposé aux machines de cette famille, chemin relatif compris.

Un fichier à imprimer en plusieurs exemplaires le dit dans son nom —
« casque_x3.gcode », « casque (x3).gcode » — ou se règle depuis l'app, ce
qui l'écrit dans exemplaires.json. Tant que le compte n'est pas atteint,
le fichier reste signalé comme à imprimer.

Ce module n'est pas lancé seul : relais_atelier.py l'importe, lui donne
ses relevés et ouvre son petit serveur HTTP sur le réseau local.
"""

import ftplib
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# nombre d'exemplaires écrit dans le nom du fichier
EXEMPLAIRES = re.compile(r"[ _(\[-]x\s*(\d{1,3})\b", re.I)

# ce qu'on accepte de lister
EXTENSIONS = (".gcode", ".gco", ".g", ".3mf", ".gcode.3mf")

VERROU = threading.Lock()


def famille_de(machine):
    """La famille d'une machine : ce qui décide quels fichiers lui vont."""
    f = str(machine.get("famille") or "").strip().lower()
    if f:
        return f
    return "k2" if machine.get("type") == "moonraker" else "p1s"


def base_nom(nom):
    """Le nom d'un fichier réduit à ce qui l'identifie d'une machine à
    l'autre : sans dossier, sans extension, sans la casse. Une K2 renvoie
    « casque_x3.gcode », une Bambu « casque_x3 » : c'est le même fichier."""
    n = os.path.basename(str(nom or "")).strip().lower()
    for e in (".gcode.3mf", ".gcode", ".3mf", ".gco", ".g"):
        if n.endswith(e):
            n = n[: -len(e)]
            break
    return n


# ----------------------------------------------------------------------
# l'index des fichiers
# ----------------------------------------------------------------------

class Bibliotheque(object):

    def __init__(self, racine, familles):
        self.racine = os.path.abspath(os.path.expanduser(racine))
        self.familles = list(familles) or ["k2", "p1s"]
        self.reglages = os.path.join(self.racine, "exemplaires.json")
        self.journal = os.path.join(self.racine, "historique.jsonl")
        for f in self.familles:
            try:
                os.makedirs(os.path.join(self.racine, f), exist_ok=True)
            except OSError:
                pass

    # --- exemplaires demandés, quand l'app les a fixés à la main --------

    def _surcharges(self):
        try:
            with open(self.reglages, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def fixer_exemplaires(self, chemin, nombre):
        chemin = self.verifier(chemin)
        rel = os.path.relpath(chemin, self.racine).replace(os.sep, "/")
        with VERROU:
            d = self._surcharges()
            if nombre is None or int(nombre) <= 0:
                d.pop(rel, None)
            else:
                d[rel] = int(nombre)
            provisoire = self.reglages + ".tmp"
            with open(provisoire, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(provisoire, self.reglages)
        return rel

    # --- chemins ------------------------------------------------------

    def verifier(self, chemin):
        """Un chemin venu du réseau ne sort pas de la bibliothèque."""
        voulu = os.path.realpath(os.path.join(self.racine, str(chemin or "").lstrip("/\\")))
        racine = os.path.realpath(self.racine)
        if voulu != racine and not voulu.startswith(racine + os.sep):
            raise ValueError("chemin hors de la bibliothèque")
        if not os.path.isfile(voulu):
            raise ValueError("fichier introuvable : %s" % chemin)
        return voulu

    # --- l'index ------------------------------------------------------

    def index(self):
        comptes = self.comptes()
        surcharges = self._surcharges()
        fichiers = []
        for famille in self.familles:
            dossier = os.path.join(self.racine, famille)
            if not os.path.isdir(dossier):
                continue
            for base, _dirs, noms in os.walk(dossier):
                for nom in noms:
                    if not nom.lower().endswith(EXTENSIONS) or nom.startswith("."):
                        continue
                    entier = os.path.join(base, nom)
                    rel = os.path.relpath(entier, self.racine).replace(os.sep, "/")
                    try:
                        st = os.stat(entier)
                    except OSError:
                        continue
                    cle = base_nom(nom)
                    passe = comptes.get(cle) or {}
                    demande = surcharges.get(rel)
                    if demande is None:
                        m = EXEMPLAIRES.search(os.path.splitext(nom)[0])
                        demande = int(m.group(1)) if m else 1
                    faits = int(passe.get("faits", 0))
                    fichiers.append({
                        "chemin": rel,
                        "famille": famille,
                        "nom": nom,
                        "dossier": os.path.dirname(rel).split("/", 1)[1] if "/" in os.path.dirname(rel) else "",
                        "taille": st.st_size,
                        "modifie": int(st.st_mtime * 1000),
                        "exemplaires": int(demande),
                        "faits": faits,
                        "reste": max(0, int(demande) - faits),
                        "dernier": passe.get("dernier") or 0,
                        "machines": passe.get("machines") or [],
                        "minutes": passe.get("minutes") or 0,
                    })
        fichiers.sort(key=lambda f: (f["famille"], f["chemin"].lower()))
        return {"racine": self.racine, "familles": self.familles, "fichiers": fichiers}

    # --- l'historique --------------------------------------------------

    def noter(self, enregistrement):
        with VERROU:
            try:
                with open(self.journal, "a", encoding="utf-8") as f:
                    f.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def historique(self, limite=200):
        lignes = []
        try:
            with open(self.journal, encoding="utf-8") as f:
                for ligne in f:
                    ligne = ligne.strip()
                    if not ligne:
                        continue
                    try:
                        lignes.append(json.loads(ligne))
                    except ValueError:
                        continue
        except OSError:
            return []
        lignes.sort(key=lambda e: e.get("fin") or e.get("at") or 0, reverse=True)
        return lignes[:limite]

    def comptes(self):
        """Par fichier : combien de fois il est allé au bout, quand pour la
        dernière fois, sur quelles machines, et le temps machine cumulé."""
        out = {}
        for e in self.historique(limite=100000):
            if e.get("etat") != "fini":
                continue
            cle = base_nom(e.get("fichier"))
            if not cle:
                continue
            c = out.setdefault(cle, {"faits": 0, "dernier": 0, "machines": [], "minutes": 0})
            c["faits"] += 1
            quand = e.get("fin") or e.get("at") or 0
            c["dernier"] = max(c["dernier"], quand)
            c["minutes"] += int(e.get("minutes") or 0)
            nom = e.get("machine")
            if nom and nom not in c["machines"]:
                c["machines"].append(nom)
        return out


# ----------------------------------------------------------------------
# envoyer un fichier sur une machine
# ----------------------------------------------------------------------

def joignable(hote, port, delai=3):
    """Vérifié avant d'envoyer : sans ça, une machine éteinte fait attendre
    le téléphone jusqu'au bout du délai d'envoi, sans rien lui dire."""
    try:
        s = socket.create_connection((hote, port), timeout=delai)
        s.close()
        return True
    except OSError:
        return False


def pousser_moonraker(machine, chemin, nom, lancer):
    """Moonraker accepte le fichier et, si on le demande, lance l'impression
    dans le même appel — avec les réglages du fichier lui-même."""
    limite = "----nmt%d" % int(time.time() * 1000)
    with open(chemin, "rb") as f:
        contenu = f.read()
    morceaux = []

    def champ(cle, valeur):
        morceaux.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                         % (limite, cle, valeur)).encode("utf-8"))

    champ("root", "gcodes")
    champ("path", "")
    if lancer:
        champ("print", "true")
    morceaux.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                     "filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                     % (limite, nom)).encode("utf-8"))
    morceaux.append(contenu)
    morceaux.append(("\r\n--%s--\r\n" % limite).encode("utf-8"))
    corps = b"".join(morceaux)

    url = "http://%s:%d/server/files/upload" % (machine["hote"], machine.get("port", 7125))
    req = urllib.request.Request(url, data=corps, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=%s" % limite)
    with urllib.request.urlopen(req, timeout=180) as r:
        r.read()
    return "lancé" if lancer else "déposé"


class _FtpImplicite(ftplib.FTP_TLS):
    """Les Bambu parlent FTPS en TLS implicite sur le port 990 : la
    connexion est chiffrée dès l'ouverture, avant le premier mot. ftplib
    ne sait faire que l'explicite, d'où cette petite greffe."""

    def __init__(self, *a, **k):
        self._enveloppe = None
        ftplib.FTP_TLS.__init__(self, *a, **k)

    @property
    def sock(self):
        return self._enveloppe

    @sock.setter
    def sock(self, valeur):
        if valeur is not None and not isinstance(valeur, ssl.SSLSocket):
            valeur = self.context.wrap_socket(valeur, server_hostname=None)
        self._enveloppe = valeur


def pousser_bambu(machine, chemin, nom, lancer):
    """On dépose le fichier sur la carte SD de la machine. On ne lance pas
    l'impression d'ici : la commande Bambu embarque le type de plateau, la
    calibration et le choix des bobines, et se tromper coûte une pièce.
    Le fichier déposé se lance d'un geste sur l'écran de la machine."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ftp = _FtpImplicite(context=ctx)
    ftp.connect(machine["hote"], 990, timeout=30)
    try:
        ftp.login("bblp", machine.get("code") or "")
        ftp.prot_p()
        ftp.set_pasv(True)
        with open(chemin, "rb") as f:
            ftp.storbinary("STOR %s" % nom, f, blocksize=32768)
    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
    return "déposé"


def pousser(biblio, machines, nom_machine, chemin_relatif, lancer=False):
    machine = None
    for m in machines:
        if m.get("nom") == nom_machine or m.get("hote") == nom_machine:
            machine = m
            break
    if machine is None:
        raise ValueError("machine inconnue : %s" % nom_machine)

    entier = biblio.verifier(chemin_relatif)
    famille_fichier = os.path.relpath(entier, biblio.racine).replace(os.sep, "/").split("/")[0]
    if famille_fichier != famille_de(machine):
        raise ValueError("ce fichier est rangé pour les %s, pas pour %s"
                         % (famille_fichier, machine.get("nom")))

    nom = os.path.basename(entier)
    port = machine.get("port", 7125) if machine["type"] == "moonraker" else 990
    if not joignable(machine["hote"], port):
        raise ValueError("%s ne répond pas sur %s — machine éteinte ?"
                         % (machine.get("nom"), machine["hote"]))
    if machine["type"] == "moonraker":
        etat = pousser_moonraker(machine, entier, nom, lancer)
    else:
        etat = pousser_bambu(machine, entier, nom, lancer)
    biblio.noter({"at": int(time.time() * 1000), "machine": machine.get("nom"),
                  "fichier": nom, "etat": "envoyé", "chemin": chemin_relatif})
    return {"ok": True, "etat": etat, "machine": machine.get("nom"), "fichier": nom,
            "lance": bool(lancer and machine["type"] == "moonraker")}


# ----------------------------------------------------------------------
# le petit serveur HTTP du réseau local
# ----------------------------------------------------------------------
#
# Il n'est joignable que depuis la maison : rien n'est ouvert sur
# Internet. Le jeton est là pour que seul le téléphone de l'atelier
# puisse pousser un fichier sur une machine, pas un appareil de passage
# sur le Wi-Fi.

class Contexte(object):
    def __init__(self, biblio, machines, jeton, etats=None):
        self.biblio = biblio
        self.machines = machines
        self.jeton = jeton or ""
        self.etats = etats if etats is not None else {}


class Service(BaseHTTPRequestHandler):

    server_version = "relais-atelier"
    protocol_version = "HTTP/1.1"
    ctx = None

    def log_message(self, format, *args):
        pass        # le journal systemd n'a pas besoin d'une ligne par appel

    # --- plomberie ----------------------------------------------------

    def _repondre(self, code, charge):
        corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _autorise(self):
        if not self.ctx.jeton:
            return True        # pas de jeton configuré : réseau local seul
        attendu = "Bearer " + self.ctx.jeton
        if self.headers.get("Authorization", "") == attendu:
            return True
        self._repondre(401, {"ok": False, "error": "jeton refusé"})
        return False

    def _corps(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8")) or {}
        except ValueError:
            return {}

    # --- routes -------------------------------------------------------

    def do_GET(self):
        route = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(route.query)
        if route.path == "/vivant":
            return self._repondre(200, {"ok": True, "relais": "atelier",
                                        "jeton": bool(self.ctx.jeton)})
        if not self._autorise():
            return
        try:
            if route.path == "/etat":
                return self._repondre(200, {"ok": True, "at": int(time.time() * 1000),
                                            "machines": self.ctx.etats})
            if route.path == "/biblio":
                return self._repondre(200, dict(self.ctx.biblio.index(), ok=True))
            if route.path == "/historique":
                n = int((params.get("n") or ["200"])[0])
                return self._repondre(200, {"ok": True,
                                            "lignes": self.ctx.biblio.historique(max(1, min(n, 2000)))})
        except Exception as e:
            return self._repondre(500, {"ok": False, "error": str(e)[:200]})
        self._repondre(404, {"ok": False, "error": "route inconnue"})

    def do_POST(self):
        route = urllib.parse.urlparse(self.path)
        if not self._autorise():
            return
        corps = self._corps()
        try:
            if route.path == "/exemplaires":
                rel = self.ctx.biblio.fixer_exemplaires(corps.get("chemin"), corps.get("n"))
                return self._repondre(200, {"ok": True, "chemin": rel})
            if route.path == "/pousser":
                res = pousser(self.ctx.biblio, self.ctx.machines,
                              corps.get("machine"), corps.get("chemin"),
                              bool(corps.get("lancer")))
                return self._repondre(200, res)
        except ValueError as e:
            return self._repondre(400, {"ok": False, "error": str(e)[:200]})
        except Exception as e:
            return self._repondre(502, {"ok": False, "error": str(e)[:200]})
        self._repondre(404, {"ok": False, "error": "route inconnue"})


def servir(contexte, port=8765):
    """Ouvre le service dans un fil à part et rend la main tout de suite."""
    Service.ctx = contexte
    serveur = ThreadingHTTPServer(("0.0.0.0", port), Service)
    serveur.daemon_threads = True
    fil = threading.Thread(target=serveur.serve_forever, name="api", daemon=True)
    fil.start()
    return serveur


def adresse_locale():
    """L'adresse du Pi telle que le téléphone doit l'appeler."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# ----------------------------------------------------------------------
# suivi des impressions, d'un relevé à l'autre
# ----------------------------------------------------------------------
#
# Une relève ne dit que l'instant présent. L'historique se déduit des
# changements : une machine qui imprimait un fichier et qui ne l'imprime
# plus vient de le finir — ou de l'interrompre, et le pourcentage le dit.

EN_COURS = {}


def suivre(biblio, etats):
    """À appeler après chaque relevé. Renvoie les lignes ajoutées."""
    ajouts = []
    for cle, etat in (etats or {}).items():
        if not etat.get("ok") or etat.get("stale"):
            continue        # une lecture ratée ou datée ne conclut rien
        nom = etat.get("nom") or cle
        fichier = etat.get("file") or ""
        phase = etat.get("state") or ""
        pourcent = etat.get("percent")
        pourcent = int(pourcent) if isinstance(pourcent, (int, float)) else -1
        suivi = EN_COURS.get(cle)

        if phase in ("printing", "paused") and fichier:
            if suivi is None or suivi.get("fichier") != fichier:
                EN_COURS[cle] = {"fichier": fichier, "debut": etat.get("at"),
                                 "pourcent": pourcent}
            else:
                suivi["pourcent"] = max(suivi.get("pourcent", -1), pourcent)
            continue

        if suivi is None:
            continue

        # la machine n'imprime plus ce fichier : on conclut
        if phase == "finished" or suivi.get("pourcent", 0) >= 97:
            issue = "fini"
        elif phase == "failed":
            issue = "échec"
        elif phase in ("idle", "preparing", "unknown"):
            issue = "interrompu"
        else:
            continue        # état qu'on ne sait pas lire : on ne conclut pas

        debut = suivi.get("debut") or etat.get("at")
        ligne = {"machine": nom, "fichier": suivi["fichier"], "etat": issue,
                 "debut": debut, "fin": etat.get("at"),
                 "minutes": max(0, int(((etat.get("at") or 0) - (debut or 0)) / 60000)),
                 "pourcent": suivi.get("pourcent", -1)}
        biblio.noter(ligne)
        ajouts.append(ligne)
        EN_COURS.pop(cle, None)
    return ajouts
