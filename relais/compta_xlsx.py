#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compta -> Argent.xlsx

L'application Atelier NMT publie ses commandes sur le canal ntfy du relais.
Ce script, resté sur le PC, les reprend et ajoute les lignes manquantes en bas
de la feuille Compta. Il ne modifie jamais une ligne déjà présente.

Le classeur contient des graphiques et des tableaux croisés dynamiques : les
bibliothèques Excel courantes les perdent à l'enregistrement. On écrit donc
directement dans le XML du fichier, et tout le reste du classeur ressort
octet pour octet identique.

    python compta_xlsx.py            # ajoute les lignes manquantes
    python compta_xlsx.py --essai    # montre ce qui serait ajouté, sans écrire

Réglages : compta.json à côté de ce fichier.
"""

import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from datetime import date, datetime

ICI = os.path.dirname(os.path.abspath(__file__))
REGLAGES = os.path.join(ICI, "compta.json")
SERVEUR = "https://ntfy.sh/"
FENETRE = "12h"          # ntfy ne garde pas les messages plus longtemps

# code pays renvoyé par Shopify -> abréviation utilisée dans le tableur
PAYS = {
    "FR": "FR", "US": "USA", "GB": "UK", "PT": "PO", "GR": "GR", "IT": "IT",
    "ES": "ES", "DE": "DE", "BE": "BE", "CH": "CH", "NL": "NL", "LU": "LU",
    "CA": "CA", "AU": "AU", "IE": "IE", "AT": "AT", "PL": "PL", "SE": "SE",
    "DK": "DK", "NO": "NO", "FI": "FI", "CZ": "CZ", "JP": "JP",
}

# colonne de la feuille Compta -> ce qu'on y met
COL_DATE, COL_NOM, COL_PAYS = "A", "B", "C"
COL_PRIX, COL_POIDS = "E", "L"
COL_AVANCEMENT, COL_RECU, COL_OBJET = "N", "O", "Q"
COL_REF = "X"            # colonne libre, sert de clé anti-doublon

DONNEES = {COL_DATE, COL_NOM, COL_PAYS, COL_PRIX, COL_POIDS,
           COL_AVANCEMENT, COL_RECU, COL_OBJET, COL_REF}

# colonnes de synthèse mensuelle : elles ne concernent qu'une ligne sur dix,
# on ne les recopie jamais
SYNTHESE = {"R", "S", "T", "U", "V", "W"}


# ----------------------------------------------------------------------
# réglages
# ----------------------------------------------------------------------

def charger_reglages():
    if not os.path.exists(REGLAGES):
        modele = {
            "sujet": "mets-ici-le-sujet-du-relais",
            "tableur": r"C:\Users\natha\Documents\Argent.xlsx",
            "feuille": "Compta",
        }
        with open(REGLAGES, "w", encoding="utf-8") as f:
            json.dump(modele, f, indent=2, ensure_ascii=False)
        print("compta.json vient d'être créé. Renseigne-le puis relance.")
        sys.exit(1)

    with open(REGLAGES, encoding="utf-8") as f:
        r = json.load(f)
    if not r.get("sujet") or not r.get("tableur"):
        print("compta.json : il manque 'sujet' ou 'tableur'.")
        sys.exit(1)
    r.setdefault("feuille", "Compta")
    return r


# ----------------------------------------------------------------------
# lecture du canal ntfy
# ----------------------------------------------------------------------

def lire_canal(sujet):
    """Renvoie les commandes publiées par l'app, la plus récente version de
    chacune, rangées par référence."""
    url = SERVEUR + sujet + "/json?poll=1&since=" + FENETRE
    req = urllib.request.Request(url, headers={"User-Agent": "compta-atelier/1"})
    with urllib.request.urlopen(req, timeout=20) as rep:
        brut = rep.read().decode("utf-8", "replace")

    commandes, vues = {}, {}
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            evt = json.loads(ligne)
        except ValueError:
            continue
        if evt.get("event") != "message":
            continue
        try:
            charge = json.loads(evt.get("message") or "{}")
        except ValueError:
            continue
        if charge.get("t") != "compta":
            continue
        quand = charge.get("at", 0)
        for c in charge.get("c", []):
            ref = c.get("r")
            if not ref:
                continue
            if quand >= vues.get(ref, -1):
                commandes[ref] = c
                vues[ref] = quand
    return commandes


# ----------------------------------------------------------------------
# lecture du classeur
# ----------------------------------------------------------------------

def chemin_feuille(zf, nom):
    """Chemin interne du XML de la feuille portant ce nom."""
    wb = zf.read("xl/workbook.xml").decode("utf-8")
    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")

    rid = None
    for m in re.finditer(r"<sheet\b[^>]*>", wb):
        bal = m.group(0)
        n = re.search(r'name="([^"]*)"', bal)
        r = re.search(r'r:id="([^"]*)"', bal)
        if n and r and n.group(1) == nom:
            rid = r.group(1)
            break
    if not rid:
        raise SystemExit("Feuille « %s » introuvable dans le classeur." % nom)

    m = re.search(r'<Relationship[^>]*Id="%s"[^>]*Target="([^"]*)"' % re.escape(rid), rels)
    if not m:
        raise SystemExit("Lien cassé vers la feuille « %s »." % nom)
    cible = m.group(1).lstrip("/")
    return cible if cible.startswith("xl/") else "xl/" + cible


def chaines_partagees(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    xml = zf.read("xl/sharedStrings.xml").decode("utf-8")
    out = []
    for si in re.findall(r"<si>(.*?)</si>", xml, re.S):
        out.append("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
    return [detexter(t) for t in out]


def detexter(t):
    return (t.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


def textor(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
                  .replace(">", "&gt;").replace('"', "&quot;"))


CELLULE = re.compile(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', re.S)
LIGNE = re.compile(r'<row\b([^>]*?)(?:/>|>(.*?)</row>)', re.S)


def colonne_de(ref):
    return re.match(r"([A-Z]+)", ref or "").group(1) if ref else ""


def lire_lignes(xml_feuille, chaines):
    """[(numero, attributs, {colonne: (attributs_cellule, contenu, valeur)})]"""
    corps = re.search(r"<sheetData\b[^>]*>(.*?)</sheetData>", xml_feuille, re.S)
    if not corps:
        raise SystemExit("Feuille illisible : pas de bloc sheetData.")

    lignes = []
    for m in LIGNE.finditer(corps.group(1)):
        attrs, dedans = m.group(1), m.group(2) or ""
        num = int(re.search(r'r="(\d+)"', attrs).group(1))
        cases = {}
        for c in CELLULE.finditer(dedans):
            cattrs, cdedans = c.group(1), c.group(2) or ""
            ref = re.search(r'r="([A-Z]+\d+)"', cattrs)
            if not ref:
                continue
            col = colonne_de(ref.group(1))
            typ = re.search(r't="([^"]*)"', cattrs)
            typ = typ.group(1) if typ else "n"
            v = re.search(r"<v>(.*?)</v>", cdedans, re.S)
            val = detexter(v.group(1)) if v else ""
            if typ == "s" and val.isdigit():
                val = chaines[int(val)] if int(val) < len(chaines) else ""
            elif typ == "inlineStr":
                it = re.search(r"<t[^>]*>(.*?)</t>", cdedans, re.S)
                val = detexter(it.group(1)) if it else ""
            cases[col] = (cattrs, cdedans, val)
        lignes.append((num, attrs, cases))
    return lignes, corps


# ----------------------------------------------------------------------
# écriture d'une ligne
# ----------------------------------------------------------------------

EPOQUE = date(1899, 12, 30)


def serie_excel(ms):
    d = datetime.fromtimestamp(ms / 1000.0).date()
    return (d - EPOQUE).days


def style_de(cattrs):
    m = re.search(r's="(\d+)"', cattrs or "")
    return ' s="%s"' % m.group(1) if m else ""


def decaler(formule, depuis, vers):
    """Recopie une formule d'une ligne à l'autre, comme un cliquer-glisser.
    Seules les références à la ligne d'origine bougent ; $A$1 reste figé."""
    ecart = vers - depuis

    def bouge(m):
        avant, col, dollar, lig = m.group(1), m.group(2), m.group(3), int(m.group(4))
        if dollar or lig != depuis:
            return m.group(0)
        return "%s%s%d" % (avant, col, lig + ecart)

    return re.sub(r"(\$?)([A-Z]{1,3})(\$?)(\d+)", bouge, formule)


