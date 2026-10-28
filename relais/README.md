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

## La lumière de chambre des machines

Sur une Bambu, c'est une commande du firmware (`ledctrl`) en MQTT local. Sur
une Creality, c'est une broche de sortie Klipper — et son nom change d'une
machine et d'une configuration à l'autre. Le relais ne le devine pas : il
demande à Klipper la liste de ses objets et prend celui qui ressemble à un
éclairage (`output_pin caselight` et compagnie). Une machine dont la
configuration n'en déclare aucun le dit, au lieu d'avoir l'air de marcher.

À l'atelier l'ordre passe en direct et la lumière s'allume quand on appuie ;
ailleurs il passe par le canal et s'applique à la relève suivante.

Les ordres partent **une machine après l'autre**, jamais les quatre d'un
coup. Chaque ordre Bambu ouvre une session MQTT, et une P1S n'en accepte
qu'un petit nombre à la fois : quatre connexions simultanées et elle
décroche.

## Le courant des machines : abandonné, et pourquoi

Le relais a piloté le courant des machines par multiprises Meross, en local.
Ça n'existe plus — ni dans le relais, ni dans l'app.

Ces multiprises lâchent leurs relais sous l'appel de courant d'un plateau
chauffant qui démarre. Une seule machine suffit : au nivelage, la protection
déclenche, on entend les relais claquer, le symbole d'alimentation clignote,
et la machine s'arrête. Parfois c'est toute la multiprise qui tombe, et les
quatre machines avec. Rien à voir avec le logiciel : la même impression
passe sans broncher dès que la machine est branchée ailleurs.

Les imprimantes sont donc sur une alimentation sans électronique. Les
multiprises Meross restent en service pour le Pi, le switch et la borne
Wi-Fi — quelques watts, aucun appel de courant, c'est ce pour quoi elles
sont faites.

Le code qui les commandait est dans l'historique git, à `4.9` : le protocole
local Meross, la récupération de la clé du compte, le verrou par défaut, la
validation par notification. Si le besoin revient, il faudra le reprendre là
— mais la bonne réponse sera plutôt un redémarrage **logiciel**, par
Moonraker pour les Creality et MQTT pour les Bambu, sans toucher au courant.

Ce qu'on en garde, et qui vaut pour tout le reste :

- **Un ordre déjà exécuté ne se rejoue pas.** La liste vit sur le disque, pas
  seulement en mémoire. Un soir de mises à jour, elle ne vivait qu'en
  mémoire, et chaque redémarrage du relais rejouait les coupures de courant
  sur des machines en train d'imprimer.
- **Aucun ordre physique n'est exécuté pendant le rattrapage de démarrage.**
  Le relais relit deux heures d'ordres en démarrant, pour ne pas perdre un
  plateau coché ou un fichier envoyé. Les ordres qui agissent sur le
  matériel — l'éclairage, le lancement d'une impression, les gestes sur le
  Pi — sont écartés et refusés à voix haute, pour que l'app le dise.


## Remettre le Pi d'aplomb depuis l'app

Le symptôme le plus courant n'est pas une panne : le Pi est allumé, il répond,
mais le partage de fichiers ne montre plus rien depuis Windows. Couper le
courant réglerait ça — c'est aussi le seul geste qu'on ne peut pas annuler à
distance, et il tombe à l'aveugle sur un disque qui écrit peut-être.

Réglages → **Le Pi** montre l'état du partage et depuis combien de temps la
machine est debout, et propose trois gestes, du plus doux au plus brutal :

| geste | ce qu'il fait | quand |
|---|---|---|
| Relancer le partage | `systemctl restart smbd` | les fichiers ne sont plus visibles depuis Windows |
| Relancer le relais | le service sort, systemd le relance | le relevé est figé ou la bibliothèque ne répond plus |
| Redémarrer le Pi | `systemctl reboot` | plus rien ne répond |

Les deux derniers coupent le relais, et c'est lui qui répond à l'app :
l'accusé de réception part donc **avant** le geste. Sans ça l'app conclurait
au silence et annoncerait que l'ordre n'est pas passé, alors qu'il l'est.

Un transfert en cours fait refuser les deux gestes lourds — l'app propose
alors de forcer. Le relais n'a besoin d'aucun droit particulier pour se
relancer lui-même (son service est en `Restart=always`) ; les deux autres
gestes passent par `sudo`, sur la règle posée par `pi-13-sans-mdp.bat`, qui
n'autorise que ces commandes-là.

Ces gestes voyagent par le canal, signés comme les autres ordres. Qui connaît
à la fois le sujet et le jeton peut donc redémarrer le Pi — c'est le même
niveau d'accès que celui qui permet déjà d'envoyer un fichier sur une machine
et de lancer une impression.

## Un ordre exécuté le reste

Le relais relit deux heures d'ordres au démarrage : sans ça, un plateau coché
pendant qu'il redémarrait serait perdu. Mais la liste de ce qu'il avait déjà
fait ne vivait qu'en mémoire — vide après un redémarrage. Un soir de mises à
jour, il a rejoué des coupures de courant sur des machines en train
d'imprimer, à chaque relance.

Cette liste est maintenant sur le disque, à côté de la bibliothèque
(`ordres_vus.json`). Et les ordres qui agissent sur le monde physique — le
courant, le redémarrage du Pi, l'éclairage, le démarrage d'une impression —
ont une fenêtre de dix minutes au lieu de deux heures : passé ce délai,
personne ne les attend plus, et les exécuter serait une surprise. Cocher un
plateau garde sa fenêtre large, puisque rien n'y est dangereux.

## Vérifier le relais sans y toucher

Trois tests tournent sans Pi ni imprimante, et à chaque envoi sur GitHub :

```
python3 test/demarrage.py      # le relais démarre et publie
python3 test/bout_en_bout.py   # la chaîne entière, contre de fausses machines
node test/smoke.js             # l'interface, dans un navigateur
```

Le deuxième monte un faux ntfy, un faux Moonraker, un faux Bambu (FTP et MQTT)
et une fausse boutique Shopify, puis fait tourner la vraie boucle du relais
contre eux.

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
