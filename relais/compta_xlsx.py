#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compta -> Argent.xlsx

L'application Atelier NMT publie ses commandes sur le canal ntfy du relais.
Ce script, resté sur le PC, les reprend et complète la feuille Compta. Il ne
modifie jamais une ligne déjà écrite.

Deux précautions commandent tout le reste :

1. Le classeur contient quatre graphiques et trois tableaux croisés. Les
   bibliothèques Excel courantes les perdent à l'enregistrement, donc on écrit
   directement dans le XML et tout le reste du fichier ressort octet pour
   octet identique.

2. On n'insère aucune ligne. Le bas de la feuille est occupé par les totaux,
   et sous les totaux par les ventes annulées. Insérer décalerait ces blocs et
   fausserait les plages des graphiques. On remplit donc seulement les lignes
   restées libres entre la dernière vente et la fin des plages additionnées —
   et on refuse d'écrire plus loin.

    python compta_xlsx.py            # complète la feuille
    python compta_xlsx.py --essai    # montre ce qui serait écrit, sans écrire

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

# code pays renvoyé par Shopify -> abréviation telle que Nathan l'écrit déjà
# dans la colonne C. Un pays absent de cette table ressort en code ISO.
PAYS = {
    "FR": "FR", "US": "USA", "GB": "UK", "IT": "IT", "CA": "CA",
    "PT": "PO", "BE": "BELG", "CH": "Sui", "NL": "HO", "AU": "AUS",
    "AT": "AUT", "DE": "GR", "GR": "GR", "ES": "ES", "LU": "LU",
    "PL": "PL", "SE": "SE", "DK": "DK", "NO": "NO", "FI": "FI",
    "CZ": "CZ", "IE": "IE", "JP": "JP",
}

# colonne de la feuille Compta -> ce qu'on y met
COL_DATE, COL_NOM, COL_PAYS = "A", "B", "C"
COL_PRIX, COL_POIDS = "E", "L"
COL_AVANCEMENT, COL_RECU, COL_OBJET = "N", "O", "Q"
COL_REF = "X"            # plus écrite ; relue au cas où un ancien essai l'ait remplie

# colonnes dont on écrit la valeur ; partout ailleurs on recopie la formule
DONNEES = {COL_DATE, COL_NOM, COL_PAYS, COL_PRIX, COL_POIDS,
           COL_AVANCEMENT, COL_RECU, COL_OBJET}

# colonnes de synthèse mensuelle : elles ne suivent pas les ventes ligne par
# ligne et descendent plus bas qu'elles. On n'y touche jamais.
SYNTHESE = {"R", "S", "T", "U", "V", "W"}

# Le numéro de commande est déjà écrit à la main dans la colonne B (« #1044 ») :
# c'est lui, et non une colonne ajoutée, qui dit de façon fiable si une vente
# est déjà saisie.
REFERENCE = re.compile(r"#\s*(\d{3,})")

# les sommes de bas de tableau, qui bornent la zone où l'on a le droit d'écrire
SOMME_PRIX = re.compile(r"SUM\(%s\d+:%s(\d+)\)" % (COL_PRIX, COL_PRIX))
SOMME_POIDS = re.compile(r"SUM\(%s\d+:%s(\d+)\)" % (COL_POIDS, COL_POIDS))


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

    with open(REGLAGES, encoding="utf-8-sig") as f:
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
    """[(numero, attributs, cases, debut, fin)]

    cases : {colonne: (attributs, contenu, valeur)}
    debut/fin : bornes du <row> dans xml_feuille, pour pouvoir le remplacer
    sur place plus tard."""
    corps = re.search(r"<sheetData\b[^>]*>(.*?)</sheetData>", xml_feuille, re.S)
    if not corps:
        raise SystemExit("Feuille illisible : pas de bloc sheetData.")
    base = corps.start(1)

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
        lignes.append((num, attrs, cases, base + m.start(), base + m.end()))
    return lignes, corps


