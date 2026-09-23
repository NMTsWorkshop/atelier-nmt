#!/usr/bin/env python3
"""Relais de l'atelier NMT — lit les imprimantes du réseau local et publie
leur état sur Internet, pour que l'application y accède de n'importe où.

Tourne sur un petit appareil resté allumé à l'atelier (Raspberry Pi).
Il n'ouvre aucun port : seules des connexions sortantes en HTTPS partent
vers ntfy.sh. Rien n'est jamais envoyé aux imprimantes, c'est de la
lecture seule.

Réglages dans relais.json, à côté de ce fichier :

{
  "sujet": "nmt-atelier-xxxxxxxx",
  "periode": 60,
  "machines": [
    {"nom": "K2 Plus", "type": "moonraker", "hote": "10.1.3.3"},
    {"nom": "Bambu 1", "type": "bambu", "hote": "10.1.3.11",
     "serie": "01P00C462500170", "code": "xxxxxxxx"}
  ]
}
"""

import json
import os
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
SERVEUR = "https://ntfy.sh/"


# --------------------------------------------------------------------------
# Creality / Klipper : Moonraker en HTTP sur le port 7125
# --------------------------------------------------------------------------

def http_json(url, delai=8):
    with urllib.request.urlopen(url, timeout=delai) as r:
        return json.loads(r.read().decode("utf-8"))


MATIERES_CREALITY = {
    "02001": "PLA-CF", "00006": "PLA-CF",
    "03001": "ABS", "07001": "ABS", "00004": "ABS",
    "06001": "PETG", "06002": "PETG", "00003": "PETG",
    "06003": "PETG-CF", "00014": "PETG-CF",
    "07002": "PC", "00021": "PC",
    "10001": "TPU", "16001": "TPU", "00005": "TPU", "00026": "TPU",
    "11001": "PA", "00008": "PA", "00023": "PA",
    "12002": "PA-CF", "12003": "PA-CF", "12004": "PA-CF", "12005": "PA-CF",
    "00009": "PA-CF", "00015": "PA-CF", "00016": "PA-CF", "00022": "PA-CF",
    "00025": "PA-CF",
    "19001": "ASA", "00007": "ASA", "00033": "ASA-CF",
    "00011": "PVA", "00012": "HIPS", "00020": "PET", "00032": "PCTG",
}
PLA_CREALITY = {
    "01001", "01002", "01004", "01601", "04001", "05001", "08001", "09001",
    "09002", "13001", "14001", "15001", "17001", "18001", "29001", "00001",
    "00002", "00024", "00035",
}


def matiere_creality(code):
    code = str(code or "").strip()
    if len(code) == 6:
        code = code[1:]
    if len(code) != 5:
        return ""
    if code in MATIERES_CREALITY:
        return MATIERES_CREALITY[code]
    return "PLA" if code in PLA_CREALITY else ""


def bobines_cfs(box):
    """Les bobines du CFS, module par module, emplacements A à D."""
    sorties = []
    for u in range(1, 5):
        mod = box.get("T%d" % u)
        if not isinstance(mod, dict) or str(mod.get("state", "")).lower() != "connect":
            continue
        couleurs = mod.get("color_value") or []
        matieres = mod.get("material_type") or []
        fabricants = mod.get("vender") or []
        for i, c in enumerate(couleurs[:4]):
            fab = str(fabricants[i] if i < len(fabricants) else "").strip()
            if fab.lower() == "none":
                continue
            c = str(c or "").strip()
            couleur = "#" + c[-6:] if len(c) >= 6 and not c.startswith("-") else ""
            type_ = matiere_creality(matieres[i] if i < len(matieres) else "")
            if not couleur and not type_:
                continue
            sorties.append({"slot": "T%d%s" % (u, "ABCD"[i]),
                            "type": type_ or "?", "color": couleur})
    return sorties


def normalise(etat):
    v = str(etat or "").lower()
    if "running" in v or "printing" in v:
        return "printing"
    if "pause" in v:
        return "paused"
    if "finish" in v or "complete" in v:
        return "finished"
    if "fail" in v or "error" in v:
        return "failed"
    if "prepare" in v or "slicing" in v:
        return "preparing"
    if "idle" in v or "standby" in v or "ready" in v:
        return "idle"
    return v or "unknown"


