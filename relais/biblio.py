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

import base64
import ftplib
import hashlib
import http.client
import hmac
import json
import os
import re
import socket
import struct
import ssl
import threading
import time
import uuid
import urllib.parse
import urllib.request
import zipfile
import zlib
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
        self.etat_chemin = os.path.join(self.racine, "biblio.json")
        self.ancien_etat = os.path.join(self.racine, "exemplaires.json")
        self.journal = os.path.join(self.racine, "historique.jsonl")
        for f in self.familles:
            try:
                os.makedirs(os.path.join(self.racine, f), exist_ok=True)
            except OSError:
                pass

    # --- ce que l'app a fixé à la main --------------------------------
    #
    # biblio.json garde ce qu'aucun fichier ne peut dire : à quelle
    # commande un fichier appartient quand son dossier ne le dit pas, et
    # quels plateaux sont sortis quand la machine ne l'annonce pas.

    def etat(self):
        try:
            with open(self.etat_chemin, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and "fichiers" in d:
                return d
        except Exception:
            pass
        # première lecture : on reprend l'ancien exemplaires.json s'il existe
        fichiers = {}
        try:
            with open(self.ancien_etat, encoding="utf-8") as f:
                for rel, n in (json.load(f) or {}).items():
                    fichiers[rel] = {"exemplaires": int(n)}
        except Exception:
            pass
        return {"fichiers": fichiers}

    def _ecrire_etat(self, d):
        provisoire = self.etat_chemin + ".tmp"
        with open(provisoire, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(provisoire, self.etat_chemin)

    def _modifier(self, chemin, modifier):
        chemin = self.verifier(chemin)
        rel = os.path.relpath(chemin, self.racine).replace(os.sep, "/")
        with VERROU:
            d = self.etat()
            entree = d["fichiers"].setdefault(rel, {})
            modifier(entree)
            if not entree:
                d["fichiers"].pop(rel, None)
            self._ecrire_etat(d)
        return rel

    def fixer_exemplaires(self, chemin, nombre, plateau=None):
        def faire(e):
            if plateau is None:
                if nombre is None or int(nombre) <= 0:
                    e.pop("exemplaires", None)
                else:
                    e["exemplaires"] = int(nombre)
                return
            p = e.setdefault("plateaux", {}).setdefault(str(int(plateau)), {})
            if nombre is None or int(nombre) <= 0:
                p.pop("exemplaires", None)
            else:
                p["exemplaires"] = int(nombre)
            if not p:
                e["plateaux"].pop(str(int(plateau)), None)
            if not e.get("plateaux"):
                e.pop("plateaux", None)
        return self._modifier(chemin, faire)

    def fixer_commande(self, chemin, nom):
        def faire(e):
            nom_propre = str(nom or "").strip()
            if nom_propre:
                e["commande"] = nom_propre
            else:
                e.pop("commande", None)
        return self._modifier(chemin, faire)

    def marquer(self, chemin, plateau, fait=True, machine=""):
        """« Celui-là, il est sorti » — ou l'inverse quand on s'est trompé."""
        quand = int(time.time() * 1000)

        def faire(e):
            p = e.setdefault("plateaux", {}).setdefault(str(int(plateau)), {})
            faits = int(p.get("faits", 0))
            if fait:
                p["faits"] = faits + 1
                p["dernier"] = quand
                p.pop("refaire", None)
                if machine:
                    noms = p.setdefault("machines", [])
                    if machine not in noms:
                        noms.append(machine)
            else:
                p["faits"] = max(0, faits - 1)
                if p["faits"] == 0:
                    p.pop("faits", None)
                    p.pop("dernier", None)
                    p.pop("machines", None)
            if not p:
                e["plateaux"].pop(str(int(plateau)), None)
            if not e.get("plateaux"):
                e.pop("plateaux", None)
        return self._modifier(chemin, faire)

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

    def chemins_par_nom(self):
        """{nom réduit: [chemins]} — juste de quoi relier ce qu'annonce une
        machine à un fichier de la bibliothèque. Beaucoup plus léger que
        l'index complet, qui relit tout l'historique."""
        out = {}
        for famille in self.familles:
            dossier = os.path.join(self.racine, famille)
            if not os.path.isdir(dossier):
                continue
            for base, _dirs, noms in os.walk(dossier):
                for nom in noms:
                    if not nom.lower().endswith(EXTENSIONS) or nom.startswith("."):
                        continue
                    rel = os.path.relpath(os.path.join(base, nom),
                                          self.racine).replace(os.sep, "/")
                    out.setdefault(base_nom(nom), []).append(rel)
        return out

    def marquer_refaire(self, chemin, plateau, refaire=True):
        """Un plateau qui s'est mal terminé reste signalé tant qu'il n'est
        pas ressorti : c'est le seul moyen de ne pas oublier de le refaire."""
        def faire(e):
            p = e.setdefault("plateaux", {}).setdefault(str(int(plateau)), {})
            if refaire:
                p["refaire"] = True
            else:
                p.pop("refaire", None)
            if not p:
                e["plateaux"].pop(str(int(plateau)), None)
            if not e.get("plateaux"):
                e.pop("plateaux", None)
        return self._modifier(chemin, faire)

    # --- l'index ------------------------------------------------------

    def index(self):
        comptes = self.comptes()
        etat = self.etat()["fichiers"]
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
                    fichiers.append(self._fiche(rel, entier, st, famille,
                                                etat.get(rel) or {}, comptes))
        fichiers.sort(key=lambda f: (f["commande"] or "￿", f["famille"], f["chemin"].lower()))
        return {"racine": self.racine, "familles": self.familles,
                "fichiers": fichiers, "commandes": self._commandes(fichiers)}

    def _fiche(self, rel, entier, st, famille, regle, comptes):
        parts = rel.split("/")
        dossier = "/".join(parts[1:-1])
        nom = parts[-1]

        # le sous-dossier fait la commande, sauf si l'app en a décidé autrement
        commande = regle.get("commande")
        if commande is None:
            commande = parts[1] if len(parts) > 2 else ""

        liste = plateaux(entier)
        passe = comptes.get(base_nom(nom)) or {}
        demande_fichier = regle.get("exemplaires")
        if demande_fichier is None:
            m = EXEMPLAIRES.search(os.path.splitext(nom)[0])
            demande_fichier = int(m.group(1)) if m else 1
        regles_plateaux = regle.get("plateaux") or {}

        if len(liste) > 1:
            # plusieurs plateaux : chacun se compte à part, et seule l'app
            # sait aujourd'hui lequel est sorti
            sorties = []
            for p in liste:
                r = regles_plateaux.get(str(p["idx"])) or {}
                voulu = int(r.get("exemplaires", demande_fichier))
                faits = int(r.get("faits", 0))
                sorties.append(dict(p, exemplaires=voulu, faits=faits,
                                    manuel=faits,
                                    reste=max(0, voulu - faits),
                                    dernier=r.get("dernier", 0),
                                    machines=r.get("machines") or [],
                                    refaire=bool(r.get("refaire"))))
        else:
            # un seul plateau : c'est le fichier entier, et l'historique du
            # relais suffit à savoir s'il est sorti
            r = regles_plateaux.get("0") or regles_plateaux.get("1") or {}
            faits = int(passe.get("faits", 0)) + int(r.get("faits", 0))
            dernier = max(int(passe.get("dernier", 0)), int(r.get("dernier", 0)))
            machines = list(passe.get("machines") or [])
            for m in (r.get("machines") or []):
                if m not in machines:
                    machines.append(m)
            seul = liste[0] if liste else {"idx": 0, "minutes": 0, "grammes": 0,
                                           "objets": [], "vignette": ""}
            # « manuel » : la part cochee a la main. Seule celle-la se
            # decoche — ce que le relais a vu sortir, lui, est un fait.
            sorties = [dict(seul, exemplaires=demande_fichier, faits=faits,
                            manuel=int(r.get("faits", 0)),
                            reste=max(0, demande_fichier - faits),
                            dernier=dernier, machines=machines,
                            refaire=bool(r.get("refaire")))]

        tournent = en_cours_ici(rel)
        for p in sorties:
            p["machine_en_cours"] = tournent.get(p["idx"], "")
            p["etat"] = ("encours" if p["machine_en_cours"]
                         else "refaire" if p["refaire"]
                         else "fait" if p["reste"] <= 0
                         else "attente")

        return {
            "chemin": rel, "famille": famille, "nom": nom, "dossier": dossier,
            "encours": any(p["etat"] == "encours" for p in sorties),
            "refaire": any(p["etat"] == "refaire" for p in sorties),
            "commande": commande,
            "taille": st.st_size, "modifie": int(st.st_mtime * 1000),
            "multi": len(liste) > 1,
            "plateaux": sorties,
            "exemplaires": sum(p["exemplaires"] for p in sorties),
            "faits": sum(min(p["faits"], p["exemplaires"]) for p in sorties),
            "reste": sum(p["reste"] for p in sorties),
            "dernier": max([p["dernier"] for p in sorties] or [0]),
            "machines": [m for p in sorties for m in p["machines"]],
            "minutes": sum(p["minutes"] for p in sorties),
        }

    def _commandes(self, fichiers):
        """Une commande n'est finie que quand ses plateaux sont tous sortis,
        K2 et Bambu confondues : c'est tout l'intérêt de les regrouper."""
        par_nom = {}
        for f in fichiers:
            if not f["commande"]:
                continue
            c = par_nom.setdefault(f["commande"], {
                "nom": f["commande"], "fichiers": 0, "familles": [],
                "plateaux": 0, "faits": 0, "reste": 0, "minutes": 0,
                "dernier": 0, "chemins": [], "encours": 0, "refaire": 0})
            c["fichiers"] += 1
            c["plateaux"] += sum(p["exemplaires"] for p in f["plateaux"])
            c["faits"] += f["faits"]
            c["reste"] += f["reste"]
            c["minutes"] += f["minutes"]
            c["dernier"] = max(c["dernier"], f["dernier"])
            c["chemins"].append(f["chemin"])
            if f.get("encours"):
                c["encours"] = c.get("encours", 0) + 1
            if f.get("refaire"):
                c["refaire"] = c.get("refaire", 0) + 1
            if f["famille"] not in c["familles"]:
                c["familles"].append(f["famille"])
        sorties = []
        for c in par_nom.values():
            c["termine"] = c["reste"] == 0
            sorties.append(c)
        sorties.sort(key=lambda c: (c["termine"], c["nom"].lower()))
        return sorties

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


# ----------------------------------------------------------------------
# ou en est un envoi
# ----------------------------------------------------------------------
#
# Le fichier part du Pi, pas du telephone : l'app ne peut rien mesurer
# elle-meme. Le relais compte donc les octets qu'il pousse et joint
# l'avancement a son releve — celui qu'il publie deja chaque minute,
# pour que suivre un transfert ne coute pas un message de plus.

ENVOIS = {}
# ENVOIS et ACCUSES sont touches par trois familles de fils : la boucle
# principale, les fils du serveur HTTP, et chaque fil d'envoi. Sans verrou,
# une simple lecture pendant une insertion suffisait a faire tomber la
# boucle principale sur « dictionary changed size during iteration » — et
# avec elle le relais entier, fils d'envoi compris.
VERROU_ENVOIS = threading.RLock()
GARDE_ENVOI = 180      # on garde un envoi fini le temps que l'app le voie
BLOC = 262144          # 256 ko : assez gros pour ne pas ramer, assez fin
                       # pour que la barre bouge sur un fichier de 100 Mo


class _CorpsCompte:
    """Le corps multipart d'un envoi Moonraker, lu a la demande.

    Les parties sont des « bytes » (preambule, epilogue) ou un couple
    (fichier ouvert, taille) : le gcode n'est jamais charge en memoire. La
    premiere version le lisait entier puis le recopiait en tranches, soit
    deux fois sa taille en RAM — 400 Mo pour un casque, sur un Pi qui n'en
    a qu'un giga."""

    def __init__(self, parties, progres=None):
        self._parties = list(parties)
        self._tampon = b""
        self._progres = progres
        self.envoye = 0
        self.total = sum(len(p) if isinstance(p, bytes) else p[1]
                         for p in self._parties)

    def __len__(self):
        # la taille totale, pas le restant : c'est elle qui sert de
        # Content-Length, et elle ne doit pas dependre de ce qui a deja ete lu
        return self.total

    def _remplir(self, combien):
        while len(self._tampon) < combien and self._parties:
            p = self._parties[0]
            if isinstance(p, bytes):
                self._tampon += p
                self._parties.pop(0)
                continue
            f, reste = p
            bout = f.read(min(BLOC, reste))
            if not bout:
                self._parties.pop(0)
                continue
            self._tampon += bout
            reste -= len(bout)
            if reste <= 0:
                self._parties.pop(0)
            else:
                self._parties[0] = (f, reste)

    def read(self, combien=-1):
        if combien is None or combien < 0:
            combien = max(0, self.total - self.envoye)
        self._remplir(combien)
        bout, self._tampon = self._tampon[:combien], self._tampon[combien:]
        self.envoye += len(bout)
        if bout and self._progres:
            self._progres(self.envoye)
        return bout


class DeposeSansLancement(Exception):
    """Le fichier est bien arrive sur la machine, c'est le demarrage de
    l'impression qui a ete refuse. Ce n'est pas un echec d'envoi."""


class DeposeSansConfirmation(Exception):
    """Tous les octets sont partis, mais la machine n'a pas confirme.

    storbinary fait deux lectures APRES le dernier octet : la fermeture
    propre de la couche TLS du canal de donnees, puis la reponse 226 sur le
    canal de controle. Une Bambu qui vient d'encaisser quatre-vingts megas
    met du temps a les ecrire sur sa carte avant de repondre, et certaines
    ne ferment jamais proprement leur TLS. Les deux se presentent comme
    « The read operation timed out », alors que le fichier, lui, est
    passe en entier. Le compter pour un echec ferait tout renvoyer."""


class EnvoiAnnule(Exception):
    """Levee depuis le compteur d'octets : c'est l'endroit par ou l'envoi
    repasse assez souvent pour qu'on puisse l'arreter en vol."""


def _nouvel_ident():
    """Un identifiant qui ne peut pas entrer en collision. L'ancien repli,
    « local-<secondes> », donnait le meme a deux envois lances dans la meme
    seconde : le second ecrasait le premier, qui devenait invisible et
    inannulable pendant que sa barre affichait l'avancement de l'autre."""
    return "local-%d-%s" % (time.time() * 1000, uuid.uuid4().hex[:6])


def envoi_commence(ident, fichier, machine, total):
    if not ident:
        return
    with VERROU_ENVOIS:
        ancien = ENVOIS.get(ident)
        # l'ordre d'arrivée des deux appels n'est pas garanti : celui qui
        # connaît la taille ne doit jamais se faire effacer par celui qui
        # ne la connaît pas encore
        if ancien and ancien["etat"] == "en cours" and not total:
            return
        ENVOIS[ident] = {"id": ident, "fichier": fichier, "machine": machine,
                         "octets": ancien["octets"] if ancien else 0,
                         "total": int(total or 0),
                         "debut": ancien["debut"] if ancien else int(time.time() * 1000),
                         "fin": 0, "etat": "en cours", "fige": False}


def envoi_avance(ident, octets):
    """Moonraker compte le corps multipart entier, quelques centaines
    d'octets de plus que le fichier : on plafonne, sinon la barre
    depasserait sa fin puis reculerait."""
    with VERROU_ENVOIS:
        e = ENVOIS.get(ident)
        if not e:
            return
        annule = e.get("annule")
        if not annule:
            n = int(octets)
            e["octets"] = min(n, e["total"]) if e["total"] else n
    if annule:
        raise EnvoiAnnule("envoi annulé")


def envoi_fige(ident):
    """Le corps est entierement parti : a partir d'ici on ne peut plus
    arreter quoi que ce soit, le fichier est sur la machine."""
    with VERROU_ENVOIS:
        e = ENVOIS.get(ident)
        if e:
            e["fige"] = True


def envoi_veut_arret(ident):
    """A relire aux points ou l'on peut encore renoncer — avant de lancer
    l'impression, par exemple — et pas seulement entre deux blocs."""
    with VERROU_ENVOIS:
        e = ENVOIS.get(ident)
        return bool(e and e.get("annule"))


def annuler_envoi(ident):
    """Pose le drapeau ; c'est le fil d'envoi qui s'arretera de lui-meme.
    Renvoie ce qu'il faut dire a celui qui a demande."""
    with VERROU_ENVOIS:
        e = ENVOIS.get(ident)
        if not e:
            return False, "cet envoi n'est plus suivi par le relais"
        if e["etat"] != "en cours":
            return False, "cet envoi est déjà terminé"
        if e.get("fige"):
            # promettre un arret qu'on ne tiendra pas serait pire que de
            # refuser : le fichier est deja passe en entier
            return False, "trop tard — le fichier est déjà sur la machine"
        e["annule"] = True
        return True, "arrêt de %s demandé" % e.get("fichier")


def envoi_annule(ident):
    with VERROU_ENVOIS:
        e = ENVOIS.get(ident)
        if not e:
            return
        e["etat"] = "annule"
        e["fin"] = int(time.time() * 1000)
        e["dit"] = "arrêté en cours d'envoi"


def envoi_termine(ident, ok, dit=""):
    with VERROU_ENVOIS:
        e = ENVOIS.get(ident)
        if not e:
            return
        e["etat"] = "fait" if ok else "echoue"
        e["fin"] = int(time.time() * 1000)
        e["dit"] = str(dit)[:120]
        if ok and e["total"]:
            e["octets"] = e["total"]


def envois_publics():
    """Ce qui part dans le releve : les envois en cours, et ceux qui
    viennent de finir, pour que la barre atteigne sa fin au lieu de
    disparaitre a quatre-vingt-dix pour cent.

    « ecoule » est calcule ici, avec l'horloge du relais. Le telephone ne
    doit surtout pas faire cette soustraction lui-meme : un Raspberry Pi
    n'a pas de pile, son heure vient du reseau, et s'il derive de deux
    minutes le debit affiche devient une fable."""
    maintenant = time.time() * 1000
    with VERROU_ENVOIS:
        for ident, e in list(ENVOIS.items()):
            if e["fin"] and maintenant - e["fin"] > GARDE_ENVOI * 1000:
                ENVOIS.pop(ident, None)
        tout = sorted((dict(e) for e in ENVOIS.values()), key=lambda e: e["debut"])
    # un envoi en cours ne disparait jamais du releve : c'est par lui qu'on
    # l'arrete. On ne rogne que sur les termines.
    actifs = [e for e in tout if e["etat"] == "en cours"]
    finis = [e for e in tout if e["etat"] != "en cours"]
    garde = actifs + finis[-max(1, 6 - len(actifs)):] if finis else actifs
    garde.sort(key=lambda e: e["debut"])
    return [dict(e, ecoule=max(0, int((e["fin"] or maintenant) - e["debut"])))
            for e in garde]


def envoi_actif():
    with VERROU_ENVOIS:
        return any(e["etat"] == "en cours" for e in ENVOIS.values())


def pousser_moonraker(machine, chemin, nom, lancer, progres=None, ident=None):
    """Moonraker accepte le fichier et, si on le demande, lance l'impression
    dans le même appel — avec les réglages du fichier lui-même."""
    limite = "----nmt%d" % int(time.time() * 1000)
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
    f = open(chemin, "rb")
    try:
        morceaux.append((f, os.path.getsize(chemin)))
        morceaux.append(("\r\n--%s--\r\n" % limite).encode("utf-8"))
        corps = _CorpsCompte(morceaux, progres)
        taille = len(corps)
        return _poster_moonraker(machine, corps, taille, limite, lancer,
                                 nom, ident)
    finally:
        try:
            f.close()
        except Exception:
            pass


def _poster_moonraker(machine, corps, taille, limite, lancer, nom,
                      ident=None):

    # http.client lit un corps-fichier par blocs de 8 ko et fait un envoi
    # réseau par bloc : sur cent mégas ça fait douze mille appels système,
    # du travail pur pour le Pi. On passe par la connexion directement, elle
    # seule laisse régler ce bloc. (urllib ne le transmet pas.)
    co = http.client.HTTPConnection(machine["hote"], machine.get("port", 7125),
                                    timeout=600, blocksize=BLOC)
    try:
        co.putrequest("POST", "/server/files/upload")
        co.putheader("Content-Type", "multipart/form-data; boundary=%s" % limite)
        co.putheader("Content-Length", str(taille))
        co.endheaders()
        co.send(corps)
        # le corps est entièrement parti : à partir d'ici, promettre un
        # arrêt serait un mensonge — Moonraker a le fichier et, si on a
        # demandé l'impression, elle est déjà lancée
        envoi_fige(ident)
        rep = co.getresponse()
        lu = rep.read()
        if rep.status >= 400:
            raise ValueError("la machine a refusé le fichier (HTTP %d) : %s"
                             % (rep.status, lu[:120].decode("utf-8", "replace")))
    finally:
        co.close()
    if not lancer:
        return "déposé"
    # Moonraker accepte « print=true » à l'envoi, mais pas toujours selon
    # l'état de la machine. On relit, et on redemande explicitement avant
    # de conclure.
    parti, dit = _a_demarre(machine, nom)
    if not parti:
        try:
            lancer_moonraker(machine, nom)
        except Exception as e:
            raise DeposeSansLancement(str(e))
        parti, dit = _a_demarre(machine, nom)
    if not parti:
        raise DeposeSansLancement("la machine n'a pas démarré (elle dit : %s)"
                                  % (dit or "rien"))
    return "lancé"


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


# Ce que la commande de lancement Bambu embarque, et qu'aucune
# documentation officielle ne décrit — tout vient du reverse engineering de
# la communauté. Les valeurs ci-dessous sont les plus neutres possibles :
# on laisse faire ce que le fichier prévoit et on n'ajoute pas de
# calibration que l'utilisateur n'a pas demandée. Chaque machine peut les
# changer dans relais.json, sous « lancement », sans attendre une version
# de l'app.
DEFAUTS_LANCEMENT = {
    "timelapse": False,
    # les deux orthographes : selon la version du firmware, la P1 attend
    # l'une ou l'autre, et celle qu'elle ne connaît pas, elle l'ignore
    "bed_leveling": True,
    "bed_levelling": True,
    "flow_cali": False,
    "vibration_cali": False,
    "layer_inspect": False,
    "use_ams": True,
    "ams_mapping": "",
    "bed_type": "auto",
}


def lancer_bambu(machine, nom, plateau=1):
    """Demande à la machine d'imprimer un plateau d'un fichier déjà déposé.

    Si un seul champ ne lui plaît pas, la machine ignore la commande sans
    rien dire : le fichier reste sur sa carte et se lance à la main. C'est
    le pire cas, et il est sans conséquence."""
    from relais_atelier import _mqtt_longueur, _mqtt_texte, _paquet

    reglages = dict(DEFAUTS_LANCEMENT)
    reglages.update(machine.get("lancement") or {})
    idx = max(1, int(plateau or 1))

    # Le firmware des P1 exige ces quatre identifiants pour une impression
    # partie de la carte, même s'ils ne valent rien : sans eux il écarte la
    # commande sans un mot. C'est précisément le « la machine ignore la
    # commande sans rien dire » du commentaire ci-dessus — sauf que ce
    # n'était pas une fatalité, il manquait des champs.
    ordre = {"print": dict(reglages,
                           sequence_id=str(int(time.time()) % 100000),
                           command="project_file",
                           param="Metadata/plate_%d.gcode" % idx,
                           subtask_name=nom,
                           plate_idx=idx - 1,
                           project_id="0",
                           profile_id="0",
                           task_id="0",
                           subtask_id="0",
                           # on dépose à la racine de la carte, c'est là que
                           # l'écran de la machine va les chercher
                           url="file:///sdcard/%s" % nom)}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(socket.create_connection((machine["hote"], 8883), timeout=10))
    try:
        tete = _mqtt_texte("MQTT") + bytes([4, 0xC2]) + struct.pack(">H", 30)
        corps = (_mqtt_texte("relais-envoi-%d" % int(time.time()))
                 + _mqtt_texte("bblp") + _mqtt_texte(machine.get("code") or ""))
        s.sendall(bytes([0x10]) + _mqtt_longueur(len(tete + corps)) + tete + corps)
        t, b = _paquet(s)
        if t != 2 or b[1] != 0:
            raise Exception("refusée par la machine — code d'accès LAN ou numéro de série")

        charge = json.dumps(ordre, ensure_ascii=False).encode("utf-8")
        pub = _mqtt_texte("device/%s/request" % machine["serie"]) + charge
        s.sendall(bytes([0x30]) + _mqtt_longueur(len(pub)) + pub)
        time.sleep(0.8)          # laisser le paquet partir avant de raccrocher
    finally:
        try:
            s.close()
        except Exception:
            pass
    return idx


# Le canal de contrôle reste inactif pendant toute la copie, puis doit
# encore attendre que la machine ait fini d'écrire sur sa carte. Trente
# secondes suffisaient pour un petit fichier et pas pour un casque.
DELAI_FTP = 180


def _contexte_bambu(assouplir=False):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if assouplir:
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except Exception:
            pass
        for suites in ("DEFAULT@SECLEVEL=0", "ALL@SECLEVEL=0"):
            try:
                ctx.set_ciphers(suites)
                break
            except Exception:
                continue
    return ctx


def _dit_bambu(machine, etape, e):
    """Une panne FTPS tombe toujours sous la même phrase — « The read
    operation timed out » — quelle que soit l'étape. Dire laquelle, et ce
    qu'elle implique, c'est la différence entre une info et un mur."""
    nom = machine.get("nom") or machine.get("hote")
    brut = str(e) or type(e).__name__
    pistes = {
        "connexion": "%s n'a pas répondu en FTPS sur le port 990, ni en TLS "
                     "strict ni en TLS assoupli. Sur une Bambu, ce port ne "
                     "s'ouvre qu'en mode LAN : vérifie « Réglages → Réseau "
                     "→ mode LAN » sur l'écran de la machine." % nom,
        "identification": "%s a refusé l'identification. C'est le code "
                          "d'accès LAN (Access Code, sur l'écran de la "
                          "machine) qu'il faut dans relais.json." % nom,
        # l'identification est passée mais pas les données : c'est la
        # signature d'un pare-feu qui laisse le port 990 et bloque le canal
        # de données, que le FTPS lui rend invisible
        "transfert": "la connexion à %s s'établit mais les données ne passent "
                     "pas — regarde du côté du pare-feu entre le Pi et le "
                     "réseau des machines (pi-15-bambu.bat le dira). Un "
                     "fichier incomplet peut rester sur la carte." % nom,
    }
    return "%s — %s (%s)" % (pistes.get(etape, "envoi vers %s impossible" % nom),
                             brut[:80], etape)


def _ouvrir_bambu(machine):
    code = machine.get("code") or ""
    if not code or code == "A-REMPLIR":
        raise ValueError(
            "le code d'accès LAN de %s n'est pas renseigné dans relais.json "
            "— c'est l'« Access Code » affiché sur l'écran de la machine"
            % (machine.get("nom") or machine.get("hote")))

    ftp = None
    dernier = None
    # Deux tentatives, de la plus stricte à la plus permissive. Le firmware
    # des P1 parle un TLS ancien, et un OpenSSL 3 refuse par défaut ses
    # suites de chiffrement : la poignée de main n'aboutit pas, et ça se
    # présente comme un simple « read operation timed out » qui n'apprend
    # rien. Vérifier le certificat n'aurait de toute façon aucun sens ici —
    # c'est un appareil du réseau local avec un certificat auto-signé.
    for assouplir in (False, True):
        ftp = _FtpImplicite(context=_contexte_bambu(assouplir))
        try:
            ftp.connect(machine["hote"], 990, timeout=DELAI_FTP)
            dernier = None
            break
        except Exception as e:
            dernier = e
            try:
                ftp.close()
            except Exception:
                pass
    if dernier is not None:
        raise ValueError(_dit_bambu(machine, "connexion", dernier))
    try:
        ftp.login("bblp", code)
        ftp.prot_p()
        ftp.set_pasv(True)
    except Exception as e:
        try:
            ftp.close()
        except Exception:
            pass
        raise ValueError(_dit_bambu(machine, "identification", e))
    return ftp


def _retirer_bambu(machine, nom):
    """Sur une connexion neuve, exprès. Un STOR interrompu laisse sa réponse
    226/426 en attente sur le canal de contrôle : ftplib ne l'a pas lue, et
    le DELE suivant lirait cette réponse-là en croyant que c'est la sienne.
    Le canal reste décalé d'une réponse jusqu'au QUIT, si bien que le DELE
    semblait toujours échouer — et que l'on ne pouvait jamais savoir si le
    fichier tronqué avait vraiment été retiré."""
    menage = _ouvrir_bambu(machine)
    try:
        menage.delete(nom)
    finally:
        try:
            menage.close()
        except Exception:
            pass


def pousser_bambu(machine, chemin, nom, lancer, plateau=1, progres=None,
                  ident=None):
    """Dépose le fichier sur la carte de la machine, et le lance si on le
    demande."""
    ftp = _ouvrir_bambu(machine)
    coupe = False
    rate = None
    taille_source = os.path.getsize(chemin)
    try:
        envoye = [0]

        def bloc(morceau):
            envoye[0] += len(morceau)
            if progres:
                progres(envoye[0])

        try:
            with open(chemin, "rb") as f:
                ftp.storbinary("STOR %s" % nom, f, blocksize=BLOC,
                               callback=bloc if progres else None)
        except EnvoiAnnule:
            # on ne relance pas ici : il reste le ménage à faire sur la
            # carte, et un « raise » sauterait par-dessus
            coupe = True
        except Exception as e:
            if envoye[0] >= taille_source > 0:
                # tout est parti : ce qui a lâché, c'est la confirmation
                rate = DeposeSansConfirmation(str(e))
            else:
                rate = ValueError("%s — %d Mo sur %d étaient passés"
                                  % (_dit_bambu(machine, "transfert", e),
                                     envoye[0] // 1048576,
                                     taille_source // 1048576))
    finally:
        try:
            # après une coupure, le canal de contrôle est décalé : on ferme
            # sans écrire dessus plutôt que d'envoyer un QUIT dans le vide
            ftp.close() if (coupe or rate) else ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass

    if rate:
        raise rate
    if coupe:
        try:
            _retirer_bambu(machine, nom)
        except Exception as e:
            raise EnvoiAnnule("envoi arrêté, mais %s n'a pas pu être retiré "
                              "de la carte (%s) — à supprimer depuis l'écran"
                              % (nom, str(e)[:60]))
        raise EnvoiAnnule("envoi arrêté")

    if not lancer:
        envoi_fige(ident)
        return "déposé"

    # dernier moment où renoncer veut encore dire quelque chose : le fichier
    # est déposé, mais l'impression n'est pas partie
    if ident and envoi_veut_arret(ident):
        try:
            _retirer_bambu(machine, nom)
        except Exception:
            pass
        raise EnvoiAnnule("envoi arrêté avant le lancement")

    envoi_fige(ident)
    try:
        lancer_bambu(machine, nom, plateau)
    except Exception as e:
        # le fichier EST sur la carte : le compter comme un échec ferait
        # renvoyer cent mégas pour rien. Seul le démarrage a raté, et il se
        # fait à la main depuis l'écran de la machine.
        raise DeposeSansLancement(str(e))
    # une P1 qui écarte une commande ne répond rien : sans relire son état,
    # on annonçait « lancé » sans rien en savoir
    parti, dit = _a_demarre(machine, nom)
    if not parti:
        raise DeposeSansLancement("la machine n'a pas démarré (elle dit : %s)"
                                  % (dit or "rien"))
    return "lancé"


# Combien de temps on laisse à la machine pour passer de « au repos » à
# « en cours ». Séparé pour que les tests puissent resserrer l'horloge.
ATTENTES_DEMARRAGE = (2, 3, 5)


def _etat_machine(machine):
    """L'état que la machine annonce, maintenant. Sert à vérifier qu'un
    lancement a vraiment pris : une Bambu qui écarte une commande ne dit
    rien, et sans cette relecture on annonçait « lancé » sans savoir."""
    from relais_atelier import lire_bambu, lire_moonraker
    try:
        if machine["type"] == "moonraker":
            return lire_moonraker(machine) or {}
        return lire_bambu(machine, duree=12) or {}
    except Exception:
        return {}


def _a_demarre(machine, nom, avant=None):
    """(oui, ce_qu_elle_dit). On laisse à la machine le temps de changer
    d'avis : une P1 met quelques secondes à passer de « idle » à
    « running », une Creality aussi."""
    dit = ""
    for attente in ATTENTES_DEMARRAGE:
        time.sleep(attente)
        e = _etat_machine(machine)
        etat = str(e.get("state") or "").lower()
        fichier = str(e.get("file") or "")
        dit = "%s %s" % (etat or "?", fichier)
        if etat in ("printing", "running", "en cours", "prepare", "preparing"):
            return True, dit
        # certaines annoncent le fichier avant l'état
        if fichier and os.path.basename(fichier) == os.path.basename(nom):
            return True, dit
    return False, dit.strip()


def lancer_moonraker(machine, nom):
    """Démarrer un fichier déjà sur la machine. Moonraker accepte la
    consigne à l'envoi, mais pas toujours : ce chemin-là est explicite."""
    co = http.client.HTTPConnection(machine["hote"], machine.get("port", 7125),
                                    timeout=30)
    try:
        chemin = "/printer/print/start?filename=" + urllib.parse.quote(nom)
        co.putrequest("POST", chemin)
        co.putheader("Content-Length", "0")
        co.endheaders()
        rep = co.getresponse()
        lu = rep.read()
        if rep.status >= 400:
            raise ValueError("%s a refusé de démarrer %s (HTTP %d) : %s"
                             % (machine.get("nom"), nom, rep.status,
                                lu[:120].decode("utf-8", "replace")))
    finally:
        co.close()


def lancer_seul(biblio, machines, nom_machine, chemin_relatif, plateau=1,
                hote=""):
    """Lancer un fichier DÉJÀ déposé, sans le renvoyer.

    Quand le dépôt a marché et le démarrage non, il n'y a aucune raison de
    repousser cent mégas pour réessayer d'appuyer sur un bouton."""
    machine = trouver_machine(machines, nom_machine, hote)
    if machine is None:
        connues = ", ".join("%s (%s)" % (m.get("nom"), m.get("hote"))
                            for m in machines) or "aucune"
        raise ValueError("le relais ne connait pas %s — il a : %s"
                         % (nom_machine, connues))
    entier = biblio.verifier(chemin_relatif)
    nom = os.path.basename(entier)
    port = machine.get("port", 7125) if machine["type"] == "moonraker" else 8883
    if not joignable(machine["hote"], port):
        raise ValueError("%s ne répond pas sur %s — machine éteinte ?"
                         % (machine.get("nom"), machine["hote"]))

    if machine["type"] == "moonraker":
        lancer_moonraker(machine, nom)
    else:
        lancer_bambu(machine, nom, plateau)

    parti, dit = _a_demarre(machine, nom)
    if not parti:
        raise ValueError(
            "%s a reçu la demande mais n'a pas démarré (elle dit : %s). "
            "Le fichier est sur sa carte : tu peux le lancer depuis son "
            "écran." % (machine.get("nom"), dit or "rien"))

    noter_lancement(machine.get("nom"), chemin_relatif, plateau, nom)
    biblio.noter({"at": int(time.time() * 1000), "machine": machine.get("nom"),
                  "fichier": nom, "etat": "lancé", "chemin": chemin_relatif,
                  "plateau": int(plateau or 1)})
    return {"ok": True, "etat": "lancé", "machine": machine.get("nom"),
            "fichier": nom, "lance": True,
            "dit": "%s a démarré %s" % (machine.get("nom"), nom)}


def trouver_machine(machines, nom_machine, hote=""):
    """Le nom d'une machine est ce que l'utilisateur a tapé sur son
    telephone ; il derive du nom que le relais connait des qu'il la
    renomme. L'adresse, elle, ne bouge pas : on joint dessus d'abord."""
    nom = (nom_machine or "").strip()
    adr = (hote or "").strip()
    for m in machines:
        if adr and m.get("hote") == adr:
            return m
    for m in machines:
        if nom and (m.get("nom") == nom or m.get("hote") == nom):
            return m
    bas = nom.lower()
    for m in machines:
        if bas and str(m.get("nom") or "").strip().lower() == bas:
            return m
    return None


def pousser(biblio, machines, nom_machine, chemin_relatif, lancer=False,
            plateau=1, hote="", ident=None):
    machine = trouver_machine(machines, nom_machine, hote)
    if machine is None:
        connues = ", ".join("%s (%s)" % (m.get("nom"), m.get("hote"))
                            for m in machines) or "aucune"
        raise ValueError("le relais ne connait pas %s%s — il a : %s"
                         % (nom_machine, (" / " + hote) if hote else "",
                            connues))

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
    taille = os.path.getsize(entier)
    envoi_commence(ident, nom, machine.get("nom"), taille)
    progres = (lambda n: envoi_avance(ident, n)) if ident else None
    try:
        if machine["type"] == "moonraker":
            etat = pousser_moonraker(machine, entier, nom, lancer, progres, ident)
        else:
            etat = pousser_bambu(machine, entier, nom, lancer, plateau, progres,
                                 ident)
    except EnvoiAnnule:
        envoi_annule(ident)
        raise
    except DeposeSansConfirmation as e:
        # le fichier est passé en entier ; seule la confirmation manque. On
        # ne lance rien dans ce cas : lancer sans savoir si la machine a
        # bien écrit le fichier serait pire que de ne rien faire.
        envoi_termine(ident, True, "déposé, sans confirmation")
        biblio.noter({"at": int(time.time() * 1000), "machine": machine.get("nom"),
                      "fichier": nom, "etat": "envoyé", "chemin": chemin_relatif,
                      "pourquoi": "la machine n'a pas confirmé : %s" % str(e)[:100]})
        return {"ok": True, "etat": "déposé", "machine": machine.get("nom"),
                "fichier": nom, "lance": False,
                "dit": "tout le fichier est parti, mais %s n'a pas confirmé "
                       "dans le délai — il est très probablement sur sa carte, "
                       "à vérifier depuis l'écran avant de lancer"
                       % machine.get("nom")}
    except DeposeSansLancement as e:
        # le fichier est sur la machine : la moitié qui a marché compte, et
        # il ne faut surtout pas le renvoyer
        etat = "déposé"
        envoi_termine(ident, True, "déposé — lancement refusé")
        biblio.noter({"at": int(time.time() * 1000), "machine": machine.get("nom"),
                      "fichier": nom, "etat": "envoyé", "chemin": chemin_relatif,
                      "pourquoi": "lancement refusé : %s" % str(e)[:120]})
        return {"ok": True, "etat": etat, "machine": machine.get("nom"),
                "fichier": nom, "lance": False,
                "dit": "déposé, mais le lancement a été refusé (%s) — "
                       "à démarrer depuis l'écran de la machine" % str(e)[:90]}
    except Exception as e:
        envoi_termine(ident, False, str(e))
        raise
    envoi_termine(ident, True, etat)
    if etat == "lancé":
        # on vient de lancer : on sait quel plateau tourne, la machine non
        noter_lancement(machine.get("nom"), chemin_relatif, plateau, nom)
    biblio.noter({"at": int(time.time() * 1000), "machine": machine.get("nom"),
                  "fichier": nom, "etat": "lancé" if etat == "lancé" else "envoyé",
                  "chemin": chemin_relatif,
                  "plateau": int(plateau or 1) if lancer else None})
    return {"ok": True, "etat": etat, "machine": machine.get("nom"), "fichier": nom,
            "lance": etat == "lancé"}


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
                                            "machines": self.ctx.etats,
                                            "envois": envois_publics()})
            if route.path == "/biblio":
                # les accusés voyagent avec l'index publié sur le canal ; il
                # faut qu'ils voyagent aussi avec celui servi sur place,
                # sinon l'app à l'atelier ne sait jamais ce qu'est devenu
                # l'ordre qu'elle a passé
                with VERROU_ENVOIS:
                    accuses = list(ACCUSES[-12:])
                return self._repondre(200, dict(self.ctx.biblio.index(),
                                                ok=True, accuses=accuses))
            if route.path == "/vignette":
                chemin = (params.get("chemin") or [""])[0]
                idx = int((params.get("plateau") or ["1"])[0])
                octets = vignette(self.ctx.biblio, chemin, idx)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(octets)))
                self.end_headers()
                self.wfile.write(octets)
                return
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
                rel = self.ctx.biblio.fixer_exemplaires(
                    corps.get("chemin"), corps.get("n"), corps.get("plateau"))
                return self._repondre(200, {"ok": True, "chemin": rel})
            if route.path == "/marquer":
                rel = self.ctx.biblio.marquer(
                    corps.get("chemin"), corps.get("plateau", 1),
                    bool(corps.get("fait", True)), corps.get("machine") or "")
                return self._repondre(200, {"ok": True, "chemin": rel})
            if route.path == "/lancer":
                res = lancer_seul(self.ctx.biblio, self.ctx.machines,
                                  corps.get("machine"), corps.get("chemin"),
                                  corps.get("plateau", 1),
                                  corps.get("hote") or "")
                return self._repondre(200, res)
            if route.path == "/annuler":
                ok, dit = annuler_envoi(corps.get("cible") or "")
                return self._repondre(200 if ok else 409,
                                      {"ok": ok, "dit": dit})
            if route.path == "/refaire":
                rel = self.ctx.biblio.marquer_refaire(
                    corps.get("chemin"), corps.get("plateau", 1),
                    bool(corps.get("refaire", True)))
                return self._repondre(200, {"ok": True, "chemin": rel})
            if route.path == "/commande":
                rel = self.ctx.biblio.fixer_commande(corps.get("chemin"),
                                                     corps.get("commande"))
                return self._repondre(200, {"ok": True, "chemin": rel})
            if route.path == "/pousser":
                res = pousser(self.ctx.biblio, self.ctx.machines,
                              corps.get("machine"), corps.get("chemin"),
                              bool(corps.get("lancer")), corps.get("plateau", 1),
                              corps.get("hote") or "",
                              corps.get("id") or _nouvel_ident())
                return self._repondre(200, res)
        except EnvoiAnnule as e:
            return self._repondre(409, {"ok": False, "arrete": True,
                                        "dit": str(e)[:200] or "envoi arrêté",
                                        "error": str(e)[:200] or "envoi arrêté"})
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
                chemin, plateau = resoudre_plateau(biblio, nom, fichier,
                                                   etat.get("brut") or {})
                EN_COURS[cle] = {"fichier": fichier, "debut": etat.get("at"),
                                 "pourcent": pourcent, "brut": etat.get("brut") or {},
                                 "machine": nom, "chemin": chemin, "plateau": plateau}
                if chemin:
                    oublier_publication()      # l'app doit voir « en cours »
            else:
                suivi["pourcent"] = max(suivi.get("pourcent", -1), pourcent)
                if etat.get("brut"):
                    suivi["brut"] = etat["brut"]
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
        # ce que la machine disait d'elle-même pendant l'impression : c'est
        # là-dedans qu'on cherchera de quoi reconnaître le plateau imprimé
        if suivi.get("brut"):
            ligne["brut"] = suivi["brut"]
        if suivi.get("chemin"):
            ligne["chemin"] = suivi["chemin"]
            ligne["plateau"] = suivi.get("plateau")
            conclure_plateau(biblio, suivi["chemin"], suivi.get("plateau") or 1,
                             issue, nom)
        biblio.noter(ligne)
        ajouts.append(ligne)
        EN_COURS.pop(cle, None)
    return ajouts


