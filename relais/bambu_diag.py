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
import struct
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


def hote_sortant():
    """L'adresse par laquelle le Pi sort — celle que verra le pare-feu."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        a = s.getsockname()[0]
        s.close()
        return a
    except Exception:
        return "le Pi"


def port_ouvert(hote, port, delai=4):
    t = time.time()
    try:
        with socket.create_connection((hote, port), timeout=delai):
            return True, time.time() - t
    except Exception as e:
        return False, str(e)


def _lg(n):
    b = b""
    while True:
        d, n = n % 128, n // 128
        b += bytes([d | 128 if n else d])
        if not n:
            return b


def _txt(s):
    s = s.encode()
    return struct.pack(">H", len(s)) + s


def _recv(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError("connexion fermée")
        b += c
    return b


def _paquet(s):
    entete = _recv(s, 1)[0]
    mult, val = 1, 0
    while True:
        x = _recv(s, 1)[0]
        val += (x & 127) * mult
        mult *= 128
        if not x & 128:
            break
    return entete >> 4, _recv(s, val)


def mqtt(machine, ftp_ok=False):
    """Le lancement d'une impression ne passe PAS par le FTPS : il passe par
    MQTT, sur le port 8883. Un pare-feu peut très bien laisser l'un et
    bloquer l'autre — le fichier arrive alors sur la carte et l'impression
    ne part jamais."""
    hote = machine["hote"]
    code = machine.get("code") or ""
    serie = machine.get("serie") or ""

    ouvert, info = port_ouvert(hote, 8883, delai=6)
    if not ouvert:
        print("  8. port 8883 (MQTT) ..... FERMÉ (%s)" % info)
        print("")
        if ftp_ok:
            print("     -> C'EST LUI. Le fichier arrive par le 990, mais l'ordre")
            print("        d'imprimer passe par le 8883, et il ne passe pas.")
        else:
            print("     -> ni le 990 ni le 8883 : la machine est éteinte, ou")
            print("        le relais ne voit pas son réseau du tout.")
        print("        À demander : du %s vers %s, autoriser le TCP sortant"
              % (hote_sortant(), hote))
        print("        sur le port 8883.")
        return
    print("  8. port 8883 (MQTT) ..... ouvert (%.0f ms)" % (info * 1000))

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        s = ctx.wrap_socket(socket.create_connection((hote, 8883), timeout=10))
    except Exception as e:
        print("  9. TLS du MQTT .......... échec (%s)" % str(e)[:60])
        return
    try:
        tete = _txt("MQTT") + bytes([4, 0xC2]) + struct.pack(">H", 30)
        corps = (_txt("diag-%d" % int(time.time())) + _txt("bblp") + _txt(code))
        s.sendall(bytes([0x10]) + _lg(len(tete + corps)) + tete + corps)
        t, b = _paquet(s)
        if t != 2 or b[1] != 0:
            print("  9. identification MQTT .. REFUSÉE (code %s)" % (b[1] if len(b) > 1 else "?"))
            print("     -> le code d'accès LAN ne convient pas pour MQTT.")
            return
        print("  9. identification MQTT .. acceptée")

        if not serie:
            print(" 10. numéro de série ...... ABSENT de relais.json")
            print("     -> sans lui le relais ne peut adresser aucun ordre.")
            return
        sujet = "device/%s/report" % serie
        pq = _txt(sujet) + bytes([0])
        s.sendall(bytes([0x82]) + _lg(2 + len(pq)) + struct.pack(">H", 1) + pq)
        t, b = _paquet(s)
        print(" 10. abonnement au report . %s (série %s)"
              % ("accepté" if t == 9 else "refusé", serie))

        s.settimeout(12)
        vus = 0
        t0 = time.time()
        while time.time() - t0 < 10:
            try:
                t, b = _paquet(s)
            except Exception:
                break
            if t == 3:
                vus += 1
        if vus:
            print(" 11. la machine parle ..... %d message(s) reçus en 10 s" % vus)
            print("     -> le chemin du lancement est libre de bout en bout.")
        else:
            print(" 11. la machine parle ..... RIEN en 10 s")
            print("     -> elle accepte la connexion mais n'envoie aucun")
            print("        rapport : numéro de série faux, ou pare-feu qui")
            print("        coupe le retour.")
    except Exception as e:
        print("  9. MQTT ................. %s" % str(e)[:70])
    finally:
        try:
            s.close()
        except Exception:
            pass


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

        # L'étape qui compte. FTP ouvre une SECONDE connexion, sur un port
        # haut que la machine annonce dans sa réponse PASV. Tant qu'on n'a
        # pas essayé, on n'a testé que le port 990.
        port_donnees = None
        try:
            hote_pasv, port_donnees = ftp.makepasv()
            print("  5. canal de données .... la machine annonce le port %d" % port_donnees)
        except Exception as e:
            print("  5. canal de données .... PASV refusé (%s)" % str(e)[:60])
            try:
                ftp.close()
            except Exception:
                pass
            return

        joint, info = port_ouvert(hote_pasv, port_donnees, delai=8)
        if not joint:
            print("  6. ce port est .......... INJOIGNABLE depuis le Pi (%s)" % info)
            print("")
            print("     -> C'EST LE PARE-FEU, presque à coup sûr.")
            print("        Le port 990 passe, le canal de données non.")
            print("        En FTPS le canal de contrôle est chiffré : le")
            print("        pare-feu ne peut PAS lire la réponse PASV, donc son")
            print("        assistant FTP ne sait pas quel port ouvrir. Il faut")
            print("        l'autoriser à la main.")
            print("        À demander : du %s vers %s, autoriser le TCP sortant"
                  % (hote_sortant(), hote_pasv))
            print("        sur les ports hauts (1024-65535), ou au moins la")
            print("        plage de données de la machine.")
            try:
                ftp.close()
            except Exception:
                pass
            return
        print("  6. ce port est .......... joignable (%.0f ms)" % (info * 1000))

        complet = False
        try:
            fichiers = []
            t = time.time()
            ftp.retrlines("NLST", fichiers.append)
            complet = True
            print("  7. carte SD ............ %d fichier(s) à la racine (%.0f ms)"
                  % (len(fichiers), (time.time() - t) * 1000))
            for f in fichiers[:6]:
                print("       %s" % f)
            if len(fichiers) > 6:
                print("       … et %d autres" % (len(fichiers) - 6))
        except Exception as e:
            print("  7. carte SD ............ illisible (%s)" % str(e)[:70])
            print("     -> le port répond mais le transfert ne passe pas :")
            print("        pare-feu qui coupe après coup, ou TLS du canal de")
            print("        données refusé par la machine.")
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass
        if complet:
            print("  -> cette machine répond correctement en %s : le relais "
                  "peut lui envoyer un fichier." % nom_mode)
        else:
            print("  -> la connexion s'établit mais aucune donnée ne passe.")
        return complet

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
        ftp_ok = bool(essayer(m))
        # le lancement est un chemin à part : on le teste même si le FTPS
        # a échoué, parce que c'est lui qui bloque quand le fichier arrive
        # mais que l'impression ne part pas
        try:
            mqtt(m, ftp_ok)
        except Exception as e:
            print("  8. MQTT ................. %s" % str(e)[:70])
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