def lire_moonraker(m):
    base = "http://%s:%d" % (m["hote"], m.get("port", 7125))
    st = http_json(base + "/printer/objects/query"
                          "?print_stats&virtual_sdcard&display_status")["result"]["status"]
    ps = st.get("print_stats") or {}
    vs = st.get("virtual_sdcard") or {}
    fichier = ps.get("filename") or ""
    ecoule = float(ps.get("print_duration") or 0)
    avance = float(vs.get("progress") or 0)

    reste = -1
    if fichier:
        try:
            meta = http_json(base + "/server/files/metadata?filename="
                             + urllib.parse.quote(fichier))["result"]
            estime = float(meta.get("estimated_time") or 0)
            if estime > 0 and ecoule > 0:
                reste = round((estime - ecoule) / 60.0)
        except Exception:
            pass
    if reste < 0 and avance > 0.01 and ecoule > 0:
        reste = round((ecoule * (1 - avance) / avance) / 60.0)

    out = {"ok": True, "kind": "moonraker", "state": normalise(ps.get("state")),
           "file": fichier, "percent": int(round(avance * 100)),
           "remaining": max(0, reste), "ams": []}
    try:
        box = http_json(base + "/printer/objects/query?box")["result"]["status"].get("box")
        if box:
            out["ams"] = bobines_cfs(box)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# Bambu : MQTT sur le port 8883, code d'accès LAN — client minimal
# --------------------------------------------------------------------------

def _mqtt_longueur(n):
    b = b""
    while True:
        d, n = n % 128, n // 128
        b += bytes([d | 128 if n else d])
        if not n:
            return b


def _mqtt_texte(s):
    s = s.encode()
    return struct.pack(">H", len(s)) + s