# ----------------------------------------------------------------------
# formules partagées
# ----------------------------------------------------------------------
#
# Excel n'écrit une formule recopiée qu'une seule fois, dans la cellule
# « maîtresse » (la seule à porter un attribut ref) ; les cellules suivantes
# s'y réfèrent par un numéro si. Sans cette table, les colonnes calculées
# d'une ligne recopiée ressortiraient vides.

F_VIDE = re.compile(r"<f\b([^>]*?)/>")
F_PLEINE = re.compile(r"<f\b([^>]*)>(.*?)</f>", re.S)


def formules_partagees(lignes):
    """si -> (ligne où la formule est écrite, texte de la formule)"""
    table = {}
    for num, _attrs, cases, _d, _f in lignes:
        for _col, (_ca, cdedans, _v) in cases.items():
            m = F_PLEINE.search(cdedans)
            if not m or not m.group(2).strip():
                continue
            at = m.group(1)
            if 't="shared"' not in at or "ref=" not in at:
                continue
            si = re.search(r'si="(\d+)"', at)
            if si:
                table.setdefault(si.group(1), (num, detexter(m.group(2))))
    return table


def formule_de(cdedans, ligne_modele, partagees):
    """(texte, ligne d'origine) de la formule d'une cellule, ou (None, None)."""
    m = F_VIDE.search(cdedans)
    if m:
        si = re.search(r'si="(\d+)"', m.group(1))
        if si and si.group(1) in partagees:
            return partagees[si.group(1)][1], partagees[si.group(1)][0]
        return None, None
    m = F_PLEINE.search(cdedans)
    if m and m.group(2).strip():
        return detexter(m.group(2)), ligne_modele
    return None, None


# ----------------------------------------------------------------------
# où a-t-on le droit d'écrire
# ----------------------------------------------------------------------

def zone_ecriture(lignes):
    """Renvoie (modele, premiere, derniere).

    modele   : (numero, attributs, cases) de la dernière vente saisie, dont on
               recopie la mise en forme et les formules.
    premiere : première ligne entièrement vide après elle.
    derniere : dernière ligne encore comprise dans les deux sommes de bas de
               tableau (prix et poids). Au-delà, une vente écrite ne serait
               plus comptée dans les totaux : on refuse d'y aller.
    """
    totaux, fins_prix, fins_poids = None, [], []
    for num, _attrs, cases, _d, _f in lignes:
        for col, (_ca, cdedans, _v) in cases.items():
            if col == COL_PRIX:
                for m in SOMME_PRIX.finditer(cdedans):
                    fins_prix.append(int(m.group(1)))
                    totaux = num if totaux is None else min(totaux, num)
            elif col == COL_POIDS:
                for m in SOMME_POIDS.finditer(cdedans):
                    fins_poids.append(int(m.group(1)))

    if totaux is None or not fins_prix or not fins_poids:
        raise SystemExit(
            "Pas de ligne de total SUM(%s…)/SUM(%s…) dans la feuille : je ne sais "
            "pas où s'arrête le tableau des ventes, donc je n'écris rien."
            % (COL_PRIX, COL_POIDS))

    derniere = min(max(fins_prix), max(fins_poids))

    # dernière ligne qui contient quelque chose au-dessus des totaux : les
    # colonnes de synthèse descendent deux lignes plus bas que les ventes
    occupees = [num for num, _a, cases, _d, _f in lignes if num < totaux and cases]
    premiere = (max(occupees) if occupees else 1) + 1

    modele = None
    for num, attrs, cases, _d, _f in lignes:
        if 1 < num < totaux and (cases.get(COL_DATE) or ("", "", ""))[2]:
            modele = (num, attrs, cases)
    if modele is None:
        raise SystemExit("Aucune vente dans la feuille : rien à recopier.")

    return modele, premiere, derniere


