# Relais de l'atelier

Un petit appareil resté allumé à l'atelier (Raspberry Pi) relève les imprimantes
toutes les minutes et publie leur état sur `ntfy.sh`. L'application Atelier NMT
lit ce relevé quand elle ne joint pas les machines elle-même : les infos
d'impression restent donc visibles en 4G, chez quelqu'un d'autre, partout.

## Ce que ça demande au réseau

- **Sortant uniquement**, en HTTPS (port 443), vers `ntfy.sh`.
- **Rien d'entrant** : aucun port à ouvrir sur la box, aucune redirection.
- Sur le réseau local : HTTP port 7125 vers les Creality, TLS port 8883 vers les
  Bambu. Le Pi doit être sur le même réseau que les imprimantes.

Aucune commande n'est envoyée aux machines : le relais est en lecture seule.

## Installation

```
sudo mkdir -p /opt/relais-atelier
sudo cp relais_atelier.py /opt/relais-atelier/
sudo cp relais.exemple.json /opt/relais-atelier/relais.json
sudo nano /opt/relais-atelier/relais.json     # sujet, machines, codes LAN
sudo chown -R $USER:$USER /opt/relais-atelier
sudo chmod 600 /opt/relais-atelier/relais.json

sudo cp relais-atelier.service /etc/systemd/system/relais-atelier@.service
sudo systemctl enable --now relais-atelier@$USER
```

Vérifier :

```
python3 /opt/relais-atelier/relais_atelier.py --une-fois   # un relevé, affiché
journalctl -u relais-atelier@$USER -f                      # le service en direct
```

## Réglages (`relais.json`)

| champ      | rôle                                                            |
|------------|-----------------------------------------------------------------|
| `sujet`    | nom secret du canal ntfy ; le même dans les réglages de l'app     |
| `periode`  | secondes entre deux relevés (60 par défaut, 30 minimum)           |
| `machines` | `type` = `moonraker` (Creality) ou `bambu` ; `hote` = adresse IP  |

Une machine Bambu demande en plus `serie` (numéro de série) et `code`
(code d'accès LAN, visible sur l'écran de la machine).

Le `sujet` sert de mot de passe : qui le connaît peut lire le relevé, et publier
un faux relevé. Prends une suite de lettres et de chiffres d'au moins 20
caractères, et ne la publie nulle part.

---

# Tableur de compta

`compta_xlsx.py` fait le trajet inverse : l'application publie ses commandes sur
le même canal, ce script les reprend et ajoute les lignes manquantes en bas de
la feuille **Compta** d'`Argent.xlsx`.

Il tourne sur le PC où vit le tableur — pas sur le Pi.

## Installation

```
python compta_xlsx.py            # crée compta.json puis s'arrête
```

Ouvrir `compta.json` :

```json
{
  "sujet": "le-même-sujet-que-le-relais",
  "tableur": "C:\\Users\\natha\\Documents\\Argent.xlsx",
  "feuille": "Compta"
}
```

Puis, dans l'app : Réglages → Tableur de compta → **Envoyer maintenant**, et sur
le PC :

```
python compta_xlsx.py --essai     # montre ce qui serait ajouté, n'écrit rien
python compta_xlsx.py             # ajoute pour de bon
```

Aucune bibliothèque à installer : Python seul suffit.

## Ce qu'il écrit, ce qu'il ne touche pas

| colonne | valeur |
|---------|--------|
| Date, Nom, Pays, Prix, Poids, Avancement, Objet | ce que dit l'app |
| Reçu | le prix pour une commande Shopify (payée d'avance), 0 pour une commande manuelle |
| Coup mat, Benef, Marge, Marge tot, Prix/kilo, A recevoir | la formule de la dernière ligne, recopiée |
| Réf (colonne X) | la référence de la commande — c'est elle qui évite les doublons |
| Platforme, Autre, Region | laissées vides, à toi de les remplir |

Une ligne déjà présente n'est **jamais** modifiée : si tu corriges un prix à la
main dans le tableur, ta correction reste. Relancer le script deux fois de suite
n'ajoute rien la seconde fois.

Le classeur contient des graphiques et des tableaux croisés dynamiques. Les
bibliothèques Excel habituelles les effacent en enregistrant, donc le script
écrit directement dans le XML du fichier : tout ce qu'il ne modifie pas ressort
octet pour octet identique. Une copie de l'état d'avant est déposée à côté, sous
le nom `Argent.xlsx.avant-compta`.

## Le canal n'est pas une mémoire

ntfy garde les messages une douzaine d'heures. L'app renvoie la liste complète à
chaque changement, donc un seul message récent suffit — mais si le PC reste
éteint plusieurs jours, il faut retoucher **Envoyer maintenant** dans l'app avant
de lancer le script.
