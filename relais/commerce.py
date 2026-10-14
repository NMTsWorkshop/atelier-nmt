# -*- coding: utf-8 -*-
"""Ce que l'atelier dit à la boutique.

Trois choses, dans cet ordre :

1. Le relais apprend les commandes. L'app les publie déjà sur le canal
   pour le tableur de compta ; il ne les lisait pas. Il les lit et les
   garde sur disque, parce que ntfy n'en garde la trace que douze heures
   et qu'un relais redémarré ne doit pas repartir de rien.

2. Il calcule un délai de fabrication. Le temps qui reste à sortir est
   connu fichier par fichier (la bibliothèque lit les gcodes tranchés) ;
   il se rattache à une commande par son numéro, se répartit sur les
   machines de sa famille, et devient un nombre de jours.

3. Il l'écrit dans la boutique. Une fois par heure, et seulement si la
   valeur a bougé : un metafield réécrit à l'identique ne sert à rien et
   consomme du quota.

Le jeton d'écriture Shopify vit ici, sur le Pi, et nulle part ailleurs.
Celui de l'app ne sait que lire les commandes ; celui-ci peut écrire, et
un téléphone perdu ne doit pas l'emporter.
"""

import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SERVEUR = "https://ntfy.sh/"

# Shopify n'est joignable qu'en clair dans un seul cas : le test de bout en
# bout, qui monte une fausse boutique sur la boucle locale. En service, ça
# reste https, et le jeton ne part donc jamais en clair.
PROTOCOLE = "https"

# Le relais ne garde pas les commandes expédiées : elles ne pèsent plus
# sur le délai, et la liste doit rester petite.
STATUT_EXPEDIEE = "delivered"

VERROU = threading.RLock()


# ----------------------------------------------------------------------
# 1. les commandes, apprises du canal et gardées sur disque
# ----------------------------------------------------------------------

