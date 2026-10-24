#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Récupérer la clé Meross et la poser dans relais.json.

Les multiprises n'acceptent un ordre local que s'il est signé avec la clé
du compte Meross. Cette clé ne s'affiche nulle part dans l'application du
fabricant : on l'obtient en s'identifiant une fois auprès de leur service,
et c'est tout ce que ce script fait.

    python3 /opt/relais-atelier/meross_cle.py

Le mot de passe est demandé ici, ne s'affiche pas, n'est écrit nulle part
et ne sert qu'à cet aller-retour. Seule la clé est gardée, dans
relais.json, à côté du reste. Elle ne vaut que sur le réseau local : un
ordre signé avec elle n'est accepté que par une multiprise qu'on peut déjà
joindre.

Rien à installer. La première version passait par une bibliothèque tierce,
qui demandait pip, qui demandait apt, qui demandait un miroir à jour — et
le Pi s'est arrêté à la troisième marche. L'échange tient en trente
lignes : un POST signé, une réponse JSON. Autant le faire ici, comme le
relais parle déjà tout seul à Moonraker, au MQTT des Bambu et à Shopify.
"""

import base64
import getpass
import hashlib
import json
import os
import platform
import random
import string
import sys
import time
import urllib.error
import urllib.request
import uuid

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(ICI, "relais.json")

# Le secret de l'application Meross. Il n'ouvre rien tout seul : il ne fait
# que signer la requête, comme le ferait leur application téléphone.
SECRET = "23x17ahWarFH6w29"
CHEMIN_LOGIN = "/v1/Auth/signIn"
CHEMIN_LOGOUT = "/v1/Profile/logout"

REGIONS = {
    "1": ("Europe", "https://iotx-eu.meross.com"),
    "2": ("Amérique", "https://iotx-us.meross.com"),
    "3": ("Asie-Pacifique", "https://iotx-ap.meross.com"),
}

# Ce que le service répond quand ça ne va pas, en français.
REFUS = {
    1001: "mot de passe manquant",
    1002: "ce compte n'existe pas",
    1003: "ce compte est désactivé ou supprimé",
    1004: "adresse ou mot de passe incorrect",
    1005: "adresse invalide",
    1008: "cette adresse n'est pas enregistrée",
    1019: "jeton invalide",
    1022: "jeton refusé",
    1028: "trop de tentatives — attends quelques minutes",
    1031: "l'adresse ne correspond pas au compte",
    1032: "code de validation en deux étapes incorrect",
    1033: ("ce compte demande une validation en deux étapes — désactive-la "
           "le temps de cette seule opération, dans l'app Meross"),
    1035: "compte verrouillé par le service",
    1042: "trop d'appels, le service a mis une limite",
    1200: "jeton expiré",
    1201: "le service n'a pas pu délivrer de jeton",
}

REDIRECTION = 1030


def _nonce(n=16):
    tirage = random.SystemRandom()
    return "".join(tirage.choice(string.ascii_uppercase + string.digits)
                   for _ in range(n))


def _signer(parametres):
    """Le corps signé, tel que l'application du fabricant l'envoie."""
    encode = base64.b64encode(
        json.dumps(parametres).encode("utf-8")).decode("utf-8")
    horodatage = int(round(time.time() * 1000))
    sel = _nonce()
    signature = hashlib.md5(
        ("%s%s%s%s" % (SECRET, horodatage, sel, encode)).encode("utf-8")
    ).hexdigest()
    return {"params": encode, "sign": signature,
            "timestamp": horodatage, "nonce": sel}


def _poster(url, parametres, jeton=None, delai=20):
    corps = json.dumps(_signer(parametres)).encode("utf-8")
    req = urllib.request.Request(url, data=corps, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Basic" if not jeton else "Basic %s" % jeton)
    req.add_header("vender", "meross")
    req.add_header("AppType", "MerossIOT")
    req.add_header("AppVersion", "0.4.9.0")
    req.add_header("AppLanguage", "EN")
    req.add_header("User-Agent", "MerossIOT/0.4.9.0")
    try:
        with urllib.request.urlopen(req, timeout=delai) as rep:
            charge = json.loads(rep.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise ValueError("le service Meross a répondu %d" % e.code)
    except Exception as e:
        raise ValueError("service Meross injoignable : %s" % str(e)[:120])
    return charge


def demander_cle(url, email, mot_de_passe, essais=2):
    """La clé du compte. Suit la redirection de région si le service en
    demande une : un compte créé ailleurs ne répond pas sur l'adresse
    européenne, et le dire vaut mieux que de renvoyer « refusé »."""
    donnees = {
        "email": email,
        "password": hashlib.md5(mot_de_passe.encode("utf-8")).hexdigest(),
        "accountCountryCode": "FR",
        "encryption": 1,
        "agree": 0,
        "mobileInfo": {
            "deviceModel": platform.machine(),
            "mobileOsVersion": platform.release(),
            "mobileOs": platform.system(),
            "uuid": uuid.uuid4().hex,
            "carrier": "",
        },
    }
    charge = _poster(url.rstrip("/") + CHEMIN_LOGIN, donnees)
    code = int(charge.get("apiStatus") or 0)

    if code == REDIRECTION and essais > 0:
        ailleurs = (charge.get("data") or {}).get("domain") or ""
        if ailleurs:
            print("   Le compte est rattaché à une autre région (%s)." % ailleurs)
            return demander_cle(ailleurs, email, mot_de_passe, essais - 1)

    if code:
        raise ValueError(REFUS.get(code, "refus du service (code %d)" % code))

    data = charge.get("data") or {}
    return data.get("key") or "", data.get("token") or "", url


def oublier_jeton(url, jeton):
    """On rend le jeton tout de suite : il ne sert qu'à l'identification,
    et le service limite le nombre de jetons qu'un compte peut avoir."""
    try:
        _poster(url.rstrip("/") + CHEMIN_LOGOUT, {}, jeton=jeton, delai=10)
    except Exception:
        pass


