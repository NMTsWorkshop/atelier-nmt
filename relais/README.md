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
