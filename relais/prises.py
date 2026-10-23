# -*- coding: utf-8 -*-
"""Les multiprises connectées, pilotées sur le réseau local.

Les Meross passent normalement par leur nuage. Elles acceptent aussi des
ordres en direct, sur le réseau : un POST sur http://<ip>/config, un petit
entête signé, et c'est tout. Rien ne sort de la maison, et une panne
d'Internet ne prive pas l'atelier de ses interrupteurs.

La signature est un MD5 de (identifiant du message + clé + horodatage).
La clé est celle du compte Meross ; elle vit dans relais.json sur le Pi,
comme le jeton Shopify, et ne sert qu'ici.

    POST /config
    {"header": {"messageId": …, "method": "SET",
                "namespace": "Appliance.Control.ToggleX",
                "payloadVersion": 1, "timestamp": …, "sign": …},
     "payload": {"togglex": {"channel": 2, "onoff": 1}}}

Une chose à ne jamais perdre de vue : le Pi est lui-même branché sur une
de ces prises, et le switch du réseau sur une autre. Couper l'une ou
l'autre, c'est se couper le bras qui tient l'interrupteur — plus personne
ne peut rallumer. Ces deux-là sont donc verrouillées, et le verrou est
dans le code, pas dans la bonne volonté de l'utilisateur.
"""

import hashlib
import json
import random
import socket
import time
import urllib.error
import urllib.request

DELAI = 6

# Ce qu'on refuse de couper, quoi qu'on nous demande. Le relais et le
# réseau qui le porte ne se coupent pas eux-mêmes.
VERROUS = ("pi", "relais", "switch", "reseau", "réseau")


def _signer(identifiant, cle, horodatage):
    brut = "%s%s%s" % (identifiant, cle or "", horodatage)
    return hashlib.md5(brut.encode("utf-8")).hexdigest()