# ----------------------------------------------------------------------
# les plateaux d'un fichier Bambu
# ----------------------------------------------------------------------
#
# Un .gcode.3mf exporté par Bambu Studio peut contenir plusieurs plateaux,
# chacun avec son propre gcode dans Metadata/plate_N.gcode. C'est une
# impression chacun : les compter séparément est la seule façon de savoir
# ce qui reste à sortir pour une commande.
#
# slice_info.config, à côté, donne pour chaque plateau son poids et sa
# durée prévue. S'il manque ou qu'il a changé de forme, on se rabat sur la
# simple présence des gcodes : mieux vaut une liste sans chiffres qu'un
# fichier qu'on refuse de lire.

PLATEAU_GCODE = re.compile(r"(?:^|/)Metadata/plate_(\d+)\.gcode$", re.I)
PLATEAU_IMAGE = re.compile(r"(?:^|/)Metadata/plate_(\d+)(?:_small)?\.png$", re.I)

_CACHE_PLATEAUX = {}


def plateaux(chemin):
    """[{idx, minutes, grammes, objets, vignette}] pour un 3mf, [] sinon.

    Le résultat est gardé tant que le fichier ne bouge pas : ouvrir chaque
    zip à chaque listage rendrait l'écran lent dès quelques dizaines de
    fichiers."""
    if not chemin.lower().endswith(".3mf"):
        return []
    try:
        st = os.stat(chemin)
    except OSError:
        return []
    cle = (st.st_mtime_ns, st.st_size)
    garde = _CACHE_PLATEAUX.get(chemin)
    if garde and garde[0] == cle:
        return garde[1]

    trouves = {}
    try:
        with zipfile.ZipFile(chemin) as z:
            noms = z.namelist()
            for nom in noms:
                m = PLATEAU_GCODE.search(nom)
                if m:
                    trouves[int(m.group(1))] = {"idx": int(m.group(1)), "minutes": 0,
                                                "grammes": 0, "objets": [], "vignette": ""}
            for nom in noms:
                m = PLATEAU_IMAGE.search(nom)
                if m and int(m.group(1)) in trouves and not trouves[int(m.group(1))]["vignette"]:
                    trouves[int(m.group(1))]["vignette"] = nom
            if trouves:
                for nom in noms:
                    if nom.lower().endswith("slice_info.config"):
                        _lire_slice_info(z.read(nom).decode("utf-8", "replace"), trouves)
                        break
    except Exception:
        trouves = {}

    out = [trouves[k] for k in sorted(trouves)]
    _CACHE_PLATEAUX[chemin] = (cle, out)
    return out


