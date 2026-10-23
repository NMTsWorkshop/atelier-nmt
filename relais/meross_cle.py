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
"""

import asyncio
import getpass
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
CHEMIN = os.path.join(ICI, "relais.json")

REGIONS = {
    "1": ("Europe", "https://iotx-eu.meross.com"),
    "2": ("Amérique", "https://iotx-us.meross.com"),
    "3": ("Asie-Pacifique", "https://iotx-ap.meross.com"),
}

MANQUE = """La bibliothèque meross_iot n'est pas installée sur ce Pi.
Elle ne sert qu'à cette identification, une seule fois :

    pip3 install --break-system-packages meross_iot

puis relance ce script. Tu peux la désinstaller juste après si tu veux :
le relais ne s'en sert pas, il parle aux multiprises tout seul."""


async def demander_cle(url, email, mot_de_passe):
    from meross_iot.http_api import MerossHttpClient
    client = await MerossHttpClient.async_from_user_password(
        api_base_url=url, email=email, password=mot_de_passe)
    try:
        return client.cloud_credentials.key
    finally:
        try:
            await client.async_logout()
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
    try:
        import meross_iot                                   # noqa: F401
    except ImportError:
        print(MANQUE)
        return 2

    if not os.path.exists(CHEMIN):
        print("relais.json introuvable à côté de ce script.")
        return 2

    for k in sorted(REGIONS):
        print("  %s. %s" % (k, REGIONS[k][0]))
    choix = input("Région du compte [1] : ").strip() or "1"
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
        cle = asyncio.run(demander_cle(url, email, mot_de_passe))
    except Exception as e:
        print("Refusé : %s" % str(e)[:200])
        print()
        print("Si c'est une erreur d'identifiants, vérifie l'adresse et le")
        print("mot de passe dans l'application Meross. Si le compte a une")
        print("validation en deux étapes, elle doit être désactivée le temps")
        print("de cette seule opération.")
        return 1
    finally:
        mot_de_passe = None

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