def _appel(hote, espace, charge, cle, methode="SET", delai=DELAI):
    """Un aller-retour avec la multiprise. Renvoie son payload."""
    identifiant = "%032x" % random.getrandbits(128)
    horodatage = int(time.time())
    corps = json.dumps({
        "header": {
            "messageId": identifiant,
            "method": methode,
            "namespace": espace,
            "payloadVersion": 1,
            "timestamp": horodatage,
            "sign": _signer(identifiant, cle, horodatage),
            "from": "",
        },
        "payload": charge or {},
    }).encode("utf-8")

    req = urllib.request.Request("http://%s/config" % hote, data=corps,
                                 method="POST")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    try:
        with urllib.request.urlopen(req, timeout=delai) as rep:
            lu = json.loads(rep.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise ValueError("la multiprise a répondu %d" % e.code)
    except socket.timeout:
        raise ValueError("pas de réponse de %s — éteinte, ou sur un autre "
                         "réseau que le Pi" % hote)
    except Exception as e:
        raise ValueError("%s injoignable : %s" % (hote, str(e)[:90]))

    entete = lu.get("header") or {}
    if entete.get("method") == "ERROR":
        code = (lu.get("payload") or {}).get("error") or {}
        if str(code.get("code")) == "5001":
            raise ValueError("clé Meross refusée — celle de relais.json ne "
                             "correspond pas à cette multiprise")
        raise ValueError("refusé par la multiprise : %s"
                         % json.dumps(code, ensure_ascii=False)[:120])
    return lu.get("payload") or {}


# ----------------------------------------------------------------------
# ce que la multiprise sait dire d'elle-même
# ----------------------------------------------------------------------

def decrire(hote, cle):
    """Modèle, numéro de série, et la liste de ses sorties.

    On ne devine pas combien de prises il y a ni comment elles sont
    numérotées : la multiprise le dit."""
    charge = _appel(hote, "Appliance.System.All", {}, cle, methode="GET")
    tout = (charge.get("all") or {})
    systeme = (tout.get("system") or {})
    materiel = systeme.get("hardware") or {}
    logiciel = systeme.get("firmware") or {}
    digest = tout.get("digest") or {}
    sorties = []
    for t in (digest.get("togglex") or []):
        sorties.append({"canal": int(t.get("channel", 0)),
                        "allumee": bool(int(t.get("onoff", 0)))})
    if not sorties and digest.get("toggle"):
        sorties.append({"canal": 0,
                        "allumee": bool(int((digest["toggle"] or {}).get("onoff", 0)))})
    return {
        "hote": hote,
        "modele": materiel.get("type") or "?",
        "serie": materiel.get("macAddress") or "",
        "firmware": logiciel.get("version") or "",
        "sorties": sorties,
    }


def etats(hote, cle):
    """{canal: allumée}. Une lecture, pas une écriture."""
    try:
        charge = _appel(hote, "Appliance.Control.ToggleX", {}, cle, methode="GET")
    except ValueError:
        return {}
    out = {}
    for t in (charge.get("togglex") or []):
        out[int(t.get("channel", 0))] = bool(int(t.get("onoff", 0)))
    return out


def basculer(hote, canal, allumer, cle):
    """Allume ou éteint une sortie. Le canal 0 est la multiprise entière."""
    _appel(hote, "Appliance.Control.ToggleX",
           {"togglex": {"channel": int(canal), "onoff": 1 if allumer else 0}}, cle)
    return True


# ----------------------------------------------------------------------
# le parc de prises, tel que relais.json le décrit
# ----------------------------------------------------------------------

class Parc:
    """Les prises nommées, avec leur verrou.

    relais.json :

        "prises": {
          "cle": "…",
          "barrettes": [
            {"nom": "machines", "hote": "10.1.2.70",
             "sorties": [{"canal": 1, "machine": "K2 Encore Plus"},
                         {"canal": 2, "machine": "K2 Plus 2"}]},
            {"nom": "reseau", "hote": "10.1.2.71",
             "sorties": [{"canal": 1, "role": "switch"},
                         {"canal": 5, "role": "pi"}]}
          ]
        }

    Une sortie porte soit le nom d'une machine, soit un rôle. Un rôle qui
    figure dans VERROUS ne se coupe jamais."""

    def __init__(self, reglages):
        reglages = reglages or {}
        self.cle = reglages.get("cle") or ""
        self.barrettes = []
        for b in (reglages.get("barrettes") or []):
            if not b.get("hote"):
                continue
            self.barrettes.append({
                "nom": b.get("nom") or b.get("hote"),
                "hote": b.get("hote"),
                "sorties": [dict(s) for s in (b.get("sorties") or [])],
            })

    def prete(self):
        return bool(self.barrettes and self.cle
                    and "A-REMPLIR" not in self.cle)

    def pourquoi_pas(self):
        if not self.barrettes:
            return "aucune multiprise décrite dans relais.json (prises.barrettes)"
        if not self.cle or "A-REMPLIR" in self.cle:
            return ("la clé Meross est restée à A-REMPLIR dans relais.json "
                    "(voir relais/README.md)")
        return ""

    def sorties(self):
        """Toutes les sorties, à plat, avec leur barrette."""
        out = []
        for b in self.barrettes:
            for s in b["sorties"]:
                out.append(dict(s, hote=b["hote"], barrette=b["nom"]))
        return out

    def pour_machine(self, nom):
        cible = str(nom or "").strip().lower()
        for s in self.sorties():
            if str(s.get("machine") or "").strip().lower() == cible:
                return s
        return None

    @staticmethod
    def verrouillee(sortie):
        role = str((sortie or {}).get("role") or "").strip().lower()
        return role in VERROUS

    def releve(self):
        """Ce qui est allumé, barrette par barrette. Jamais d'exception :
        une multiprise éteinte ne doit pas faire tomber la relève."""
        out = []
        for b in self.barrettes:
            vus = etats(b["hote"], self.cle) if self.cle else {}
            for s in b["sorties"]:
                canal = int(s.get("canal", 0))
                out.append({
                    "barrette": b["nom"], "hote": b["hote"], "canal": canal,
                    "machine": s.get("machine") or "",
                    "role": s.get("role") or "",
                    "verrouillee": self.verrouillee(s),
                    "allumee": vus.get(canal),
                })
        return out

    def commander(self, sortie, allumer):
        """(ok, ce qu'on en dit). Le verrou est vérifié ici, au plus près
        du geste : c'est le seul endroit par lequel tout passe."""
        if not sortie:
            return False, "prise inconnue"
        quoi = sortie.get("machine") or sortie.get("role") or "cette prise"
        if self.verrouillee(sortie):
            return False, ("%s alimente le relais lui-même — le couper "
                           "d'ici, c'est perdre le moyen de le rallumer. "
                           "Ça se fait à la main, sur place." % quoi)
        if not self.prete():
            return False, self.pourquoi_pas()
        try:
            basculer(sortie["hote"], sortie.get("canal", 0), allumer, self.cle)
        except ValueError as e:
            return False, str(e)
        return True, "%s : %s" % (quoi, "allumée" if allumer else "éteinte")