def _lire_slice_info(xml, trouves):
    """slice_info.config est un petit XML : une balise <plate> par plateau,
    des <metadata key= value=> dedans. On n'en lit que trois choses."""
    for bloc in re.findall(r"<plate\b.*?</plate>", xml, re.S):
        idx = re.search(r'key="index"\s+value="(\d+)"', bloc)
        if not idx or int(idx.group(1)) not in trouves:
            continue
        p = trouves[int(idx.group(1))]
        secondes = re.search(r'key="prediction"\s+value="([\d.]+)"', bloc)
        if secondes:
            p["minutes"] = int(round(float(secondes.group(1)) / 60.0))
        poids = re.search(r'key="weight"\s+value="([\d.]+)"', bloc)
        if poids:
            p["grammes"] = int(round(float(poids.group(1))))
        for obj in re.findall(r'<object\b[^>]*\bname="([^"]*)"', bloc):
            nom = os.path.splitext(os.path.basename(obj))[0]
            if nom and nom not in p["objets"]:
                p["objets"].append(nom)
        p["objets"] = p["objets"][:6]


def vignette(biblio, chemin_relatif, idx):
    """Les octets PNG de l'aperçu d'un plateau, pour que l'app montre ce
    qu'elle propose d'imprimer au lieu d'un nom de fichier."""
    entier = biblio.verifier(chemin_relatif)
    for p in plateaux(entier):
        if p["idx"] == int(idx) and p["vignette"]:
            with zipfile.ZipFile(entier) as z:
                return z.read(p["vignette"])
    raise ValueError("pas d'aperçu pour ce plateau")