def cle(texte):
    """Ce qui identifie une vente de façon stable : son numéro de commande
    Shopify (#1044 -> « 1044 »), ou à défaut le libellé tel quel pour les
    ventes saisies à la main."""
    texte = str(texte or "").strip()
    m = REFERENCE.search(texte)
    if m:
        return m.group(1)
    return texte.lower() or None


def deja_saisies(lignes):
    """Toute la feuille est balayée, y compris sous les totaux : c'est là que
    Nathan gare les ventes annulées, et elles ne doivent pas revenir."""
    vues = set()
    for _num, _attrs, cases, _d, _f in lignes:
        for col in (COL_NOM, COL_REF):
            k = cle((cases.get(col) or ("", "", ""))[2])
            if k:
                vues.add(k)
    return vues


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
        espace = ' xml:space="preserve"' if formule != formule.strip() else ""
        return '<c r="%s"%s><f%s>%s</f></c>' % (ref, st, espace, textor(formule))
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


def batir_ligne(num, cmd, modele, partagees):
    """XML d'une ligne : les données viennent de l'app, les formules sont
    recopiées de la dernière vente saisie."""
    modele_num, attrs_modele, modele_cases = modele

    valeurs = {
        COL_DATE: serie_excel(cmd.get("d") or 0),
        COL_NOM: cmd.get("r", ""),
        COL_PAYS: PAYS.get((cmd.get("p") or "").upper(), (cmd.get("p") or "").upper()),
        COL_PRIX: cmd.get("e", 0) or "",
        COL_POIDS: cmd.get("g", 0) or "",
        COL_AVANCEMENT: cmd.get("s", "not started"),
        # ce qui est réellement tombé sur le compte, frais Shopify déduits :
        # l'app ne le connaît pas, Nathan le complète au versement
        COL_RECU: 0,
        COL_OBJET: cmd.get("o", ""),
    }

    cases = []
    for col in sorted(set(list(modele_cases.keys()) + list(valeurs.keys())), key=rang):
        if col in SYNTHESE:
            continue
        cattrs, cdedans, _v = modele_cases.get(col, ("", "", ""))
        if col in DONNEES:
            cases.append(cellule(col, num, valeurs.get(col, ""), cattrs))
            continue
        f, origine = formule_de(cdedans, modele_num, partagees)
        if f is not None:
            cases.append(cellule(col, num, None, cattrs,
                                 formule=decaler(f, origine, num)))
        elif cattrs:
            cases.append(cellule(col, num, "", cattrs))

    attrs = re.sub(r'\sr="\d+"', "", attrs_modele or "")
    attrs = re.sub(r'\sspans="[^"]*"', "", attrs)
    return '<row r="%d"%s>%s</row>' % (num, attrs, "".join(cases))


def etendre_etendue(xml, derniere):
    """La balise dimension annonce l'étendue utilisée de la feuille. Elle
    couvre déjà largement la zone libre, mais autant ne pas dépendre de ça."""
    def pousser(m):
        return '%s%d"' % (m.group(1), max(int(m.group(2)), derniere))
    return re.sub(r'(<dimension ref="[A-Z]+\d+:[A-Z]+)(\d+)"', pousser, xml, count=1)


def recomposer(xml, corps, lignes, neuves):
    """Remet la feuille à plat en remplaçant sur place les lignes réécrites et
    en glissant les autres à leur rang. Rien n'est décalé : les numéros de
    ligne de tout le reste du classeur restent valables."""
    restants = sorted(neuves)
    out = []
    for num, _attrs, _cases, deb, fin in lignes:
        while restants and restants[0] < num:
            out.append(neuves[restants.pop(0)])
        if num in neuves:
            out.append(neuves[num])
            restants.remove(num)
        else:
            out.append(xml[deb:fin])
    for n in restants:
        out.append(neuves[n])
    return xml[:corps.start(1)] + "".join(out) + xml[corps.end(1):]