def poser(cle):
    with open(CHEMIN, encoding="utf-8-sig") as f:
        c = json.load(f)
    p = c.get("prises")
    if not isinstance(p, dict):
        p = {"barrettes": []}
    p["cle"] = cle
    c["prises"] = p
    with open(CHEMIN + ".tmp", "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    os.chmod(CHEMIN + ".tmp", 0o600)
    os.replace(CHEMIN + ".tmp", CHEMIN)


def main():
    print("=" * 62)
    print("   La clé Meross, pour piloter les multiprises en local")
    print("=" * 62)
    print()

    if not os.path.exists(CHEMIN):
        print("relais.json introuvable à côté de ce script.")
        return 2

    for k in sorted(REGIONS):
        print("  %s. %s" % (k, REGIONS[k][0]))
    choix = (input("Région du compte [1] : ").strip() or "1")
    if choix not in REGIONS:
        print("Choix inconnu.")
        return 2
    url = REGIONS[choix][1]

    email = input("Adresse du compte Meross : ").strip()
    if not email:
        print("Rien saisi.")
        return 2
    mot_de_passe = getpass.getpass("Mot de passe (il ne s'affiche pas) : ")
    if not mot_de_passe:
        print("Rien saisi.")
        return 2

    print()
    print("Identification…")
    try:
        cle, jeton, ou = demander_cle(url, email, mot_de_passe)
    except ValueError as e:
        print("Refusé : %s" % e)
        return 1
    finally:
        mot_de_passe = None

    if jeton:
        oublier_jeton(ou, jeton)

    if not cle:
        print("Le service n'a pas renvoyé de clé.")
        return 1

    poser(cle)
    print("Clé posée dans relais.json (%d caractères). Elle ne s'affiche pas."
          % len(cle))
    print()
    print("Ensuite :")
    print("   python3 %s/meross_diag.py --chercher" % ICI)
    return 0


if __name__ == "__main__":
    sys.exit(main())