def cellule(col, ligne, valeur, cattrs_modele, formule=None):
    st = style_de(cattrs_modele)
    ref = "%s%d" % (col, ligne)
    if formule is not None:
        return '<c r="%s"%s><f>%s</f></c>' % (ref, st, textor(formule))
    if valeur is None or valeur == "":
        return '<c r="%s"%s/>' % (ref, st)
    if isinstance(valeur, (int, float)):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, st, valeur)
    return '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (
        ref, st, textor(valeur))


ORDRE_COL = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def rang(col):
    n = 0
    for ch in col:
        n = n * 26 + (ORDRE_COL.index(ch) + 1)
    return n


def batir_ligne(num, cmd, modele_num, modele_cases, attrs_modele):
    """Construit le XML d'une ligne : les données viennent de l'app, les
    formules sont recopiées de la dernière ligne déjà remplie."""
    valeurs = {
        COL_DATE: serie_excel(cmd.get("d") or 0),
        COL_NOM: cmd.get("n", ""),
        COL_PAYS: PAYS.get((cmd.get("p") or "").upper(), (cmd.get("p") or "").upper()),
        COL_PRIX: cmd.get("e", 0) or "",
        COL_POIDS: cmd.get("g", 0) or "",
        COL_AVANCEMENT: cmd.get("s", "not started"),
        COL_RECU: (cmd.get("e", 0) or 0) if str(cmd.get("r", "")).startswith("#") else 0,
        COL_OBJET: cmd.get("o", ""),
        COL_REF: cmd.get("r", ""),
    }

    cases = []
    for col in sorted(set(list(modele_cases.keys()) + list(valeurs.keys())), key=rang):
        if col in SYNTHESE:
            continue
        cattrs, cdedans, _ = modele_cases.get(col, ("", "", ""))
        f = re.search(r"<f[^>]*>(.*?)</f>", cdedans, re.S)
        if col in DONNEES:
            cases.append(cellule(col, num, valeurs.get(col, ""), cattrs))
        elif f:
            cases.append(cellule(col, num, None, cattrs,
                                 formule=decaler(detexter(f.group(1)), modele_num, num)))
        elif cattrs:
            cases.append(cellule(col, num, "", cattrs))

    attrs = re.sub(r'\sr="\d+"', "", attrs_modele or "")
    attrs = re.sub(r'\sspans="[^"]*"', "", attrs)
    return '<row r="%d"%s>%s</row>' % (num, attrs, "".join(cases))