# ----------------------------------------------------------------------
# réécriture du classeur
# ----------------------------------------------------------------------

def reecrire(source, chemin_xml, nouveau_xml):
    sauvegarde = source + ".avant-compta"
    shutil.copy2(source, sauvegarde)

    temporaire = source + ".tmp"
    with zipfile.ZipFile(sauvegarde, "r") as lu, \
         zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as ecrit:
        for item in lu.infolist():
            # calcChain décrit l'ordre de calcul des formules ; il devient faux
            # dès qu'on en ajoute une, et Excel le refabrique tout seul
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

def jour(ms):
    return datetime.fromtimestamp((ms or 0) / 1000.0).strftime("%d/%m/%Y")


def faire_de_la_place(derniere):
    """Agrandir le tableau est une opération de structure : Excel la fait
    proprement (il décale les totaux, rallonge les sommes et recale les
    graphiques), ce script non. Autant le dire clairement."""
    print("Pour faire de la place, dans Excel :")
    print("  sélectionne les lignes %d à %d par leurs numéros, clic droit, "
          "« Insérer »." % (derniere, derniere + 29))
    print("Excel décale les totaux et rallonge tout seul les sommes : tu "
          "récupères")
    print("30 lignes libres, et tout le reste du classeur reste juste.")


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
    partagees = formules_partagees(lignes)
    modele, premiere, derniere = zone_ecriture(lignes)
    deja = deja_saisies(lignes)

    manquantes = []
    for ref, cmd in sorted(commandes.items(), key=lambda kv: kv[1].get("d", 0)):
        if cle(ref) not in deja:
            manquantes.append((ref, cmd))

    print("%d commande(s) sur le canal, %d déjà dans la feuille."
          % (len(commandes), len(commandes) - len(manquantes)))

    if not manquantes:
        print("Le tableur est à jour.")
        return

    place = derniere - premiere + 1
    if place <= 0:
        print()
        print("Plus une seule ligne libre : tes ventes descendent jusqu'à la "
              "ligne %d," % (premiere - 1))
        print("et tes totaux ne comptent rien au-delà de la ligne %d. Je "
              "n'écris donc rien :" % derniere)
        print("une ligne écrite plus bas ne serait additionnée nulle part.")
        print()
        faire_de_la_place(derniere)
        sys.exit(1)

    retenues = manquantes[:place]
    refusees = manquantes[place:]

    neuves = {}
    print()
    for i, (ref, cmd) in enumerate(retenues):
        num = premiere + i
        neuves[num] = batir_ligne(num, cmd, modele, partagees)
        print("  ligne %-4d %-10s %-11s %7s €  %6s g  %-12s %s" % (
            num, ref, jour(cmd.get("d")), cmd.get("e", "-"), cmd.get("g", "-"),
            cmd.get("s", ""), (cmd.get("o") or "")[:34]))

    if refusees:
        print()
        print("Pas écrites : il n'y a plus de place avant tes totaux.")
        for ref, cmd in refusees:
            print("  %-10s %s" % (ref, jour(cmd.get("d"))))

    nouveau = recomposer(xml, corps, lignes, neuves)
    nouveau = etendre_etendue(nouveau, max(neuves))

    if essai:
        print()
        print("--essai : rien n'a été écrit. Relance sans --essai pour valider.")
        return

    sauvegarde = reecrire(tableur, chemin, nouveau)
    print()
    print("%d ligne(s) écrite(s) dans la feuille %s." % (len(retenues), r["feuille"]))
    print("Colonne O (Reçu) laissée à 0 : à compléter au versement Shopify.")
    print("Copie de l'état d'avant : %s" % sauvegarde)

    reste = derniere - (premiere + len(retenues) - 1)
    if refusees or 0 <= reste <= 4:
        print()
        if not refusees:
            print("Attention : il ne reste que %d ligne(s) libre(s) avant tes "
                  "totaux." % reste)
        faire_de_la_place(derniere)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