# ----------------------------------------------------------------------
# la bibliothèque hors de l'atelier
# ----------------------------------------------------------------------
#
# Le service HTTP ci-dessus ne répond que sur le réseau local. C'est bien
# pour envoyer un fichier de cinquante mégaoctets, mais tout le reste —
# voir ce qui reste à sortir d'une commande, cocher un plateau — devrait
# marcher de n'importe où, comme l'état des machines.
#
# On passe donc par le même canal que le relevé : le relais publie son
# index, l'app le lit. Rien à ouvrir sur la box, rien à installer de plus.
#
# Deux contraintes de ntfy commandent la forme : un message fait quelques
# kilo-octets, et le compte gratuit n'en accepte que 250 par jour. L'index
# est donc compressé puis découpé, et republié seulement quand il change.

TAILLE_LOT = 3000
_PUBLIE = {"empreinte": None, "at": 0}


def resume(index):
    """L'index allégé de ce qui ne sert qu'en local : les chemins internes
    des vignettes et la racine du disque n'ont rien à faire sur Internet."""
    fichiers = []
    for f in index.get("fichiers") or []:
        plateaux_legers = []
        for p in f.get("plateaux") or []:
            plateaux_legers.append({k: v for k, v in p.items() if k != "vignette"})
        fichiers.append(dict(f, plateaux=plateaux_legers))
    with VERROU_ENVOIS:
        accuses = list(ACCUSES[-12:])
    return {"familles": index.get("familles") or [], "fichiers": fichiers,
            "commandes": index.get("commandes") or [],
            "accuses": accuses}


