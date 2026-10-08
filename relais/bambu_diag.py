#!/usr/bin/env python3
"""Teste le FTPS de chaque Bambu du relais, etape par etape.

Une panne FTPS tombe toujours sous la meme phrase — « The read operation
timed out » — qu'elle vienne du port, de la poignee de main TLS ou du code
d'acces. Ce script les separe.

    python3 bambu_diag.py            # lit /opt/relais-atelier/relais.json
"""

import ftplib
import json
import os
import socket
import ssl
import sys
import time

REGLAGES = os.environ.get("RELAIS_JSON", "/opt/relais-atelier/relais.json")


class FtpImplicite(ftplib.FTP_TLS):
    """TLS des l'ouverture, avant le premier mot — ce que parlent les Bambu
    sur le port 990. ftplib ne sait faire que l'explicite."""

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


def contexte(assouplir):
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


def port_ouvert(hote, port, delai=4):
    t = time.time()
    try:
        with socket.create_connection((hote, port), timeout=delai):
            return True, time.time() - t
    except Exception as e:
        return False, str(e)


def essayer(machine):
    nom = machine.get("nom") or machine.get("hote")
    hote = machine["hote"]
    code = machine.get("code") or ""
    print("\n=== %s  (%s) ===" % (nom, hote))

    ouvert, info = port_ouvert(hote, 990)
    if not ouvert:
        print("  1. port 990 ............ FERMÉ (%s)" % info)
        print("     -> le mode LAN n'est pas actif sur la machine, ou elle est")
        print("        éteinte, ou le relais ne voit pas son réseau.")
        return
    print("  1. port 990 ............ ouvert (%.0f ms)" % (info * 1000))

    if not code or code == "A-REMPLIR":
        print("  2. code d'accès LAN .... ABSENT de relais.json")
        print("     -> c'est l'« Access Code » affiché sur l'écran de la machine.")
        return
    print("  2. code d'accès LAN .... renseigné (%d caractères)" % len(code))

    for nom_mode, assouplir in (("strict", False), ("assoupli", True)):
        ftp = FtpImplicite(context=contexte(assouplir))
        t = time.time()
        try:
            ftp.connect(hote, 990, timeout=25)
        except Exception as e:
            print("  3. TLS %-9s ...... échec (%s)" % (nom_mode, str(e)[:60]))
            try:
                ftp.close()
            except Exception:
                pass
            continue
        print("  3. TLS %-9s ...... poignée de main ok (%.0f ms)"
              % (nom_mode, (time.time() - t) * 1000))
        try:
            ftp.login("bblp", code)
            ftp.prot_p()
            ftp.set_pasv(True)
        except Exception as e:
            print("  4. identification ...... REFUSÉE (%s)" % str(e)[:70])
            print("     -> le code d'accès LAN ne correspond pas.")
            try:
                ftp.close()
            except Exception:
                pass
            return
        print("  4. identification ...... acceptée")
        try:
            fichiers = []
            ftp.retrlines("NLST", fichiers.append)
            print("  5. carte SD ............ %d fichier(s) à la racine" % len(fichiers))
            for f in fichiers[:6]:
                print("       %s" % f)
            if len(fichiers) > 6:
                print("       … et %d autres" % (len(fichiers) - 6))
        except Exception as e:
            print("  5. carte SD ............ illisible (%s)" % str(e)[:70])
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
        print("  -> cette machine répond correctement en %s." % nom_mode)
        return

    print("     -> aucun des deux modes TLS ne passe. Si le port est ouvert")
    print("        mais que la poignée de main échoue, c'est la version de TLS")
    print("        de la machine que le Pi refuse.")


def main():
    print("OpenSSL du Pi : %s" % ssl.OPENSSL_VERSION)
    try:
        with open(REGLAGES, encoding="utf-8-sig") as f:
            c = json.load(f)
    except Exception as e:
        print("relais.json illisible (%s) : %s" % (REGLAGES, e))
        return 1
    bambus = [m for m in (c.get("machines") or []) if m.get("type") == "bambu"]
    if not bambus:
        print("aucune machine Bambu dans relais.json")
        return 1
    for m in bambus:
        essayer(m)
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
