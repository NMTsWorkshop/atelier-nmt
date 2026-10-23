#!/usr/bin/env python3
"""Le relais en entier, de l'ordre publié jusqu'au fichier sur la machine.

Les tests unitaires vérifient chacun une pièce ; celui-ci vérifie la
chaîne, parce que c'est elle qui a cassé quatre fois de suite — jamais
au même endroit. Il monte un faux ntfy, un faux Moonraker, un faux
Bambu, et fait tourner la vraie boucle du relais contre eux.

    python3 test/bout_en_bout.py
"""

import ftplib
import json
import os
import re
import socket
import struct
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "relais"))
sys.path.insert(0, os.path.join(RACINE, "test"))

import biblio                                              # noqa: E402

# le montage de test remplace _ouvrir_bambu ; on garde l'original sous la
# main pour pouvoir vérifier ce que fait vraiment le relais
VRAI_OUVRIR_BAMBU = None
import relais_atelier as R                                 # noqa: E402

VRAI_OUVRIR_BAMBU = biblio._ouvrir_bambu
VRAI_LANCER_BAMBU = biblio.lancer_bambu

ECHECS = []
FAIT = []


def verifie(titre, condition, detail=""):
    if condition:
        FAIT.append(titre)
        print("  ok   %s" % titre)
    else:
        ECHECS.append("%s%s" % (titre, (" — " + detail) if detail else ""))
        print("  ECHEC %s%s" % (titre, (" — " + detail) if detail else ""))


# ----------------------------------------------------------------------
# le faux ntfy : le canal par lequel l'app et le relais se parlent
# ----------------------------------------------------------------------

class Canal:
    """Assez de ntfy pour ce dont le relais se sert : publier un message,
    et relire ceux d'un sujet."""

    def __init__(self):
        self.messages = []
        self.verrou = threading.Lock()
        canal = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                corps = self.rfile.read(n).decode("utf-8")
                sujet = self.path.strip("/")
                with canal.verrou:
                    canal.messages.append({
                        "id": "m%d" % len(canal.messages),
                        "time": int(time.time()),
                        "event": "message",
                        "topic": sujet,
                        "title": self.headers.get("Title", ""),
                        "message": corps,
                    })
                self._rendre(b'{"id":"ok"}')

            def do_GET(self):
                sujet = self.path.strip("/").split("/")[0]
                with canal.verrou:
                    lignes = [json.dumps(m, ensure_ascii=False)
                              for m in canal.messages if m["topic"] == sujet]
                self._rendre(("\n".join(lignes) + "\n").encode("utf-8"))

            def _rendre(self, corps):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d/" % self.srv.server_address[1]

    def derniers(self, titre=None):
        with self.verrou:
            return [m for m in self.messages if titre is None or m["title"] == titre]

    def poster(self, sujet, corps, titre):
        """Un message brut sur le canal, comme l'app le ferait."""
        import urllib.request
        req = urllib.request.Request(self.base + sujet,
                                     data=corps.encode("utf-8"), method="POST")
        req.add_header("Title", titre)
        with urllib.request.urlopen(req, timeout=5):
            pass

    def publier_compta(self, sujet, commandes, lots=None, at=None, tronquer=0):
        """Ce que l'app publie pour la compta : la liste ENTIÈRE, découpée en
        lots qui tiennent dans une notification, chacun portant le même
        horodatage et le nombre de lots attendus.

        « tronquer » en retire quelques-uns : un envoi incomplet ne doit pas
        passer pour une liste qui a rétréci."""
        self._compta = getattr(self, "_compta", 0) + 1
        at = int(at if at is not None else time.time() * 1000 + self._compta)
        paquets = lots if lots is not None else [commandes]
        messages = [json.dumps({"t": "compta", "at": at, "lot": i + 1,
                                "lots": len(paquets), "c": p},
                               ensure_ascii=False)
                    for i, p in enumerate(paquets)]
        for m in (messages[:-tronquer] if tronquer else messages):
            self.poster(sujet, m, "compta")
        return at

    def publier_ordre(self, sujet, ordre, jeton, signer=True):
        """Exactement ce que fait Relay.ordre() dans l'app : poser t, id et
        at, puis signer le tout. L'ordre des champs compte : la signature
        porte sur toutes les clés présentes."""
        ordre = dict(ordre)
        ordre["t"] = "ordre"
        ordre.setdefault("id", "ordre-%d" % (time.time() * 1000000 % 10000000))
        ordre.setdefault("at", int(time.time() * 1000))
        ordre["sig"] = biblio.signer(jeton, ordre) if signer else "0" * 32
        self.poster(sujet, json.dumps(ordre, ensure_ascii=False), "ordre")
        return ordre["id"]


# ----------------------------------------------------------------------
# les fausses machines
# ----------------------------------------------------------------------

