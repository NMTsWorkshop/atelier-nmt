#!/usr/bin/env python3
"""Le relais demarre-t-il ? main() n'est jamais appele par les autres tests,
et c'est pourtant la seule fonction dont une faute tue le service chez lui."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "relais"))

recu = []

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        recu.append((self.headers.get("Title"), self.rfile.read(n).decode()))
        self._r(b'{"id":"ok"}')
    def do_GET(self):
        self._r(b"\n")
    def _r(self, c):
        self.send_response(200); self.send_header("Content-Length", str(len(c)))
        self.end_headers(); self.wfile.write(c)
    def log_message(self, *a): pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d/" % srv.server_address[1]

dossier = tempfile.mkdtemp(prefix="demarrage-")
import relais_atelier as R
import biblio
R.ICI = dossier
R.SERVEUR = base
biblio.SERVEUR = base
with open(os.path.join(dossier, "relais.json"), "w") as f:
    json.dump({"sujet": "sujet-de-test", "periode": 60, "jeton": "j",
               "biblio": os.path.join(dossier, "gcodes"), "port_api": 0,
               "marge_delai": 2,
               "shopify": {"domaine": "A-REMPLIR.myshopify.com",
                           "jeton": "A-REMPLIR", "version": "2026-04"},
               "machines": [{"nom": "K2 Plus 1", "type": "moonraker",
                             "hote": "127.0.0.9", "port": 1}]}, f)
os.makedirs(os.path.join(dossier, "gcodes", "k2", "1045"), exist_ok=True)
with open(os.path.join(dossier, "gcodes", "k2", "1045", "socle.gcode"), "w") as f:
    f.write("; estimated printing time (normal mode) = 4h 0m 0s\n"
            "; filament used [g] = 20.0\n")

# « --une-fois » imprime l'état complet des machines : utile à la main, du
# bruit dans un journal d'intégration. On le garde pour le cas d'échec.
import io as _io
sys.argv = ["relais_atelier.py", "--une-fois"]
_vu = _io.StringIO()
_vrai = sys.stdout
sys.stdout = _vu
try:
    R.main()
finally:
    sys.stdout = _vrai

def rate(quoi):
    print(_vu.getvalue()[-2000:], file=sys.stderr)
    raise AssertionError(quoi)


titres = [t for t, _ in recu]
if "atelier" not in titres: rate("aucun relevé publié : %s" % titres)
if "biblio" not in titres: rate("bibliothèque non publiée : %s" % titres)
# le délai doit avoir été calculé même sans jeton Shopify
if R.VITRINE.get("jours") != 2: rate("délai faux ou absent : %s" % R.VITRINE)
rel = [json.loads(c) for t, c in recu if t == "atelier"][-1]
if rel.get("vitrine", {}).get("marge") != 2: rate("la marge n'est pas publiée")
if "A-REMPLIR" not in rel["vitrine"]["boutique"]: rate(str(rel["vitrine"]))
# l'etat du Pi voyage avec la releve : c'est ce qui permet a l'app de dire
# « le partage est arrete » au lieu de laisser deviner
if "pi" not in rel: rate("l'etat du Pi n'est pas publie : %s" % sorted(rel))
if "partage" not in rel["pi"]: rate(str(rel["pi"]))
print("démarrage : ok — relevé, bibliothèque et vitrine publiés "
      "(délai %d j, marge %d j)" % (R.VITRINE["jours"], R.VITRINE["marge"]))