# ----------------------------------------------------------------------
# réécriture du classeur
# ----------------------------------------------------------------------

def reecrire(source, chemin_xml, nouveau_xml, essai):
    if essai:
        return
    sauvegarde = source + ".avant-compta"
    shutil.copy2(source, sauvegarde)

    temporaire = source + ".tmp"
    with zipfile.ZipFile(sauvegarde, "r") as lu, \
         zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as ecrit:
        for item in lu.infolist():
            # calcChain décrit l'ordre de calcul des formules ; il devient faux
            # dès qu'on ajoute une ligne, et Excel le refabrique tout seul
            if item.filename == "xl/calcChain.xml":
                continue
            donnees = lu.read(item.filename)
            if item.filename == chemin_xml:
                donnees = nouveau_xml.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                donnees = forcer_recalcul(donnees.decode("utf-8")).encode("utf-8")
            elif item.filename == "[Content_Types].xml":
                donnees = re.sub(
                    r'<Override[^>]*PartName="/xl/calcChain\.xml"[^>]*/>', "",
                    donnees.decode("utf-8")).encode("utf-8")
            ecrit.writestr(item, donnees)

    os.replace(temporaire, source)
    return sauvegarde


def titrer_colonne_ref(xml, lignes):
    """Écrit « Réf » en haut de la colonne des références, si elle est vide.
    Sans ça la colonne ressemble à une salissure au bout du tableau."""
    entete = next((cases for num, _, cases in lignes if num == 1), None)
    if entete is None or (entete.get(COL_REF) or ("", "", ""))[2]:
        return xml

    modele = entete.get(COL_OBJET) or ("", "", "")
    case = cellule(COL_REF, 1, "Réf", modele[0])
    if COL_REF in entete:
        return re.sub(r'<c r="%s1"[^>]*(?:/>|>.*?</c>)' % COL_REF, case, xml, count=1, flags=re.S)
    return re.sub(r"(<row\b[^>]*\br=\"1\"[^>]*>)(.*?)(</row>)",
                  lambda m: m.group(1) + m.group(2) + case + m.group(3),
                  xml, count=1, flags=re.S)