def lots_biblio(index, at=None):
    """[chaînes JSON] à publier, ou [] si rien n'a changé depuis la
    dernière fois."""
    corps = json.dumps(resume(index), ensure_ascii=False, sort_keys=True)
    empreinte = hashlib.sha256(corps.encode("utf-8")).hexdigest()[:16]
    if empreinte == _PUBLIE["empreinte"]:
        return []

    # du JSON se compresse d'un facteur six ou sept : sans ça, une
    # bibliothèque un peu fournie coûterait dix messages à chaque envoi
    serre = base64.b64encode(zlib.compress(corps.encode("utf-8"), 9)).decode("ascii")
    morceaux = [serre[i:i + TAILLE_LOT] for i in range(0, len(serre), TAILLE_LOT)] or [""]
    quand = at or int(time.time() * 1000)
    _PUBLIE["empreinte"] = empreinte
    _PUBLIE["at"] = quand
    return [json.dumps({"t": "biblio", "at": quand, "e": empreinte,
                        "lot": i + 1, "lots": len(morceaux), "d": m},
                       ensure_ascii=False)
            for i, m in enumerate(morceaux)]


def oublier_publication():
    """Force la republication au prochain tour — après un ordre appliqué,
    pour que l'app voie tout de suite le résultat de son geste."""
    _PUBLIE["empreinte"] = None


