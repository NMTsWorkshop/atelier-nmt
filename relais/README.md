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
| `marge_delai` | jours ajoutés au délai calculé (0 par défaut)                  |
| `shopify`  | `domaine`, `jeton` d'écriture, `version` de l'API Admin           |

Une machine Bambu demande en plus `serie` (numéro de série) et `code`
(code d'accès LAN, visible sur l'écran de la machine).

Le `sujet` sert de mot de passe : qui le connaît peut lire le relevé, et publier
un faux relevé. Prends une suite de lettres et de chiffres d'au moins 20
caractères, et ne la publie nulle part.

---

# Délai de fabrication publié dans la boutique

Le relais sait ce qu'il reste à imprimer : la bibliothèque lit le temps et le
poids dans chaque fichier tranché, et l'app lui publie la liste des commandes.
Il en tire un délai en jours et l'écrit dans la boutique, pour que la fiche
produit l'affiche sans que personne ait à y penser.

## Le calcul

1. Chaque fichier d'une commande donne son temps d'impression, multiplié par le
   nombre d'exemplaires qui restent à sortir.
2. Les temps s'additionnent **par famille de machines** : ce qui reste sur les
   K2 n'attend pas ce qui reste sur les Bambu.
3. Chaque total se divise par le nombre de machines de la famille — deux K2
   sortent deux fois plus vite qu'une.
4. Les deux familles travaillent en parallèle : c'est **la plus chargée** qui
   donne le délai, pas la somme. Les machines tournent jour et nuit, donc
   `jours = arrondi supérieur (heures / 24)`.
5. `marge_delai` ajoute des jours de sécurité (0 par défaut). L'app peut la
   changer depuis les réglages, elle est gardée sur le Pi.

Une commande marquée expédiée dans l'app ne compte plus. Une commande dont
aucun fichier n'est dans la bibliothèque ne compte pas non plus : elle est
nommée dans le journal pour qu'on sache ce qui manque.

## Ce qu'il écrit

Quatre metafields sur la boutique elle-même (propriétaire `Shop`), dans
l'espace de noms `nmt` :

| clé                       | type             | contenu                        |
|---------------------------|------------------|--------------------------------|
| `lead_time_days`          | `number_integer` | le délai calculé, en jours     |
| `lead_time_updated_at`    | `date_time`      | quand il a été écrit (UTC)     |
| `painting_open`           | `boolean`        | la peinture est-elle ouverte   |
| `painting_lead_time_days` | `number_integer` | le délai de peinture, en jours |

**Une fois par heure, et seulement si une valeur a changé.** Réécrire un
metafield à l'identique ne sert à rien et consomme du quota ; l'horodatage, lui,
ne compte pas comme un changement, sinon il provoquerait l'envoi qu'il est censé
seulement dater.

Les définitions de ces quatre metafields existent déjà côté boutique, avec ces
types exacts. Le relais n'y touche pas, et ne touche pas au thème.

## Le jeton d'écriture

Il vit sur le Pi, dans `relais.json`, et nulle part ailleurs. Celui de l'app ne
sait que lire les commandes : un téléphone perdu ne doit pas emporter le droit
d'écrire dans la boutique.

Pour le créer, dans l'admin Shopify :

1. **Paramètres → Applications et canaux de vente → Développer des
   applications → Créer une application**. L'appeler par exemple
   `Relais de l'atelier`.
2. **Configurer les champs d'application de l'API Admin**. Cocher
   `write_content` : c'est lui qui ouvre les metafields de la boutique. Rien
   d'autre n'est nécessaire — le relais n'a besoin ni de lire les commandes
   (l'app le lui dit), ni de toucher aux produits.
3. **Installer l'application**, puis **Identifiants de l'API → Jeton d'accès
   de l'API Admin → Révéler**. Il ne s'affiche qu'une fois.
4. Le poser sur le Pi, et nulle part ailleurs :

   ```
   nano /opt/relais-atelier/relais.json
   ```

   ```json
   "shopify": {
     "domaine": "xxxxxx.myshopify.com",
     "jeton": "shpat_...",
     "version": "2026-04"
   }
   ```

   Le `domaine` est l'adresse `.myshopify.com` de la boutique, pas le nom de
   domaine du site.

5. Essayer :

   ```
   python3 /opt/relais-atelier/relais_atelier.py --une-fois
   ```

   La ligne `boutique prévenue : délai N j` dit que c'est passé. Si Shopify
   refuse, son message est rendu tel quel — il nomme lui-même le droit qui
   manque, et il suffit de le cocher puis de relancer.

Tant que `shopify.jeton` est resté à `A-REMPLIR`, le relais calcule le délai et
le note dans son journal sans rien envoyer. Rien ne casse, rien ne part.

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

## Quand une Bambu refuse un fichier

`bambu_diag.py`, installé à côté du relais, teste chaque Bambu étape par
étape et sépare les causes que « The read operation timed out » confond :

    python3 /opt/relais-atelier/bambu_diag.py

1. le port 990 répond-il (sinon : mode LAN à activer sur l'écran)
2. le code d'accès LAN est-il renseigné dans `relais.json`
3. la poignée de main TLS passe-t-elle, en strict puis en assoupli
4. l'identification est-elle acceptée
5. quel port de données la machine annonce-t-elle
6. ce port est-il joignable depuis le Pi — **s'il ne l'est pas, c'est le
   pare-feu** : le canal de contrôle FTPS étant chiffré, l'assistant FTP
   du pare-feu ne peut pas lire la réponse PASV et ne sait donc pas quel
   port ouvrir
7. la carte se lit-elle vraiment