def forcer_recalcul(wb):
    """Excel recalcule tout à l'ouverture : les formules ajoutées n'ont donc
    pas besoin d'une valeur écrite d'avance."""
    if "<calcPr" in wb:
        def poser(m):
            bal = m.group(0)
            bal = re.sub(r'\sfullCalcOnLoad="[^"]*"', "", bal)
            return bal[:-2] + ' fullCalcOnLoad="1"/>' if bal.endswith("/>") else bal
        return re.sub(r"<calcPr\b[^>]*/>", poser, wb, count=1)
    return wb.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')


# ----------------------------------------------------------------------
# programme
# ----------------------------------------------------------------------

def main():
    essai = "--essai" in sys.argv
    r = charger_reglages()
    tableur = os.path.expanduser(r["tableur"])
    if not os.path.exists(tableur):
        print("Tableur introuvable : %s" % tableur)
        sys.exit(1)

    commandes = lire_canal(r["sujet"])
    if not commandes:
        print("Rien sur le canal. Ouvre Réglages dans l'app et touche "
              "« Envoyer maintenant », puis relance.")
        return

    with zipfile.ZipFile(tableur, "r") as zf:
        chemin = chemin_feuille(zf, r["feuille"])
        chaines = chaines_partagees(zf)
        xml = zf.read(chemin).decode("utf-8")

    lignes, corps = lire_lignes(xml, chaines)

    # ce qui est déjà dans la feuille
    deja, modele = set(), None
    for num, attrs, cases in lignes:
        ref = (cases.get(COL_REF) or ("", "", ""))[2]
        if ref:
            deja.add(ref)
        if (cases.get(COL_DATE) or ("", "", ""))[2] and num > 1:
            modele = (num, attrs, cases)
            # les lignes écrites avant l'existence de la colonne Réf : on les
            # reconnaît à la date et à l'objet, pour ne pas les redoubler
            objet = (cases.get(COL_OBJET) or ("", "", ""))[2]
            date_ = (cases.get(COL_DATE) or ("", "", ""))[2]
            if objet and date_:
                deja.add("~%s|%s" % (date_, objet.strip().lower()))

    if not modele:
        print("Aucune ligne de vente dans la feuille : impossible de savoir "
              "quelles formules recopier.")
        sys.exit(1)

    modele_num, modele_attrs, modele_cases = modele

    a_ajouter = []
    for ref, cmd in sorted(commandes.items(), key=lambda kv: kv[1].get("d", 0)):
        if ref in deja:
            continue
        cle = "~%s|%s" % (serie_excel(cmd.get("d") or 0),
                          (cmd.get("o") or "").strip().lower())
        if cle in deja:
            continue
        a_ajouter.append((ref, cmd))

    if not a_ajouter:
        print("Le tableur est déjà à jour (%d commande(s) sur le canal)." % len(commandes))
        return

    suivante = max(n for n, _, _ in lignes) + 1
    neuves = []
    for i, (ref, cmd) in enumerate(a_ajouter):
        num = suivante + i
        neuves.append(batir_ligne(num, cmd, modele_num, modele_cases, modele_attrs))
        d = datetime.fromtimestamp((cmd.get("d") or 0) / 1000.0).strftime("%d/%m/%Y")
        print("  ligne %-4d %-10s %-11s %7s €  %6s g  %-12s %s" % (
            num, ref, d, cmd.get("e", "-"), cmd.get("g", "-"),
            cmd.get("s", ""), (cmd.get("o") or "")[:34]))

    dernier = suivante + len(a_ajouter) - 1
    nouveau = (xml[:corps.end(1)] + "".join(neuves) + xml[corps.end(1):])
    nouveau = titrer_colonne_ref(nouveau, lignes)
    nouveau = re.sub(r'(<dimension ref="[A-Z]+\d+:[A-Z]+)(\d+)"',
                     lambda m: '%s%d"' % (m.group(1), max(int(m.group(2)), dernier)),
                     nouveau, count=1)

    if essai:
        print("\n--essai : rien n'a été écrit. Relance sans --essai pour valider.")
        return

    sauvegarde = reecrire(tableur, chemin, nouveau, essai)
    print("\n%d ligne(s) ajoutée(s) à la feuille %s." % (len(a_ajouter), r["feuille"]))
    print("Copie de l'état d'avant : %s" % sauvegarde)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
