# -*- coding: utf-8 -*-
"""Une fausse multiprise Meross, juste assez pour le relais.

Elle vérifie la signature comme la vraie — c'est la moitié de ce qu'on
veut tester : une clé fausse doit être refusée, et refusée d'une manière
qui se lit."""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FausseMeross:
    def __init__(self, cle="cle-de-test", canaux=(1, 2, 3, 4, 5),
                 modele="mss425f", muette=False):
        self.cle = cle
        self.etats = {c: True for c in canaux}
        self.modele = modele
        self.muette = muette
        self.recus = []
        faux = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    msg = json.loads(self.rfile.read(n).decode("utf-8"))
                except ValueError:
                    return self._rendre({"header": {"method": "ERROR"},
                                         "payload": {"error": {"code": 5000}}})
                tete = msg.get("header") or {}
                faux.recus.append(tete.get("namespace"))
                attendu = hashlib.md5(
                    ("%s%s%s" % (tete.get("messageId"), faux.cle,
                                 tete.get("timestamp"))).encode()).hexdigest()
                if tete.get("sign") != attendu:
                    return self._rendre({"header": {"method": "ERROR"},
                                         "payload": {"error": {"code": 5001}}})

                espace = tete.get("namespace")
                if espace == "Appliance.System.All":
                    return self._rendre({"header": {"method": "GETACK"},
                                         "payload": {"all": {
                        "system": {"hardware": {"type": faux.modele,
                                                "macAddress": "48:e1:e9:00:00:01"},
                                   "firmware": {"version": "4.2.3"}},
                        "digest": {"togglex": [
                            {"channel": c, "onoff": 1 if v else 0}
                            for c, v in sorted(faux.etats.items())]}}}})

                if espace == "Appliance.Control.ToggleX":
                    if tete.get("method") == "GET":
                        return self._rendre({"header": {"method": "GETACK"},
                                             "payload": {"togglex": [
                            {"channel": c, "onoff": 1 if v else 0}
                            for c, v in sorted(faux.etats.items())]}})
                    tx = (msg.get("payload") or {}).get("togglex") or {}
                    canal = int(tx.get("channel", 0))
                    etat = bool(int(tx.get("onoff", 0)))
                    if canal == 0:
                        for c in faux.etats:
                            faux.etats[c] = etat
                    else:
                        faux.etats[canal] = etat
                    return self._rendre({"header": {"method": "SETACK"},
                                         "payload": {}})

                return self._rendre({"header": {"method": "ERROR"},
                                     "payload": {"error": {"code": 5002}}})

            def _rendre(self, charge):
                if faux.muette:
                    return                      # on ne repond pas du tout
                corps = json.dumps(charge).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]
        self.hote = "127.0.0.1:%d" % self.port
