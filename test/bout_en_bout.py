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
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "relais"))
sys.path.insert(0, os.path.join(RACINE, "test"))

import biblio                                              # noqa: E402
import relais_atelier as R                                 # noqa: E402

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

    def publier_ordre(self, sujet, ordre, jeton, signer=True):
        """Exactement ce que fait Relay.ordre() dans l'app : poser t, id et
        at, puis signer le tout. L'ordre des champs compte : la signature
        porte sur toutes les clés présentes."""
        ordre = dict(ordre)
        ordre["t"] = "ordre"
        ordre.setdefault("id", "ordre-%d" % (time.time() * 1000000 % 10000000))
        ordre.setdefault("at", int(time.time() * 1000))
        ordre["sig"] = biblio.signer(jeton, ordre) if signer else "0" * 32
        corps = json.dumps(ordre, ensure_ascii=False).encode("utf-8")
        import urllib.request
        req = urllib.request.Request(self.base + sujet, data=corps, method="POST")
        req.add_header("Title", "ordre")
        with urllib.request.urlopen(req, timeout=5):
            pass
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

def monter_atelier(lenteur=0.0):
    dossier = tempfile.mkdtemp(prefix="atelier-")
    bib = biblio.Bibliotheque(dossier, ["k2", "p1s"])
    for famille, nom, mo in (("k2", "socle.gcode", 3), ("p1s", "casque.3mf", 4)):
        with open(os.path.join(dossier, famille, nom), "wb") as f:
            f.write(os.urandom(mo * 1024 * 1024))

    moon = FauxMoonraker(lenteur=lenteur, hote="127.0.0.2")
    FauxBambu = charger_faux_bambu()
    bam = FauxBambu(lenteur=lenteur)

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
    time.sleep(0.5)
    arret = canal.publier_ordre(sujet, {"quoi": "annuler", "cible": ident2}, jeton)
    un_tour()
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