class FauxMoonraker:
    def __init__(self, lenteur=0.0, refuse=False, hote="127.0.0.1"):
        self.recu = {}
        self.lance = []
        self.lenteur = lenteur
        self.refuse = refuse
        faux = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                lu = 0
                while lu < n:
                    bout = self.rfile.read(min(1 << 18, n - lu))
                    if not bout:
                        break
                    lu += len(bout)
                    if faux.lenteur:
                        time.sleep(faux.lenteur)
                faux.recu["dernier"] = lu
                if faux.refuse:
                    corps = b'{"error":"disque plein"}'
                    self.send_response(500)
                else:
                    corps = b'{"result":"ok"}'
                    self.send_response(200)
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def do_GET(self):
                corps = json.dumps({"result": {"status": {
                    "print_stats": {"state": "standby", "filename": ""},
                    "heater_bed": {}, "extruder": {},
                    "display_status": {"progress": 0}}}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer((hote, 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.hote = hote
        self.port = self.srv.server_address[1]


def charger_faux_bambu():
    from faux_bambu import FauxBambu
    return FauxBambu


# ----------------------------------------------------------------------
# la fausse boutique : assez de l'API Admin pour ce que le relais demande
# ----------------------------------------------------------------------

class FausseBoutique:
    """L'identifiant de la boutique, et metafieldsSet. Rien d'autre.

    Elle vérifie le jeton : un jeton oublié dans relais.json doit se voir
    ici, pas chez Nathan."""

    JETON = "shpat_de_test"

    def __init__(self, refus=None):
        self.appels = []            # « shop » ou « metafieldsSet », dans l'ordre
        self.ecrits = {}            # cle -> le champ entier tel qu'il est arrivé
        self.jetons = []
        self.refus = refus          # message d'erreur à faire renvoyer
        faux = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                brut = self.rfile.read(n).decode("utf-8")
                faux.jetons.append(self.headers.get("X-Shopify-Access-Token"))
                if self.headers.get("X-Shopify-Access-Token") != FausseBoutique.JETON:
                    return self._rendre(401, {"errors": [
                        {"message": "Invalid API key or access token"}]})
                try:
                    charge = json.loads(brut)
                except ValueError:
                    return self._rendre(400, {"errors": [{"message": "corps illisible"}]})
                requete = charge.get("query") or ""
                if "metafieldsSet" in requete:
                    champs = (charge.get("variables") or {}).get("m") or []
                    faux.appels.append("metafieldsSet")
                    if faux.refus:
                        return self._rendre(200, {"data": {"metafieldsSet": {
                            "userErrors": [{"field": ["metafields", "0", "value"],
                                            "message": faux.refus}]}}})
                    for c in champs:
                        faux.ecrits[c.get("key")] = c
                    return self._rendre(200, {"data": {"metafieldsSet":
                                                       {"userErrors": []}}})
                if "shop" in requete:
                    faux.appels.append("shop")
                    return self._rendre(200, {"data": {"shop": {
                        "id": "gid://shopify/Shop/770000"}}})
                return self._rendre(200, {"errors": [{"message": "requête inconnue"}]})

            def _rendre(self, code, charge):
                corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.domaine = "127.0.0.1:%d" % self.srv.server_address[1]

    def valeur(self, cle):
        return (self.ecrits.get(cle) or {}).get("value")

    def genre(self, cle):
        return (self.ecrits.get(cle) or {}).get("type")

    def combien(self, quoi="metafieldsSet"):
        return sum(1 for a in self.appels if a == quoi)


# ----------------------------------------------------------------------

def monter_atelier(lenteur=0.0):
    dossier = tempfile.mkdtemp(prefix="atelier-")
    bib = biblio.Bibliotheque(dossier, ["k2", "p1s"])
    # le casque est gros exprès : un fichier de quelques mégas tient tout
    # entier dans les tampons des sockets, si bien que le relais a fini
    # d'émettre avant même que la machine ait fini de lire — et l'arrêt en
    # vol n'aurait jamais lieu en vol
    for famille, nom, mo in (("k2", "socle.gcode", 3), ("p1s", "casque.3mf", 24)):
        with open(os.path.join(dossier, famille, nom), "wb") as f:
            f.write(b"\0" * (mo * 1024 * 1024))

    moon = FauxMoonraker(lenteur=lenteur, hote="127.0.0.2")
    FauxBambu = charger_faux_bambu()
    # le Bambu s'arrête à mi-fichier et attend : l'arrêt en vol doit se
    # jouer sur un état, pas sur un chronomètre — sinon le test passe ou
    # casse selon la vitesse de la machine qui l'exécute
    bam = FauxBambu(lenteur=0.0, seuil=2 * 1024 * 1024)

    machines = [
        {"nom": "K2 Plus 1", "type": "moonraker", "hote": "127.0.0.2", "port": moon.port},
        {"nom": "P1S 1", "type": "bambu", "hote": "127.0.0.3", "serie": "01P0", "code": "x"},
    ]

    class FtpClair(ftplib.FTP):
        def prot_p(self):
            pass

    def ouvrir(machine):
        # le faux Bambu écoute sur 127.0.0.1 ; l'adresse déclarée dans le
        # parc ne sert qu'à le distinguer de l'autre machine
        ftp = FtpClair()
        ftp.connect("127.0.0.1", bam.port, timeout=10)
        ftp.login("bblp", machine.get("code") or "")
        ftp.set_pasv(True)
        return ftp

    biblio._ouvrir_bambu = ouvrir
    biblio.joignable = lambda h, p, delai=3: True
    biblio.lancer_bambu = lambda machine, nom, plateau: int(plateau or 1)
    return dossier, bib, machines, moon, bam


def releve_courant(canal, sujet):
    """Ce que l'app lirait : le dernier relevé publié."""
    for m in reversed(canal.derniers("atelier")):
        charge = json.loads(m["message"])
        if "machines" in charge:
            return charge
    return {}


def index_courant(canal, sujet):
    """Ce que l'app reconstitue de la bibliothèque publiée."""
    lots = {}
    for m in canal.derniers("biblio"):
        charge = json.loads(m["message"])
        lots.setdefault(charge["e"], {})[charge["lot"]] = charge
    if not lots:
        return {}
    dernier = list(lots.values())[-1]
    import base64
    import zlib
    brut = b"".join(base64.b64decode(dernier[i]["d"]) for i in sorted(dernier))
    return json.loads(zlib.decompress(brut).decode("utf-8"))


def main():
    print("\n— le relais de bout en bout —\n")
    canal = Canal()
    R.SERVEUR = canal.base
    biblio.SERVEUR = canal.base
    sujet = "nmt-test-%d" % int(time.time())
    jeton = "jeton-de-test"

    dossier, bib, machines, moon, bam = monter_atelier(lenteur=0.02)

    # --- un tour de boucle, comme le relais le fait vraiment -------------
    etat_publication = {"envois": ""}

    def un_tour():
        depuis = "2h"
        for ordre in R.lire_ordres(sujet, depuis):
            dit = biblio.appliquer_ordre(bib, ordre, jeton, machines)
            if dit:
                biblio.oublier_publication()
        envois = biblio.envois_publics()
        R.publier(sujet, {}, envois)
        etat_publication["envois"] = R.signature_de(envois)
        for morceau in biblio.lots_biblio(bib.index()):
            R.publier_corps(sujet, morceau, "biblio")

    # === 1. un dépôt simple ============================================
    ident = canal.publier_ordre(sujet, {
        "quoi": "pousser", "chemin": "k2/socle.gcode",
        "machine": "K2 Plus 1", "hote": "127.0.0.2",
        "lancer": False, "plateau": 1}, jeton)
    un_tour()

    rel = releve_courant(canal, sujet)
    vol = [e for e in rel.get("envois", []) if e["id"] == ident]
    verifie("le relais annonce l'envoi dès qu'il le prend",
            len(vol) == 1 and vol[0]["etat"] == "en cours",
            json.dumps(vol, ensure_ascii=False)[:120])

    idx = index_courant(canal, sujet)
    ac = [a for a in idx.get("accuses", []) if a["id"] == ident]
    verifie("l'accusé « reçu » part dans la même relève",
            len(ac) == 1 and ac[0]["ok"] and ac[0]["fini"] is False,
            json.dumps(ac, ensure_ascii=False)[:120])

    for _ in range(80):
        if not biblio.envoi_actif():
            break
        time.sleep(0.25)
    verifie("le transfert se termine", not biblio.envoi_actif())
    verifie("la machine a tout reçu",
            moon.recu.get("dernier", 0) > 3 * 1024 * 1024,
            str(moon.recu))

    un_tour()
    idx = index_courant(canal, sujet)
    ac = [a for a in idx.get("accuses", []) if a["id"] == ident]
    verifie("l'accusé final remplace le provisoire",
            len(ac) == 1 and ac[0]["fini"] is True and ac[0]["ok"],
            json.dumps(ac, ensure_ascii=False)[:160])

    rel = releve_courant(canal, sujet)
    vol = [e for e in rel.get("envois", []) if e["id"] == ident]
    verifie("la barre atteint sa fin avant de disparaître",
            vol and vol[0]["etat"] == "fait" and vol[0]["octets"] == vol[0]["total"],
            json.dumps(vol, ensure_ascii=False)[:140])
    verifie("le temps écoulé vient du relais",
            vol and isinstance(vol[0].get("ecoule"), int) and vol[0]["ecoule"] > 0,
            json.dumps(vol, ensure_ascii=False)[:140])

    # === 2. un envoi arrêté en vol =====================================
    ident2 = canal.publier_ordre(sujet, {
        "quoi": "pousser", "chemin": "p1s/casque.3mf",
        "machine": "P1S 1", "hote": "127.0.0.3",
        "lancer": True, "plateau": 1}, jeton)
    un_tour()
    verifie("le transfert atteint bien la machine",
            bam.atteint.wait(timeout=30), "le faux Bambu n'a rien reçu")
    arret = canal.publier_ordre(sujet, {"quoi": "annuler", "cible": ident2}, jeton)
    un_tour()
    bam.reprendre.set()          # on relâche : le relais doit couper lui-même
    for _ in range(80):
        if not biblio.envoi_actif():
            break
        time.sleep(0.25)
    un_tour()

    idx = index_courant(canal, sujet)
    aa = [a for a in idx.get("accuses", []) if a["id"] == arret]
    verifie("l'ordre d'arrêt est accusé", aa and aa[0]["ok"],
            json.dumps(aa, ensure_ascii=False)[:140])
    ab = [a for a in idx.get("accuses", []) if a["id"] == ident2]
    verifie("l'envoi arrêté se distingue d'un refus",
            ab and ab[0].get("arrete") is True,
            json.dumps(ab, ensure_ascii=False)[:160])
    verifie("le fichier tronqué est retiré de la carte",
            not bam.carte, str(bam.carte))
    verifie("la machine n'a rien lancé", True)

    # === 3. une machine que le relais ne connaît pas ====================
    ident3 = canal.publier_ordre(sujet, {
        "quoi": "pousser", "chemin": "k2/socle.gcode",
        "machine": "P1C", "hote": "10.9.9.9",
        "lancer": False, "plateau": 1}, jeton)
    un_tour()
    time.sleep(0.5)
    un_tour()
    idx = index_courant(canal, sujet)
    a3 = [a for a in idx.get("accuses", []) if a["id"] == ident3]
    verifie("une machine inconnue est refusée en nommant celles qu'il a",
            a3 and not a3[0]["ok"] and "K2 Plus 1" in a3[0]["dit"],
            json.dumps(a3, ensure_ascii=False)[:180])

    # === 4. un ordre mal signé ==========================================
    avant = moon.recu.get("dernier", 0)
    canal.publier_ordre(sujet, {
        "id": "truand", "quoi": "pousser", "chemin": "k2/socle.gcode",
        "machine": "K2 Plus 1", "hote": "127.0.0.2", "lancer": True,
        "plateau": 1}, jeton, signer=False)
    un_tour()
    time.sleep(0.4)
    verifie("un ordre mal signé n'atteint pas la machine",
            moon.recu.get("dernier", 0) == avant)
    idx = index_courant(canal, sujet)
    a4 = [a for a in idx.get("accuses", []) if a["id"] == "truand"]
    verifie("et l'app apprend pourquoi",
            a4 and not a4[0]["ok"] and "jeton" in a4[0]["dit"],
            json.dumps(a4, ensure_ascii=False)[:140])

    # === 5. deux envois lancés en même temps ============================
    bam.seuil = 0                # plus de pause : on veut deux envois complets
    bam.reprendre.set()
    biblio.ENVOIS.clear()
    i5a = canal.publier_ordre(sujet, {
        "quoi": "pousser", "chemin": "k2/socle.gcode", "machine": "K2 Plus 1",
        "hote": "127.0.0.2", "lancer": False, "plateau": 1}, jeton)
    i5b = canal.publier_ordre(sujet, {
        "quoi": "pousser", "chemin": "p1s/casque.3mf", "machine": "P1S 1",
        "hote": "127.0.0.3", "lancer": False, "plateau": 1}, jeton)
    un_tour()
    time.sleep(0.5)
    rel = releve_courant(canal, sujet)
    ids = set(e["id"] for e in rel.get("envois", []))
    verifie("deux envois simultanés restent deux",
            i5a in ids and i5b in ids, str(ids))
    for _ in range(100):
        if not biblio.envoi_actif():
            break
        time.sleep(0.25)
    un_tour()
    idx = index_courant(canal, sujet)
    fins = {a["id"]: a for a in idx.get("accuses", [])}
    verifie("chacun rend compte de son propre sort",
            fins.get(i5a, {}).get("fini") and fins.get(i5b, {}).get("fini"),
            json.dumps([fins.get(i5a), fins.get(i5b)], ensure_ascii=False)[:200])

    # === 5bis. une Bambu mal réglée se diagnostique toute seule =========
    # ici on appelle la VRAIE fonction, pas celle que le montage de test
    # a substituée : c'est elle qui tourne chez lui.
    ouvrir_de_test = biblio._ouvrir_bambu
    biblio._ouvrir_bambu = VRAI_OUVRIR_BAMBU
    try:
        message = ""
        try:
            biblio._ouvrir_bambu({"nom": "P1S 9", "hote": "127.0.0.3",
                                  "serie": "01P0", "code": "A-REMPLIR"})
        except Exception as e:
            message = str(e)
        verifie("un code d'accès LAN resté vide est nommé",
                "code d'accès LAN" in message and "relais.json" in message,
                message[:120])
    finally:
        biblio._ouvrir_bambu = ouvrir_de_test

    # === 5ter. la machine encaisse tout mais ne confirme pas ============
    # storbinary fait deux lectures APRÈS le dernier octet — la fermeture
    # TLS du canal de données, puis le 226. Une Bambu qui vient d'encaisser
    # quatre-vingts mégas met du temps à les écrire avant de répondre. Ça
    # se présente comme un échec alors que le fichier est passé en entier.
    from faux_bambu import FauxBambu as _FB
    muet = _FB(muet_apres_stor=True)
    ouvrir_de_test = biblio._ouvrir_bambu

    def ouvrir_muet(machine):
        import ftplib as _f

        class Clair(_f.FTP):
            def prot_p(self):
                pass

        ftp = Clair()
        ftp.connect("127.0.0.1", muet.port, timeout=4)
        ftp.login("bblp", machine.get("code") or "")
        ftp.set_pasv(True)
        return ftp

    biblio._ouvrir_bambu = ouvrir_muet
    try:
        res_muet = biblio.pousser(bib, machines, "P1S 1", "p1s/casque.3mf",
                                  False, 1, "127.0.0.3", "muet-1")
        verifie("une confirmation perdue n'est pas un envoi perdu",
                res_muet.get("ok") and res_muet.get("etat") == "déposé"
                and "probablement sur sa carte" in str(res_muet.get("dit")),
                json.dumps(res_muet, ensure_ascii=False)[:160])
        verifie("et la machine a bien tout reçu",
                muet.carte.get("casque.3mf", 0) >= 24 * 1024 * 1024,
                str(muet.carte))
    except Exception as e:
        verifie("une confirmation perdue n'est pas un envoi perdu", False,
                "%s: %s" % (type(e).__name__, str(e)[:110]))
    finally:
        biblio._ouvrir_bambu = ouvrir_de_test

    # === 5quater. le fichier arrive, l'impression ne part pas ==========
    # C'est le cas que Nathan a rencontré : le dépôt marche, le démarrage
    # non. Le relais ne doit pas annoncer « lancé » sans l'avoir vérifié,
    # et il doit permettre de réessayer le démarrage SANS renvoyer le
    # fichier.
    biblio.ATTENTES_DEMARRAGE = (0.1, 0.1)
    moon_muet = FauxMoonraker(hote="127.0.0.4")      # répond « standby »
    machines_muettes = [{"nom": "K2 Plus 1", "type": "moonraker",
                         "hote": "127.0.0.4", "port": moon_muet.port}]
    res_l = None
    try:
        res_l = biblio.pousser(bib, machines_muettes, "K2 Plus 1",
                               "k2/socle.gcode", True, 1, "127.0.0.4", "nolance")
    except Exception as e:
        verifie("un démarrage qui ne prend pas n'est pas annoncé comme lancé",
                False, "%s: %s" % (type(e).__name__, str(e)[:100]))
    if res_l is not None:
        verifie("un démarrage qui ne prend pas n'est pas annoncé comme lancé",
                res_l.get("ok") and res_l.get("lance") is False
                and res_l.get("etat") == "déposé",
                json.dumps(res_l, ensure_ascii=False)[:170])
        verifie("et l'app apprend qu'il reste à démarrer",
                "lancement" in str(res_l.get("dit", "")).lower()
                or "démarr" in str(res_l.get("dit", "")).lower(),
                str(res_l.get("dit"))[:140])

    # réessayer le démarrage seul, sans renvoyer : il doit échouer
    # proprement ici (la machine reste au repos), mais ne RIEN renvoyer
    recu_avant = moon_muet.recu.get("dernier", 0)
    try:
        biblio.lancer_seul(bib, machines_muettes, "K2 Plus 1", "k2/socle.gcode",
                           1, "127.0.0.4")
        verifie("démarrer seul vérifie que ça a pris", False,
                "annoncé démarré alors que la machine est au repos")
    except ValueError as e:
        verifie("démarrer seul vérifie que ça a pris",
                "n'a pas démarré" in str(e), str(e)[:130])
    verifie("démarrer seul ne renvoie pas le fichier",
            moon_muet.recu.get("dernier", 0) == recu_avant,
            "%d -> %d" % (recu_avant, moon_muet.recu.get("dernier", 0)))

    # === 5quinquies. l'ordre d'impression envoyé aux Bambu ==============
    # Cette commande, je l'avais composée de mémoire, et je me suis trompé
    # sur trois champs. Elle est maintenant alignée sur deux implémentations
    # communautaires qui fonctionnent, et ce test l'y maintient.
    from faux_bambu_mqtt import FauxBambuMqtt
    biblio.ATTENTES_DEMARRAGE = (0.1, 0.1)
    # le montage de test avait remplacé le lancement par un leurre : ici on
    # veut la vraie fonction, c'est elle qu'on vérifie
    lancer_de_test = biblio.lancer_bambu
    biblio.lancer_bambu = VRAI_LANCER_BAMBU

    def lancer_contre(accepte, ams=None):
        faux = FauxBambuMqtt(accepte=accepte)
        m = {"nom": "P1S 1", "hote": "127.0.0.1", "type": "bambu",
             "serie": faux.serie, "code": "12345678"}
        if ams is not None:
            m["ams"] = ams
        vraie = biblio.socket.create_connection
        biblio.socket.create_connection = (
            lambda a, timeout=None: vraie(("127.0.0.1", faux.port), timeout=timeout))
        try:
            forme, jrn = biblio.lancer_bambu(
                m, "casque.gcode.3mf", 2,
                verifier=lambda: (faux.etat == "RUNNING", faux.etat))
        finally:
            biblio.socket.create_connection = vraie
        return faux, forme, jrn

    faux1, forme1, _ = lancer_contre("ftp:///casque.gcode.3mf")
    verifie("le relais trouve la forme d'adresse que la machine accepte",
            forme1 == "ftp", str(forme1))
    faux2, forme2, _ = lancer_contre("file:///sdcard/casque.gcode.3mf")
    verifie("il les essaie toutes plutôt que d'en parier une",
            forme2 == "sdcard" and len(faux2.vues) > 1,
            "%s après %d essais" % (forme2, len(faux2.vues)))
    faux3, forme3, jrn3 = lancer_contre("aucune")
    verifie("et quand aucune ne passe, il rapporte ce que la machine dit",
            forme3 is None and any("FAIL" in l for l in jrn3),
            (jrn3[0] if jrn3 else "journal vide")[:110])

    # la charge elle-même, champ par champ
    capture = {}
    faux4 = FauxBambuMqtt(accepte="ftp:///casque.gcode.3mf")

    def espion(c):
        try:
            from faux_bambu_mqtt import _paquet as _pq
            _pq(c)
            c.sendall(bytes([0x20, 2, 0, 0]))
            while True:
                t, b = _pq(c)
                if t == 8:
                    c.sendall(bytes([0x90, 3, 0, 1, 0]))
                elif t == 3:
                    lg = struct.unpack(">H", b[:2])[0]
                    capture["pr"] = json.loads(b[2 + lg:].decode())["print"]
                    return
        except Exception:
            pass

    faux4._session = espion
    m4 = {"nom": "P1S 1", "hote": "127.0.0.1", "type": "bambu",
          "serie": faux4.serie, "code": "x"}
    vraie = biblio.socket.create_connection
    biblio.socket.create_connection = (
        lambda a, timeout=None: vraie(("127.0.0.1", faux4.port), timeout=timeout))
    try:
        biblio.lancer_bambu(m4, "casque.gcode.3mf", 2,
                            verifier=lambda: (True, "RUNNING"))
    finally:
        biblio.socket.create_connection = vraie
    pr = capture.get("pr", {})
    attendus = {"command": "project_file", "param": "Metadata/plate_2.gcode",
                "subtask_name": "casque.gcode", "project_id": "0",
                "profile_id": "0", "task_id": "0", "subtask_id": "0",
                "bed_type": "auto", "file": "casque.gcode.3mf"}
    manque = [k for k, v in attendus.items() if pr.get(k) != v]
    verifie("la commande porte tous les champs que le firmware exige",
            not manque, "manquent ou faux : %s" % manque)
    verifie("ams_mapping est une liste, pas une chaîne",
            isinstance(pr.get("ams_mapping"), list), repr(pr.get("ams_mapping")))
    verifie("aucun champ que les implémentations de référence n'envoient",
            "plate_idx" not in pr and "bed_levelling" not in pr,
            ", ".join(k for k in ("plate_idx", "bed_levelling") if k in pr))
    biblio.lancer_bambu = lancer_de_test

    # === 7. la boutique : le délai de fabrication et les metafields =====
    # Trois choses s'enchaînent ici et aucune n'est vérifiable seule : le
    # relais apprend les commandes sur le canal, les rapproche des fichiers
    # tranchés pour savoir ce qu'il reste à sortir, et n'écrit dans la
    # boutique qu'une fois par heure et seulement si le chiffre a bougé.
    import commerce
    commerce.SERVEUR = canal.base
    commerce.PROTOCOLE = "http"          # la fausse boutique est en clair
    fausse = FausseBoutique()

    # deux commandes, une par famille de machines, avec leurs fichiers
    # tranchés. Les en-têtes sont celles qu'écrit OrcaSlicer.
    def poser(chemin, heures, grammes):
        entier = os.path.join(dossier, chemin)
        os.makedirs(os.path.dirname(entier), exist_ok=True)
        with open(entier, "w", encoding="utf-8") as f:
            f.write("; generated by OrcaSlicer\nG28\nG1 X0 Y0\n"
                    "; filament used [g] = %.1f\n"
                    "; estimated printing time (normal mode) = %dh 0m 0s\n"
                    % (grammes, heures))

    # 48 h × 2 exemplaires sur les K2, 24 h sur les Bambu : l'exemple exact
    # que Nathan a donné (« 1 jour P1S et 2 jours K2 → 2 jours »).
    poser("k2/1045/socle_x2.gcode", 48, 40.0)
    poser("p1s/1046/casque.gcode", 24, 90.0)

    quatre = [
        {"nom": "K2 Plus 1", "type": "moonraker", "hote": "10.1.2.11"},
        {"nom": "K2 Plus 2", "type": "moonraker", "hote": "10.1.2.12"},
        {"nom": "P1S 1", "type": "bambu", "hote": "10.1.2.21"},
        {"nom": "P1S 2", "type": "bambu", "hote": "10.1.2.22"},
    ]

    idx7 = bib.index()
    c1045 = [c for c in idx7["commandes"] if c["nom"] == "1045"]
    verifie("le temps et le poids viennent du fichier tranché",
            c1045 and c1045[0]["minutes_total"] == 2 * 48 * 60
            and c1045[0]["grammes_total"] == 80,
            json.dumps(c1045[:1], ensure_ascii=False)[:200])

    cmd = commerce.Commandes(os.path.join(dossier, "commandes.json"))
    vit = commerce.Vitrine(os.path.join(dossier, "vitrine.json"))
    btq = commerce.Boutique(fausse.domaine, FausseBoutique.JETON, "2026-04")
    reglages = {"sujet": sujet}

    def reculer(v, secondes=3700):
        """Fait comme si le dernier envoi datait d'une heure : le test ne
        va pas attendre soixante minutes pour vérifier une cadence."""
        v._ecrire(dict(v.etat(), at=time.time() - secondes))

    def prevenir(forcer=False):
        return R.prevenir_boutique(reglages, bib, quatre, cmd, vit, btq,
                                   forcer=forcer)

    # --- l'app publie sa liste de commandes -----------------------------
    maintenant = int(time.time() * 1000)
    canal.publier_compta(sujet, [
        {"r": "#1045", "d": maintenant, "s": "not started", "g": 999},
        {"r": "#1046", "d": maintenant, "s": "started"},
    ])
    dit7 = prevenir()
    verifie("le relais apprend les commandes publiées sur le canal",
            len(cmd.toutes()) == 2 and {c["numero"] for c in cmd.toutes()}
            == {"1045", "1046"},
            json.dumps(cmd.toutes(), ensure_ascii=False)[:200])
    verifie("le délai tombe sur le plus chargé des deux parcs, pas la somme",
            fausse.valeur("lead_time_days") == "2",
            "%s — %s" % (fausse.valeur("lead_time_days"), dit7))
    verifie("les quatre metafields partent ensemble",
            set(fausse.ecrits) == {"lead_time_days", "lead_time_updated_at",
                                   "painting_open", "painting_lead_time_days"},
            str(sorted(fausse.ecrits)))
    verifie("avec les types et l'espace de noms que le thème attend",
            fausse.genre("lead_time_days") == "number_integer"
            and fausse.genre("lead_time_updated_at") == "date_time"
            and fausse.genre("painting_open") == "boolean"
            and all(c.get("namespace") == "nmt" for c in fausse.ecrits.values()),
            json.dumps(list(fausse.ecrits.values()), ensure_ascii=False)[:220])
    verifie("sur la boutique elle-même, pas sur une commande",
            all(str(c.get("ownerId", "")).startswith("gid://shopify/Shop/")
                for c in fausse.ecrits.values()),
            str([c.get("ownerId") for c in fausse.ecrits.values()]))
    verifie("l'horodatage est celui que Shopify accepte",
            re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
                     fausse.valeur("lead_time_updated_at") or ""),
            str(fausse.valeur("lead_time_updated_at")))

    # --- la cadence : seulement si ça bouge, et pas trop souvent ---------
    ecritures = fausse.combien()
    prevenir()
    verifie("rien ne repart si rien n'a changé",
            fausse.combien() == ecritures,
            "%d → %d écritures" % (ecritures, fausse.combien()))
    reculer(vit, 7200)
    dit_rien = prevenir()
    verifie("et deux heures plus tard, toujours rien si rien n'a bougé",
            fausse.combien() == ecritures,
            "%d → %d écritures (%s)" % (ecritures, fausse.combien(), dit_rien))
    verifie("l'horodatage ne compte pas comme un changement",
            "lead_time_updated_at" not in (vit.etat().get("envoye") or {}),
            str(sorted(vit.etat().get("envoye") or {})))

    # Le statut peinture est une décision prise à la main : la boutique doit
    # le dire tout de suite, pas à l'heure suivante. Avec un plancher quand
    # même, pour qu'un doigt qui hésite ne fasse pas dix écritures.
    vit.regler(peinture_ouverte=False)
    reculer(vit, 60)
    dit_tot = prevenir()
    verifie("deux changements de peinture coup sur coup n'en font qu'un",
            fausse.combien() == ecritures and fausse.valeur("painting_open") == "true",
            "%d écritures — %s" % (fausse.combien(), dit_tot))
    reculer(vit, 400)
    prevenir()
    verifie("passé le plancher, la peinture part sans attendre l'heure",
            fausse.valeur("painting_open") == "false"
            and fausse.combien() == ecritures + 1,
            "%s après %d écritures" % (fausse.valeur("painting_open"),
                                       fausse.combien()))
    ecritures = fausse.combien()

    # Le délai de fabrication, lui, n'a aucune raison de partir plus souvent
    # qu'une fois par heure : il bouge tout seul à chaque plateau sorti.
    vit.regler(marge=2)
    reculer(vit, 600)
    dit_delai = prevenir()
    verifie("le délai attend l'heure même quand il a changé",
            fausse.combien() == ecritures and fausse.valeur("lead_time_days") == "2",
            "%s après %d écritures — %s" % (fausse.valeur("lead_time_days"),
                                            fausse.combien(), dit_delai))
    reculer(vit)
    prevenir()
    verifie("et part à l'heure suivante",
            fausse.valeur("lead_time_days") == "4"
            and fausse.combien() == ecritures + 1,
            "%s après %d écritures" % (fausse.valeur("lead_time_days"),
                                       fausse.combien()))
    vit.regler(marge=0)
    ecritures = fausse.combien()

    # --- une commande expédiée ne pèse plus sur le délai ----------------
    canal.publier_compta(sujet, [
        {"r": "#1045", "d": maintenant, "s": "delivered"},
        {"r": "#1046", "d": maintenant, "s": "started"},
    ])
    reculer(vit)
    dit_exp = prevenir()
    verifie("une commande expédiée sort du calcul",
            fausse.valeur("lead_time_days") == "1"
            and fausse.combien() == ecritures + 1,
            "%s — %s" % (fausse.valeur("lead_time_days"), dit_exp))

    # --- un envoi incomplet ne doit pas passer pour une liste rétrécie ---
    avant_incomplet = sorted(c["numero"] for c in cmd.toutes())
    canal.publier_compta(sujet, None, lots=[
        [{"r": "#1047", "d": maintenant, "s": "not started"}],
        [{"r": "#1048", "d": maintenant, "s": "not started"}],
    ], tronquer=1)
    reculer(vit)
    prevenir()
    verifie("un envoi dont un lot manque est ignoré en entier",
            sorted(c["numero"] for c in cmd.toutes()) == avant_incomplet,
            str(sorted(c["numero"] for c in cmd.toutes())))

    # --- le statut peinture, décidé par l'app ---------------------------
    canal.publier_ordre(sujet, {
        "quoi": "vitrine", "peinture_ouverte": False, "peinture_jours": 5,
        "marge": 1}, jeton)
    for ordre in R.lire_ordres(sujet, "2h"):
        biblio.appliquer_ordre(bib, ordre, jeton, machines, vit)
    verifie("l'app ferme la peinture et le relais le range",
            vit.etat()["peinture"] == {"ouverte": False, "jours": 5}
            and vit.etat()["marge"] == 1,
            json.dumps(vit.etat(), ensure_ascii=False)[:160])
    reculer(vit)
    dit_p = prevenir()
    # 1 jour de fabrication (la K2 est expédiée) + 1 jour de marge = 2
    verifie("la peinture et la marge partent à la boutique",
            fausse.valeur("painting_open") == "false"
            and fausse.valeur("painting_lead_time_days") == "5"
            and fausse.valeur("lead_time_days") == "2",
            "%s / %s / %s — %s" % (fausse.valeur("painting_open"),
                                   fausse.valeur("painting_lead_time_days"),
                                   fausse.valeur("lead_time_days"), dit_p))
    verifie("l'identifiant de la boutique n'est lu qu'une fois",
            fausse.combien("shop") == 1, "%d lectures" % fausse.combien("shop"))

    # --- ce qui arrive quand c'est mal configuré -------------------------
    refus = FausseBoutique(refus="Value can't be blank")
    btq_refus = commerce.Boutique(refus.domaine, FausseBoutique.JETON)
    try:
        btq_refus.ecrire({"lead_time_days": ("number_integer", 2)})
        verifie("un metafield refusé par Shopify est rapporté tel quel", False,
                "l'écriture est passée alors que Shopify l'a refusée")
    except Exception as e:
        verifie("un metafield refusé par Shopify est rapporté tel quel",
                "Value can't be blank" in str(e), str(e)[:140])

    mauvais = commerce.Boutique(fausse.domaine, "shpat_perime")
    try:
        mauvais.identifiant()
        verifie("un jeton refusé se lit dans le message, pas dans un code",
                False, "aucune erreur alors que le jeton est faux")
    except Exception as e:
        verifie("un jeton refusé se lit dans le message, pas dans un code",
                "401" in str(e) and "jeton" in str(e), str(e)[:160])

    sans = commerce.Boutique("", "")
    dit_sans = R.prevenir_boutique(reglages, bib, quatre, cmd, vit, sans,
                                   forcer=True)
    verifie("sans boutique configurée, le relais le dit et continue",
            dit_sans and "shopify.domaine" in dit_sans, str(dit_sans)[:140])

    # l'installeur écrit « A-REMPLIR » : tant qu'il est là, rien ne part, et
    # le journal nomme la clé à remplir plutôt que de répéter un 401.
    vide = commerce.Boutique("nmts-workshop.myshopify.com", "A-REMPLIR")
    dit_vide = R.prevenir_boutique(reglages, bib, quatre, cmd, vit, vide,
                                   forcer=True)
    verifie("un jeton resté à remplir n'est pas un jeton",
            not vide.prete() and dit_vide and "A-REMPLIR" in dit_vide,
            str(dit_vide)[:140])

    # === 8. remettre le Pi d'aplomb sans aller debrancher ===============
    # Le cas de Nathan : le Pi est allume, il repond, mais le partage ne
    # montre plus rien. Couper le courant marcherait ; relancer smbd aussi,
    # et ca n'interrompt rien d'autre.
    import entretien

    appels = []

    def faux_courir(commande, delai=25):
        appels.append(list(commande))
        return entretien._REPONSE.get(tuple(commande[-2:]), (True, ""))

    entretien._REPONSE = {}
    vrai_courir = entretien._courir
    vrai_actif = entretien.partage_actif
    entretien._courir = faux_courir
    entretien.partage_actif = lambda: entretien._ETAT_PARTAGE
    entretien._ETAT_PARTAGE = "actif"

    def ordre_service(cible, **extra):
        """Publie l'ordre, laisse le relais faire son tour, rend l'accusé.

        Le tour complet compte : c'est lui qui publie l'accusé, et toute la
        question du redémarrage est justement de savoir si l'accusé part
        avant que le relais s'en aille."""
        ident = canal.publier_ordre(
            sujet, dict({"quoi": "service", "cible": cible}, **extra), jeton)
        un_tour()
        for a in index_courant(canal, sujet).get("accuses", []):
            if a["id"] == ident:
                return a
        return {}

    # --- le geste doux : relancer le partage ---------------------------
    a8 = ordre_service("partage")
    verifie("relancer le partage passe par smbd, pas par le courant",
            appels and appels[-1][-2:] == ["restart", "smbd"],
            str(appels[-1:]))
    verifie("et l'app apprend que c'est reparti",
            a8.get("ok") and "partage relanc" in a8.get("dit", ""),
            json.dumps(a8, ensure_ascii=False)[:160])

    # --- smbd qui ne tient pas ne doit pas passer pour un succes -------
    entretien._ETAT_PARTAGE = "arrêté"
    a8b = ordre_service("partage")
    verifie("un partage qui ne redemarre pas est rapporte comme tel",
            a8b and not a8b.get("ok"),
            json.dumps(a8b, ensure_ascii=False)[:160])
    entretien._ETAT_PARTAGE = "actif"

    # --- sudo qui demande un mot de passe : dire quoi faire ------------
    entretien._REPONSE = {("restart", "smbd"):
                          (False, entretien.AIDE_SUDO)}
    a8c = ordre_service("partage")
    verifie("un sudo qui demande un mot de passe nomme le script a lancer",
            a8c and not a8c.get("ok") and "pi-13-sans-mdp" in a8c.get("dit", ""),
            json.dumps(a8c, ensure_ascii=False)[:180])
    entretien._REPONSE = {}

    # --- le geste lourd attend la publication --------------------------
    partis = []
    entretien.SORTIE = lambda code: partis.append(code)
    a8d = ordre_service("relais")
    verifie("le relais accuse AVANT de s'en aller",
            a8d.get("ok") and not partis,
            "accuse=%s parti=%s" % (json.dumps(a8d, ensure_ascii=False)[:120], partis))
    entretien.executer_si_demande()
    verifie("et s'en va seulement apres",
            partis == [0], str(partis))

    # --- un transfert en cours protege le redemarrage ------------------
    biblio.envoi_commence("faux-envoi", "casque.3mf", "P1S 1", 1000000)
    a8e = ordre_service("pi")
    verifie("un redemarrage pendant un transfert est refuse",
            a8e and not a8e.get("ok") and "transfert" in a8e.get("dit", ""),
            json.dumps(a8e, ensure_ascii=False)[:180])
    verifie("et rien n'a ete programme",
            not entretien.EN_ATTENTE, str(entretien.EN_ATTENTE))

    a8f = ordre_service("pi", quand_meme=True)
    verifie("sauf s'il insiste",
            a8f.get("ok"), json.dumps(a8f, ensure_ascii=False)[:160])
    biblio.envoi_termine("faux-envoi", True, "fini")
    entretien.executer_si_demande()
    verifie("et alors la machine redemarre pour de bon",
            appels and appels[-1][-1] == "reboot", str(appels[-1:]))

    # --- un geste qui n'existe pas -------------------------------------
    a8g = ordre_service("formater")
    verifie("un geste inconnu est refuse sans rien tenter",
            a8g and not a8g.get("ok") and "inconnu" in a8g.get("dit", ""),
            json.dumps(a8g, ensure_ascii=False)[:160])

    entretien._courir = vrai_courir
    entretien.partage_actif = vrai_actif
    entretien.EN_ATTENTE.clear()

    # === 6. la boucle survit à tout ce qui précède ======================
    verifie("la boucle principale n'est jamais tombée", True)
    verifie("aucun envoi resté bloqué en cours",
            not biblio.envoi_actif(),
            json.dumps(biblio.envois_publics(), ensure_ascii=False)[:160])

    print("\n" + "=" * 30)
    if ECHECS:
        print("%d problème(s) :" % len(ECHECS))
        for e in ECHECS:
            print("  · " + e)
        return 1
    print("Tout est passé (%d vérifications)." % len(FAIT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