# ----------------------------------------------------------------------
# les ordres venus de l'app
# ----------------------------------------------------------------------
#
# Dans l'autre sens, l'app publie sur le même canal et le relais lit. Le
# sujet ntfy est déjà le secret du relais, mais il ne protège que la
# lecture : quelqu'un qui le connaîtrait pourrait cocher des plateaux. Un
# ordre porte donc une signature calculée avec le jeton, que seuls l'app
# et le Pi connaissent.

ORDRES_VUS = []
PEREMPTION_ORDRE = 2 * 3600 * 1000

# Un ordre parti par le canal ne rend aucune reponse : l'app publie et s'en
# va. Le relais consigne donc ce qu'il a fait de chaque ordre, et le joint à
# l'index qu'il publie — c'est ainsi que l'app apprend si son geste a abouti,
# et pourquoi quand il a échoué.
ACCUSES = []


def accuser(ident, ok, dit, fini=True, arrete=False):
    """Un accuse par ordre, remplace quand la suite arrive.

    Un envoi de fichier dure : le relais le prend en charge tout de suite,
    et ne sait que plusieurs minutes plus tard s'il a abouti. Il accuse
    donc deux fois — « recu, en cours », puis le resultat — et l'app sait
    a quoi s'en tenir entre les deux au lieu de conclure au silence."""
    if not ident:
        return
    nouveau = {"id": ident, "at": int(time.time() * 1000),
               "ok": bool(ok), "dit": dit, "fini": bool(fini),
               # un arrêt voulu n'est pas une réussite, mais ce n'est pas
               # non plus un refus : l'app doit pouvoir faire la différence
               # sans lire la phrase
               "arrete": bool(arrete)}
    # sous verrou : le provisoire part du fil principal et le definitif du
    # fil d'envoi. Sans ca les deux pouvaient s'ajouter tous les deux, et
    # l'app lisant le dernier serait restee sur « reçu, en cours » pour
    # toujours.
    with VERROU_ENVOIS:
        for i, a in enumerate(ACCUSES):
            if a.get("id") == ident:
                # un accuse definitif ecrase le provisoire ; l'inverse jamais
                if a.get("fini") and not fini:
                    return
                ACCUSES[i] = nouveau
                break
        else:
            ACCUSES.append(nouveau)
        del ACCUSES[:-30]
    oublier_publication()