def _recevoir(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError("connexion fermée")
        b += c
    return b


def _paquet(s):
    entete = _recevoir(s, 1)[0]
    mult, val = 1, 0
    while True:
        x = _recevoir(s, 1)[0]
        val += (x & 127) * mult
        mult *= 128
        if not x & 128:
            break
    return entete >> 4, _recevoir(s, val)


def lire_bambu(m, duree=8):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    s = ctx.wrap_socket(socket.create_connection((m["hote"], 8883), timeout=8))
    complet, partiel = None, None
    try:
        tete = _mqtt_texte("MQTT") + bytes([4, 0xC2]) + struct.pack(">H", 30)
        corps = (_mqtt_texte("relais-nmt-%d" % int(time.time()))
                 + _mqtt_texte("bblp") + _mqtt_texte(m["code"]))
        s.sendall(bytes([0x10]) + _mqtt_longueur(len(tete + corps)) + tete + corps)
        t, b = _paquet(s)
        if t != 2 or b[1] != 0:
            raise Exception("refusé par la machine — code d'accès LAN ou numéro de série erroné")

        sujet = "device/%s/report" % m["serie"]
        ab = struct.pack(">H", 1) + _mqtt_texte(sujet) + b"\x00"
        s.sendall(bytes([0x82]) + _mqtt_longueur(len(ab)) + ab)
        dem = json.dumps({"pushing": {"sequence_id": "1", "command": "pushall"}}).encode()
        pub = _mqtt_texte("device/%s/request" % m["serie"]) + dem
        s.sendall(bytes([0x30]) + _mqtt_longueur(len(pub)) + pub)

        fin = time.time() + duree
        s.settimeout(1)
        while time.time() < fin and complet is None:
            try:
                t, b = _paquet(s)
            except socket.timeout:
                continue
            if t != 3:
                continue
            lt = struct.unpack(">H", b[:2])[0]
            try:
                msg = json.loads(b[2 + lt:].decode("utf-8")).get("print") or {}
            except Exception:
                continue
            etat = "gcode_state" in msg or "mc_percent" in msg
            bobines = "ams" in msg or "vt_tray" in msg
            if etat and bobines:
                complet = msg
            elif etat and partiel is None:
                partiel = msg
    finally:
        try:
            s.close()
        except Exception:
            pass

    p = complet or partiel
    if p is None:
        raise Exception("aucune donnée reçue en %d s" % duree)

    bobines = []
    ams = p.get("ams") or {}
    try:
        presentes = int(str(ams.get("tray_exist_bits", "0")), 16)
    except Exception:
        presentes = 0
    for i, unite in enumerate(ams.get("ams") or []):
        num = int(unite.get("id", i))
        for j, t in enumerate(unite.get("tray") or []):
            idx = int(t.get("id", j))
            type_ = str(t.get("tray_type") or "")
            occupe = (presentes >> (num * 4 + idx)) & 1
            if not type_ and occupe:
                bobines.append({"slot": str(idx), "type": "?", "color": "", "inconnue": True})
            elif type_:
                c = str(t.get("tray_color") or "")
                bobines.append({"slot": str(idx), "type": type_,
                                "color": "#" + c[:6] if len(c) >= 6 else ""})
    ext = p.get("vt_tray") or {}
    if ext.get("tray_type"):
        c = str(ext.get("tray_color") or "")
        bobines.append({"slot": "ext", "type": ext["tray_type"],
                        "color": "#" + c[:6] if len(c) >= 6 else ""})

    fichier = p.get("subtask_name") or p.get("gcode_file") or ""
    return {"ok": True, "kind": "bambu", "state": normalise(p.get("gcode_state")),
            "file": fichier, "percent": int(p.get("mc_percent", -1)),
            "remaining": int(p.get("mc_remaining_time", -1)),
            "nozzle": p.get("nozzle_temper", 0), "bed": p.get("bed_temper", 0),
            "ams": bobines}


# --------------------------------------------------------------------------
# Relevé et publication
# --------------------------------------------------------------------------

def lisible(e, hote):
    t = str(e).lower()
    if "code d'accès" in t or "not authorized" in t:
        return str(e)
    if "timed out" in t or "timeout" in t:
        return "pas de réponse de %s — machine éteinte ?" % hote
    if "refused" in t:
        return "%s refuse la connexion — service coupé ?" % hote
    if "unreachable" in t or "no route" in t:
        return "%s hors du réseau" % hote
    return str(e)[:120]


def relever(machines):
    etats = {}
    for m in machines:
        cle = m["hote"]
        debut = time.time()
        try:
            etat = lire_moonraker(m) if m["type"] == "moonraker" else lire_bambu(m)
        except Exception as e:
            etat = {"ok": False, "kind": m["type"], "error": lisible(e, m["hote"])}
        etat["nom"] = m.get("nom", m["hote"])
        etat["at"] = int(time.time() * 1000)
        etat["ms"] = int((time.time() - debut) * 1000)
        etats[cle] = etat
    return etats


def publier(sujet, etats):
    corps = json.dumps({"v": 1, "at": int(time.time() * 1000), "machines": etats},
                       ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(SERVEUR + sujet, data=corps, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Title", "atelier")
    req.add_header("Priority", "min")  # pas de notification, juste du stockage
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def charger_reglages():
    chemin = os.path.join(ICI, "relais.json")
    if not os.path.exists(chemin):
        print("Fichier relais.json manquant à côté du programme.", file=sys.stderr)
        sys.exit(2)
    with open(chemin, encoding="utf-8") as f:
        c = json.load(f)
    if not c.get("sujet"):
        print("Le champ « sujet » est vide dans relais.json.", file=sys.stderr)
        sys.exit(2)
    return c


def main():
    c = charger_reglages()
    periode = max(30, int(c.get("periode", 60)))
    unique = "--une-fois" in sys.argv
    while True:
        debut = time.time()
        etats = relever(c.get("machines") or [])
        joignables = sum(1 for e in etats.values() if e.get("ok"))
        try:
            publier(c["sujet"], etats)
            print("%s — %d/%d machines, publié"
                  % (time.strftime("%H:%M:%S"), joignables, len(etats)), flush=True)
        except urllib.error.HTTPError as e:
            print("%s — publication refusée (HTTP %s)" % (time.strftime("%H:%M:%S"), e.code),
                  file=sys.stderr, flush=True)
        except Exception as e:
            print("%s — publication impossible : %s" % (time.strftime("%H:%M:%S"), e),
                  file=sys.stderr, flush=True)
        if unique:
            print(json.dumps(etats, ensure_ascii=False, indent=1))
            return
        time.sleep(max(5, periode - (time.time() - debut)))


if __name__ == "__main__":
    main()