class Commandes:
    """La liste des commandes telle que l'app la publie.

    Clé : la référence (« #1045 »). On ne garde que ce qui sert au délai
    et à l'affichage du journal — ni client, ni prix, ni pays : le relais
    n'en a pas besoin, et ce qu'on ne stocke pas ne fuit pas."""

    CHAMPS = ("r", "d", "s", "g")

    def __init__(self, chemin):
        self.chemin = chemin
        self._cache = None

    def etat(self):
        with VERROU:
            if self._cache is None:
                try:
                    with open(self.chemin, encoding="utf-8") as f:
                        self._cache = json.load(f)
                except Exception:
                    self._cache = {"commandes": {}, "vu": 0}
                self._cache.setdefault("commandes", {})
                self._cache.setdefault("vu", 0)
            return self._cache

    def _ecrire(self, etat):
        with VERROU:
            self._cache = etat
            provisoire = self.chemin + ".tmp"
            with open(provisoire, "w", encoding="utf-8") as f:
                json.dump(etat, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(provisoire, self.chemin)

    def maj(self, lignes, at=0):
        """Range ce qui vient d'arriver. Renvoie le nombre de nouveautés.

        L'app publie la liste entière à chaque fois, pas un delta : une
        ligne absente d'un envoi ne veut pas dire qu'elle a disparu, elle
        peut simplement être dans un autre lot."""
        etat = dict(self.etat())
        etat["commandes"] = dict(etat["commandes"])
        change = 0
        for l in lignes or []:
            ref = str(l.get("r") or "").strip()
            if not ref:
                continue
            garde = {c: l[c] for c in self.CHAMPS if l.get(c) is not None}
            garde["numero"] = numero(ref)
            if etat["commandes"].get(ref) != garde:
                etat["commandes"][ref] = garde
                change += 1
        if at:
            etat["vu"] = max(int(etat.get("vu") or 0), int(at))
        if change:
            self._ecrire(etat)
        return change

    def toutes(self):
        return list(self.etat()["commandes"].values())

    def en_cours(self):
        """Celles qui pèsent encore sur le délai : tout sauf les expédiées."""
        return [c for c in self.toutes()
                if str(c.get("s") or "") != STATUT_EXPEDIEE]

    def oublier_expediees(self, garde=200):
        """Une commande expédiée ne sert plus à rien ; on en garde quelques
        unes pour le journal, pas des milliers."""
        etat = dict(self.etat())
        toutes = etat["commandes"]
        expediees = [(c.get("d") or 0, r) for r, c in toutes.items()
                     if str(c.get("s") or "") == STATUT_EXPEDIEE]
        if len(expediees) <= garde:
            return 0
        expediees.sort()
        for _, r in expediees[:len(expediees) - garde]:
            toutes.pop(r, None)
        self._ecrire(etat)
        return len(expediees) - garde


NUMERO = re.compile(r"(?<!\d)(\d{3,})(?!\d)")


def numero(texte):
    """« #1045 » → « 1045 », « 1045 Mando » → « 1045 », sinon ''."""
    m = NUMERO.search(str(texte or ""))
    return m.group(1) if m else ""


def lire_compta(sujet, depuis="12h"):
    """Les commandes que l'app a publiées sur le canal.

    Elle publie la liste entière découpée en lots ; on ne garde que les
    lots du dernier envoi, reconnaissable à son horodatage."""
    url = (SERVEUR + urllib.parse.quote(sujet)
           + "/json?poll=1&since=" + str(depuis))
    req = urllib.request.Request(url, headers={"User-Agent": "relais-atelier/1"})
    with urllib.request.urlopen(req, timeout=15) as rep:
        brut = rep.read().decode("utf-8", "replace")

    envois = {}
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            evt = json.loads(ligne)
            if evt.get("event") != "message":
                continue
            charge = json.loads(evt.get("message") or "{}")
        except ValueError:
            continue
        if charge.get("t") != "compta":
            continue
        at = int(charge.get("at") or 0)
        envois.setdefault(at, {})[int(charge.get("lot") or 1)] = charge

    if not envois:
        return [], 0
    at = max(envois)
    lots = envois[at]
    attendus = max((c.get("lots") or 1) for c in lots.values())
    if len(lots) < attendus:
        # envoi incomplet : mieux vaut ne rien ranger que ranger la moitié
        # d'une liste et croire que le reste a disparu
        return [], 0
    lignes = []
    for i in sorted(lots):
        lignes.extend(lots[i].get("c") or [])
    return lignes, at


# ----------------------------------------------------------------------
# 2. le délai de fabrication
# ----------------------------------------------------------------------

def machines_par_famille(machines, famille_de):
    compte = {}
    for m in machines or []:
        f = famille_de(m)
        compte[f] = compte.get(f, 0) + 1
    return compte


def delai(commandes, index, machines, famille_de, marge=0):
    """Combien de jours avant qu'une nouvelle commande puisse sortir.

    Le temps qui reste se répartit sur les machines de sa famille : deux
    K2 sortent deux fois plus vite qu'une. Les deux familles travaillent
    en parallèle, donc c'est la plus chargée qui donne le délai, pas la
    somme. Les machines tournent jour et nuit.

    Renvoie de quoi comprendre le chiffre, pas seulement le chiffre."""
    par_numero = {}
    for c in (index or {}).get("commandes") or []:
        n = c.get("numero") or numero(c.get("nom"))
        if n:
            par_numero[n] = c

    minutes = {}
    retenues, sans_fichier = [], []
    for cmd in commandes:
        n = cmd.get("numero") or numero(cmd.get("r"))
        fiche = par_numero.get(n) if n else None
        if not fiche:
            sans_fichier.append(cmd.get("r"))
            continue
        pris = False
        for fam, v in (fiche.get("par_famille") or {}).items():
            m = int(v.get("minutes_reste") or 0)
            if m > 0:
                minutes[fam] = minutes.get(fam, 0) + m
                pris = True
        if pris:
            retenues.append(cmd.get("r"))

    compte = machines_par_famille(machines, famille_de)
    heures = {}
    for fam, m in minutes.items():
        n = max(1, compte.get(fam, 1))
        heures[fam] = (m / 60.0) / n

    pire = max(heures.values()) if heures else 0.0
    jours = int(math.ceil(pire / 24.0)) + max(0, int(marge or 0))
    return {
        "jours": jours,
        "heures": round(pire, 1),
        "par_famille": {f: round(h, 1) for f, h in heures.items()},
        "machines": compte,
        "marge": max(0, int(marge or 0)),
        "commandes": len(retenues),
        "sans_fichier": sans_fichier[:10],
    }


# ----------------------------------------------------------------------
# 3. l'écriture dans la boutique
# ----------------------------------------------------------------------

ESPACE = "nmt"

MUTATION = """mutation p($m:[MetafieldsSetInput!]!){
  metafieldsSet(metafields:$m){ userErrors{ field message } }
}"""


def _message_http(e):
    """Ce que Shopify a mis dans le corps d'une réponse d'erreur."""
    try:
        charge = json.loads(e.read().decode("utf-8", "replace"))
    except Exception:
        return getattr(e, "reason", "") or "pas de détail"
    if isinstance(charge.get("errors"), str):
        return charge["errors"]
    if isinstance(charge.get("errors"), list):
        return "; ".join(str(x.get("message") or x) for x in charge["errors"])[:200]
    return json.dumps(charge, ensure_ascii=False)[:200]


class Boutique:
    """Le minimum pour écrire quelques metafields sur la boutique.

    On ne lit l'identifiant de la boutique qu'une fois : il ne change
    jamais, et c'est un aller-retour de moins à chaque envoi."""

    def __init__(self, domaine, jeton, version="2026-04"):
        self.domaine = str(domaine or "").replace("https://", "").replace("http://", "").strip("/")
        self.jeton = jeton or ""
        self.version = version or "2026-04"
        self._id = None

    def prete(self):
        # « A-REMPLIR » est ce que l'installeur écrit : tant qu'il est là, le
        # relais calcule le délai sans essayer de l'envoyer. Mieux vaut un
        # journal clair qu'une erreur d'authentification toutes les heures.
        return bool(self.domaine and self.jeton
                    and "A-REMPLIR" not in self.jeton
                    and "CHANGEMOI" not in self.jeton)

    def pourquoi_pas(self):
        """Pourquoi elle n'est pas prête, en nommant la clé à remplir."""
        if not self.domaine:
            return "shopify.domaine est vide dans relais.json"
        if not self.jeton:
            return "shopify.jeton est vide dans relais.json"
        if not self.prete():
            return ("shopify.jeton est resté à A-REMPLIR dans relais.json "
                    "(voir relais/README.md)")
        return ""

    def _appel(self, requete, variables=None, delai=20):
        url = "%s://%s/admin/api/%s/graphql.json" % (PROTOCOLE, self.domaine, self.version)
        corps = json.dumps({"query": requete, "variables": variables or {}},
                           ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=corps, method="POST")
        req.add_header("X-Shopify-Access-Token", self.jeton)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=delai) as rep:
                charge = json.loads(rep.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            # Un 401 ou un 403 ne veut dire qu'une chose : le jeton. Le code
            # seul n'aide personne, alors on rend ce que Shopify a écrit et
            # on nomme la cause probable.
            raise ValueError("Shopify a répondu %d : %s%s"
                             % (e.code, _message_http(e),
                                " — le jeton d'écriture est-il bon, et a-t-il "
                                "le droit write_shop_metafields ?"
                                if e.code in (401, 403) else ""))
        if charge.get("errors"):
            raise ValueError("Shopify a refusé : %s"
                             % json.dumps(charge["errors"], ensure_ascii=False)[:200])
        return charge.get("data") or {}

    def identifiant(self):
        if not self._id:
            self._id = ((self._appel("{shop{id}}").get("shop") or {}).get("id") or "")
        return self._id

    def ecrire(self, valeurs):
        """valeurs : {cle: (type, valeur)}. Renvoie la liste des clés écrites.

        « type » est celui du metafield côté Shopify : number_integer,
        date_time, boolean. Un type qui ne correspond pas à ce qui a été
        déclaré fait refuser l'écriture, et Shopify le dit."""
        oid = self.identifiant()
        if not oid:
            raise ValueError("boutique introuvable — le jeton a-t-il le droit de lire ?")
        champs = [{"ownerId": oid, "namespace": ESPACE, "key": cle,
                   "type": genre, "value": str(valeur)}
                  for cle, (genre, valeur) in sorted(valeurs.items())]
        data = self._appel(MUTATION, {"m": champs})
        erreurs = ((data.get("metafieldsSet") or {}).get("userErrors") or [])
        if erreurs:
            raise ValueError("; ".join(
                "%s : %s" % (".".join(str(x) for x in (e.get("field") or [])),
                             e.get("message"))
                for e in erreurs)[:300])
        return [c["key"] for c in champs]


class Vitrine:
    """Ce que la boutique affiche, et quand on le lui a dit.

    Réécrire un metafield à l'identique ne sert à rien, et consomme du
    quota : on garde la dernière valeur envoyée et on ne repart que sur un
    changement.

    Les deux valeurs n'ont pas la même urgence. Le délai de fabrication est
    recalculé tout seul et part une fois par heure. Le statut peinture, lui,
    est une décision prise à la main : quand il la prend, la boutique doit
    le dire tout de suite, pas dans cinquante-neuf minutes. D'où deux
    cadences, avec un plancher quand même, pour qu'un doigt qui hésite sur
    l'interrupteur ne fasse pas dix écritures."""

    PERIODE = 3600       # le délai de fabrication : une fois par heure
    MINIMUM = 300        # le statut peinture : vite, mais pas dix fois

    CADENCES = {
        "lead_time_days": PERIODE,
        "painting_open": MINIMUM,
        "painting_lead_time_days": MINIMUM,
    }

    def __init__(self, chemin):
        self.chemin = chemin
        self._cache = None

    def etat(self):
        with VERROU:
            if self._cache is None:
                try:
                    with open(self.chemin, encoding="utf-8") as f:
                        self._cache = json.load(f)
                except Exception:
                    self._cache = {}
                self._cache.setdefault("envoye", {})
                self._cache.setdefault("at", 0)
                self._cache.setdefault("peinture", {"ouverte": True, "jours": 0})
                self._cache.setdefault("marge", 0)
            return self._cache

    def _ecrire(self, etat):
        with VERROU:
            self._cache = etat
            provisoire = self.chemin + ".tmp"
            with open(provisoire, "w", encoding="utf-8") as f:
                json.dump(etat, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(provisoire, self.chemin)

    def regler(self, peinture_ouverte=None, peinture_jours=None, marge=None):
        """Ce que l'app décide : le statut peinture et la marge."""
        etat = dict(self.etat())
        etat["peinture"] = dict(etat["peinture"])
        if peinture_ouverte is not None:
            etat["peinture"]["ouverte"] = bool(peinture_ouverte)
        if peinture_jours is not None:
            etat["peinture"]["jours"] = max(0, int(peinture_jours))
        if marge is not None:
            etat["marge"] = max(0, int(marge))
        self._ecrire(etat)
        return etat

    def a_envoyer(self, jours):
        """Les valeurs du moment, prêtes pour Shopify."""
        p = self.etat()["peinture"]
        return {
            "lead_time_days": ("number_integer", int(jours)),
            "painting_open": ("boolean", "true" if p.get("ouverte") else "false"),
            "painting_lead_time_days": ("number_integer", int(p.get("jours") or 0)),
        }

    def faut_envoyer(self, valeurs, maintenant=None):
        """(oui, pourquoi). Seulement si ça bouge, et pas plus souvent que
        ce que la valeur la plus pressée de celles qui ont bougé autorise."""
        etat = self.etat()
        maintenant = maintenant if maintenant is not None else time.time()
        depuis = maintenant - float(etat.get("at") or 0)
        avant = etat.get("envoye") or {}
        apres = {k: str(v[1]) for k, v in valeurs.items()}
        bouges = [k for k in sorted(apres) if avant.get(k) != apres[k]]
        if not bouges:
            return False, "rien n'a changé"
        attendu = min(self.CADENCES.get(k, self.PERIODE) for k in bouges)
        if depuis < attendu:
            return False, ("%s a changé, envoi dans %d min"
                           % (", ".join(bouges),
                              int((attendu - depuis) // 60) + 1))
        return True, ("premier envoi" if not avant
                      else "changement : " + ", ".join(
                          "%s %s→%s" % (k, avant.get(k, "—"), apres[k])
                          for k in bouges))

    def noter_envoi(self, valeurs, maintenant=None):
        etat = dict(self.etat())
        etat["envoye"] = {k: str(v[1]) for k, v in valeurs.items()}
        etat["at"] = maintenant if maintenant is not None else time.time()
        self._ecrire(etat)


def horodatage(maintenant=None):
    """Le format que Shopify attend pour un date_time : ISO 8601, UTC."""
    t = maintenant if maintenant is not None else time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