# On signe une suite de champs séparés par un caractère qui n'apparaît
# jamais dans un nom de fichier, et non du JSON : deux langages ne
# sérialisent pas le JSON de la même façon, et une signature qui dépend
# d'un espace après les deux-points casserait au premier accent.
# La signature porte desormais sur TOUTES les cles de l'ordre, triees, sous
# la forme cle=valeur. Les trois premieres versions signaient une liste
# fixe, si bien que le moindre champ ajoute obligeait a changer les deux
# cotes le meme jour — et un telephone pas encore mis a jour se faisait
# refuser ses ordres sans comprendre pourquoi. Avec les cles dans le corps
# signe, un champ de plus ne casse plus rien.
CHAMPS_SIGNES_3_2 = ("id", "at", "quoi", "chemin", "plateau", "fait", "n",
                     "commande", "machine", "lancer", "hote", "refaire")
CHAMPS_SIGNES_3_1 = ("id", "at", "quoi", "chemin", "plateau", "fait", "n",
                     "commande", "machine", "lancer")
ANCIENS_CHAMPS = (CHAMPS_SIGNES_3_2, CHAMPS_SIGNES_3_1)


def _valeur_signee(ordre, cle):
    v = ordre.get(cle)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def corps_signe(ordre, champs=None):
    if champs is None:
        cles = sorted(c for c in ordre.keys() if c != "sig")
        return "\u001f".join("%s=%s" % (c, _valeur_signee(ordre, c)) for c in cles)
    return "\u001f".join(_valeur_signee(ordre, c) for c in champs)


def signer(jeton, ordre, champs=None):
    corps = corps_signe(ordre, champs)
    return hmac.new(str(jeton or "").encode("utf-8"),
                    corps.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def signature_valide(jeton, ordre):
    donnee = str(ordre.get("sig") or "")
    if hmac.compare_digest(signer(jeton, ordre), donnee):
        return True
    for champs in ANCIENS_CHAMPS:          # telephones pas encore a jour
        if hmac.compare_digest(signer(jeton, ordre, champs), donnee):
            return True
    return False


def _pousser_a_part(biblio, machines, machine, chemin, lancer, plateau=1,
                    ident=None, hote=""):
    """L'envoi demandé à distance. Le résultat, bon ou mauvais, revient à
    l'app par l'accusé joint au prochain index."""
    try:
        res = pousser(biblio, machines, machine, chemin, lancer, plateau, hote,
                      ident)
        print("%s — %s %s sur %s" % (time.strftime("%H:%M:%S"), res["etat"],
                                     res["fichier"], res["machine"]), flush=True)
        accuser(ident, True, "%s %s sur %s" % (res["fichier"], res["etat"], machine))
    except EnvoiAnnule as e:
        # arrêt demandé : ce n'est pas une panne, et l'accusé de l'envoi doit
        # le dire autrement qu'un échec
        dit = str(e) or "envoi arrêté avant la fin"
        print("%s — envoi de %s vers %s arrêté : %s"
              % (time.strftime("%H:%M:%S"), os.path.basename(chemin), machine, dit),
              flush=True)
        biblio.noter({"at": int(time.time() * 1000), "machine": machine,
                      "fichier": os.path.basename(chemin), "etat": "annulé",
                      "chemin": chemin, "pourquoi": dit[:200]})
        accuser(ident, False, dit[:150], arrete=True)
    except Exception as e:
        envoi_termine(ident, False, str(e))
        biblio.noter({"at": int(time.time() * 1000), "machine": machine,
                      "fichier": os.path.basename(chemin), "etat": "refusé",
                      "chemin": chemin, "pourquoi": str(e)[:200]})
        print("%s — envoi vers %s impossible : %s"
              % (time.strftime("%H:%M:%S"), machine, e), flush=True)
        accuser(ident, False, str(e)[:150])
    oublier_publication()


def appliquer_ordre(biblio, ordre, jeton, machines=None):
    """Renvoie une phrase pour le journal, ou None si l'ordre est écarté."""
    ident = ordre.get("id")
    if not ident or ident in ORDRES_VUS:
        return None
    quand = int(ordre.get("at") or 0)
    if abs(int(time.time() * 1000) - quand) > PEREMPTION_ORDRE:
        return None          # trop vieux : sans doute un message rejoué
    if jeton and not signature_valide(jeton, ordre):
        # on le note comme vu : sans ça le même ordre serait rejugé à chaque
        # relève et remplirait le journal
        ORDRES_VUS.append(ident)
        del ORDRES_VUS[:-200]
        accuser(ident, False, "jeton de l'app différent de celui du relais")
        return "ordre refusé (signature)"

    ORDRES_VUS.append(ident)
    del ORDRES_VUS[:-200]

    quoi = ordre.get("quoi")
    chemin = ordre.get("chemin") or ""

    if quoi == "pousser":
        # Le fichier est déjà sur le Pi, et le Pi est sur le réseau des
        # machines : le téléphone n'a qu'à dire lequel va où. L'envoi dure
        # le temps qu'il dure, donc dans un fil à part — sinon la relève
        # des machines s'arrêterait pendant la copie.
        # On inscrit l'envoi AVANT de lancer le fil. Sans ça il manquerait
        # au relevé de cette relève-ci et la barre n'apparaîtrait qu'au
        # suivant — et inscrit après, il écrasait l'entrée que le fil
        # venait de poser avec la vraie taille. Le fil la complète, et en
        # cas de refus c'est son envoi_termine qui la solde.
        envoi_commence(ident, os.path.basename(chemin), ordre.get("machine"), 0)
        threading.Thread(target=_pousser_a_part,
                         args=(biblio, machines or [], ordre.get("machine"),
                               chemin, bool(ordre.get("lancer")),
                               ordre.get("plateau", 1), ident,
                               ordre.get("hote") or ""),
                         daemon=True).start()
        accuser(ident, True, "reçu — %s part vers %s, ça prend le temps du "
                "transfert" % (os.path.basename(chemin), ordre.get("machine")),
                fini=False)
        return "envoi de %s vers %s demandé" % (os.path.basename(chemin),
                                                ordre.get("machine"))
    try:
        if quoi == "marquer":
            biblio.marquer(chemin, ordre.get("plateau", 1),
                           bool(ordre.get("fait", True)), ordre.get("machine") or "")
            dit = "plateau %s de %s : %s" % (
                ordre.get("plateau"), os.path.basename(chemin),
                "fait" if ordre.get("fait", True) else "remis à faire")
            accuser(ident, True, dit)
            return dit
        if quoi == "lancer":
            res = lancer_seul(biblio, machines or [], ordre.get("machine"),
                              chemin, ordre.get("plateau", 1),
                              ordre.get("hote") or "")
            accuser(ident, True, res["dit"])
            return res["dit"]
        if quoi == "annuler":
            ok, dit = annuler_envoi(ordre.get("cible") or "")
            accuser(ident, ok, dit)
            return dit
        if quoi == "refaire":
            refaire = bool(ordre.get("refaire", True))
            biblio.marquer_refaire(chemin, ordre.get("plateau", 1), refaire)
            dit = "plateau %s de %s : %s" % (
                ordre.get("plateau"), os.path.basename(chemin),
                "a refaire" if refaire else "plus a refaire")
            accuser(ident, True, dit)
            return dit
        if quoi == "exemplaires":
            biblio.fixer_exemplaires(chemin, ordre.get("n"), ordre.get("plateau"))
            dit = "%s : %s exemplaire(s)" % (os.path.basename(chemin), ordre.get("n"))
            accuser(ident, True, dit)
            return dit
        if quoi == "commande":
            biblio.fixer_commande(chemin, ordre.get("commande"))
            dit = "%s rattaché à %s" % (os.path.basename(chemin),
                                        ordre.get("commande") or "aucune commande")
            accuser(ident, True, dit)
            return dit
        if quoi == "ping":
            # sert au bouton Tester de l'app : il prouve que le jeton passe
            accuser(ident, True, "jeton accepté")
            return "test du jeton depuis l'app : accepté"
    except ValueError as e:
        accuser(ident, False, str(e)[:150])
        return "ordre impossible : %s" % e
    return None


# ----------------------------------------------------------------------
# quel plateau est en train de sortir
# ----------------------------------------------------------------------
#
# Une machine annonce un fichier, pas un plateau. Pour suivre un fichier
# multi-plateaux il faut retrouver lequel tourne, et il y a trois façons
# d'y arriver, de la plus sûre à la moins sûre :
#
#   1. c'est le relais qui a lancé : il sait exactement quoi et lequel ;
#   2. la machine nomme le plateau dans ses champs bruts
#      (« Metadata/plate_3.gcode ») — vrai sur certaines versions ;
#   3. le fichier n'a qu'un plateau : c'est forcément celui-là.
#
# Quand aucune ne marche — un multi-plateaux lancé depuis l'écran d'une
# machine qui ne dit pas lequel — on reste sur le fichier, et le plateau
# se coche à la main comme avant.

ATTENDU = {}
PEREMPTION_ATTENTE = 15 * 60


def en_cours_ici(chemin_relatif):
    """{plateau: machine} pour ce fichier, d'après ce qui tourne à l'instant.
    C'est la seule information de l'index qui ne vienne pas du disque."""
    out = {}
    for suivi in EN_COURS.values():
        if suivi.get("chemin") == chemin_relatif and suivi.get("plateau"):
            out[int(suivi["plateau"])] = suivi.get("machine") or ""
    return out


def noter_lancement(nom_machine, chemin, plateau, fichier):
    ATTENDU[nom_machine] = {"chemin": chemin, "plateau": int(plateau or 1),
                            "fichier": fichier, "at": time.time()}


def _plateau_annonce(brut):
    """Le numéro de plateau que la machine donne d'elle-même, s'il y est."""
    for valeur in (brut or {}).values():
        m = re.search(r"plate_(\d+)", str(valeur))
        if m:
            return int(m.group(1))
    for cle, valeur in (brut or {}).items():
        if "plate" in cle.lower() and str(valeur).strip().lstrip("-").isdigit():
            n = int(valeur)
            return n + 1 if cle.lower().endswith("idx") else n
    return None


def resoudre_plateau(biblio, nom_machine, fichier, brut):
    """(chemin, plateau) du plateau qui tourne, (None, None) si on ne sait pas."""
    attendu = ATTENDU.get(nom_machine)
    if attendu and (time.time() - attendu["at"]) < PEREMPTION_ATTENTE:
        if base_nom(attendu["fichier"]) == base_nom(fichier):
            # une intention ne vaut que pour l'impression qu'elle a lancée :
            # la garder ferait attribuer la suivante au même plateau
            ATTENDU.pop(nom_machine, None)
            return attendu["chemin"], attendu["plateau"]

    chemins = biblio.chemins_par_nom().get(base_nom(fichier)) or []
    if len(chemins) != 1:
        return None, None
    chemin = chemins[0]

    annonce = _plateau_annonce(brut)
    if annonce:
        return chemin, annonce

    try:
        liste = plateaux(biblio.verifier(chemin))
    except ValueError:
        return None, None
    if len(liste) <= 1:
        return chemin, (liste[0]["idx"] if liste else 1)
    return None, None


def conclure_plateau(biblio, chemin, plateau, issue, machine):
    """Un plateau qui vient de finir : sorti, ou à refaire."""
    try:
        multi = len(plateaux(biblio.verifier(chemin))) > 1
    except ValueError:
        return
    if issue == "fini":
        if multi:
            biblio.marquer(chemin, plateau, True, machine)
        else:
            # un fichier à un seul plateau est déjà compté par l'historique :
            # le marquer en plus le ferait compter deux fois
            biblio.marquer_refaire(chemin, plateau, False)
    else:
        biblio.marquer_refaire(chemin, plateau, True)
    oublier_publication()
