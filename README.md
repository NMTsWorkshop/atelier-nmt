# Atelier NMT

Application Android pour piloter le parc d'imprimantes : machines et filament chargé,
stock de bobines, commandes Shopify avec calcul du filament nécessaire, et surtout
des timers par machine avec une vraie notification quand l'impression est finie.

Les notifications passent par `AlarmManager.setAlarmClock()`, le seul mode de réveil
qu'Android ne repousse jamais, même en veille profonde. C'est ce qui manque aux apps
Bambu et Creality.

---

## 1. Obtenir l'APK

**Après la première installation, tu n'as plus rien à faire ici** : l'app se met
à jour toute seule. Réglages → Rechercher une mise à jour, ou elle vérifie
d'elle-même une fois par jour et te propose d'installer.

### Par GitHub (rien à installer)

1. Crée un dépôt sur github.com (privé, peu importe le nom).
2. Envoie le contenu de ce dossier dedans — par glisser-déposer dans
   « uploading an existing file », ou en ligne de commande :
   ```bash
   git init && git add . && git commit -m "Atelier NMT"
   git branch -M main
   git remote add origin https://github.com/<toi>/<depot>.git
   git push -u origin main
   ```
3. Onglet **Actions** du dépôt : la compilation démarre toute seule et dure
   trois à quatre minutes.
4. L'APK arrive à deux endroits — la page **Releases** du dépôt (lien direct,
   pratique depuis le téléphone), et en pièce jointe du build dans Actions.
5. Sur le téléphone, ouvre le fichier et autorise l'installation depuis cette source.

À chaque modification que tu pousses, un nouvel APK est compilé automatiquement.

### Par Android Studio

Ouvre le dossier, laisse la synchronisation Gradle se faire, puis
`Build → Build Bundle(s)/APK(s) → Build APK(s)`. Le projet n'embarque pas de
wrapper Gradle : Android Studio proposera d'utiliser sa propre version, accepte.

---

## 2. Premier démarrage sur le téléphone

Trois réglages à faire une fois, sinon les notifications arrivent en retard :

- **Notifications** : l'app les demande au lancement, accepte.
- **Alarmes précises** : si un bandeau d'alerte apparaît sur l'écran Machines,
  appuie dessus et autorise.
- **Batterie** : Réglages → Applications → Atelier NMT → Batterie → **Sans
  restriction**. Le raccourci est aussi dans l'onglet Réglages de l'app.
  Sur Samsung, vérifie en plus que l'app n'est pas dans « Applications en veille ».

Ensuite : Réglages → **Tester** les notifications. Une alerte tombe une minute
plus tard ; verrouille l'écran en attendant, c'est le vrai test.

---

## 3. Connecter Shopify

Dans l'admin Shopify : **Paramètres → Applications et canaux de vente →
Développer des applications → Créer une application**.

- Configuration → **Admin API** → autorisation `read_orders` (seule requise).
- Installer l'application, puis révéler le **jeton d'accès Admin API** (`shpat_…`).

Dans l'app, onglet Réglages :

| Champ | Valeur |
|---|---|
| Domaine myshopify | `ta-boutique.myshopify.com` |
| Jeton | le `shpat_…` |
| Version d'API | `2026-04` |

**Tester** doit répondre « Connecté à NMT's Workshop ».

Le jeton ne quitte jamais le téléphone : les requêtes partent directement de
l'appareil vers Shopify. `read_orders` donne accès aux commandes des 60 derniers
jours, ce qui couvre largement la file de production.

Ce jeton-là ne sait que **lire**. Celui qui écrit le délai de fabrication dans
la boutique est un second jeton, qui vit sur le Pi et pas sur le téléphone :
voir `relais/README.md`, « le jeton d'écriture ».

---

## 4. Au quotidien

**Machines** — une carte par imprimante. « Lancer une impression » démarre un
timer (raccourcis 30 min à 12 h, ou saisie libre) et permet de rattacher la
pièce à une ligne de commande. Le compte à rebours tourne, `+15 min` rattrape
un décalage, « Terminer » libère la machine et déduit le filament consommé.
Appuie sur l'en-tête d'une carte pour renommer la machine ou la supprimer.

**Stock** — une fiche par **référence** (marque + matière + couleur), pas par
bobine : tu indiques le nombre de bobines neuves en réserve et ce qui reste sur
celle qui est entamée. Un achat de 10 kg de noir, c'est donc une fiche avec
« 10 bobines neuves », pas dix saisies. Le niveau affiché concerne la bobine
entamée — Pleine, Entamée, Faible, Bientôt vide — et « Ajuster » permet de la
corriger à l'œil, de retirer 50 à 500 g, d'ajouter des bobines à la réserve ou
d'en ouvrir une neuve. Quand une impression épuise la bobine entamée, l'app
ouvre la suivante toute seule. « À racheter » n'apparaît que lorsqu'il n'y a
plus d'avance. En haut, un bloc récapitule ce que réclament les commandes en
cours et signale ce qui manque.

**Commandes** — le bouton Shopify récupère les commandes non expédiées, et
vérifie du même coup celles que l'app connaît déjà : une commande traitée dans
la boutique passe en « expédiée », ses lignes sont cochées, et elle ne pèse plus
sur le délai de fabrication. La matière est déduite du nom de la variante
(`Covert / Without Visor / PLA`), la couleur se saisit à la main. Le poids, lui,
est lu dans le fichier tranché quand la commande en a un dans la bibliothèque —
sinon il se saisit, et reste mémorisé par variante. Chaque commande affiche
« Stock OK », « Juste » ou « Manque ~320 g », et le temps qu'il reste à sortir.

**Délai annoncé dans la boutique** — Réglages → *Délai annoncé dans la
boutique*. Le relais additionne ce qu'il reste à imprimer, le répartit sur les
machines de chaque famille, et écrit le nombre de jours sur la boutique ; la
fiche produit l'affiche sans qu'on y pense. Le même écran porte le statut
peinture (ouverte ou fermée, et son délai) et une marge en jours. Le jeton qui
écrit dans la boutique vit sur le Pi, pas sur le téléphone : `relais/README.md`
explique comment le créer.

**Liaison réseau** — dans la fiche d'une machine, section Liaison réseau : la
marque, l'adresse IP, et pour une Bambu le numéro de série et le code d'accès
LAN. « Tester la liaison » répond tout de suite. Une fois branchée, l'app lit
l'avancement et le temps restant sur la machine elle-même, affiche les bobines
vues par l'AMS, et te notifie à la vraie fin d'impression — plus besoin de
saisir un timer. La relève tourne toutes les quinze minutes en arrière-plan,
sans notification permanente, et l'heure de fin est recalée à chaque passage.
Le bouton de synchronisation en haut de l'écran Machines force une relève.

Côté Bambu, **il n'est pas nécessaire de couper le cloud** : le MQTT local
répond avec le seul code d'accès, vérifié sur P1S. Le téléphone doit être sur
le même réseau que l'atelier.

**Profils** — tes réglages habituels : matière, couche, buse, remplissage,
températures, notes. Un profil peut être rattaché par défaut à une machine.

Tout est stocké sur le téléphone. Réglages → **Exporter** écrit une sauvegarde
JSON dans les Téléchargements ; **Importer** la relit.

---

## 5. Modifier l'app

```
web/                interface (HTML/CSS/JS, aucune dépendance)
  index.html
  css/app.css
  js/store.js       données, persistance, calculs de stock
  js/ui.js          feuilles modales, toasts, sélecteurs
  js/machines.js    parc et timers
  js/stock.js       bobines
  js/orders.js      commandes et synchro Shopify
  js/profiles.js    profils d'impression
  js/settings.js    réglages, sauvegarde
  js/app.js         navigation, horloges
app/                coque Android (Java, aucune dépendance)
  …/MainActivity.java   WebView + bouton retour
  …/Bridge.java         pont JS ↔ Android (alarmes, HTTP, fichiers)
  …/Timers.java         planification des alarmes
  …/AlarmReceiver.java  notification de fin
  …/BootReceiver.java   replanification après redémarrage
  …/Printers.java       lecture Moonraker et Bambu, format commun
  …/BambuClient.java    MQTT local, lecture seule
  …/Sync.java           relève périodique et recalage des alarmes
  …/Notifier.java       construction des notifications
  …/Updater.java        mise à jour depuis la page Releases
test/smoke.js       test de bout en bout de l'interface
```

Le dossier `web/` **est** le dossier `assets` de l'APK (voir `app/build.gradle`) :
modifier l'interface, c'est modifier ces fichiers, rien à recopier.

Pour travailler l'interface sans téléphone, ouvre `web/index.html` dans un
navigateur. Tout fonctionne sauf ce qui dépend d'Android : notifications et
synchro Shopify (bloquée par CORS hors de l'app). Le test de bout en bout :

```bash
npm i playwright && node test/smoke.js
```

---

## 6. Limites connues

- Les machines non branchées gardent le timer manuel : tu saisis la durée
  toi-même, comme avant.
- La relève exige d'être sur le Wi-Fi de l'atelier. Hors du réseau, l'app
  affiche la dernière valeur connue et la signale comme datée.
- Le stock est une estimation. Rien ne pèse les bobines à ta place : les
  bobines neuves sont comptées, l'entamée est estimée à l'œil.
- Les données vivent sur un seul téléphone ; la synchro entre appareils
  demanderait un serveur.
- Le délai publié dans la boutique ne compte que les commandes dont un fichier
  est rangé dans la bibliothèque. Les autres sont nommées sur l'écran des
  réglages, pour qu'on voie ce qui manque plutôt que de croire à un délai trop
  court. Une commande annulée dans Shopify, elle, continue de compter : il faut
  la passer en expédiée à la main.
- Allumer ou éteindre une machine à distance demande une prise commandée : une
  imprimante éteinte n'a plus de réseau, et rien ne peut la réveiller par
  l'adresse IP.
- APK signé avec la clé de debug : parfait pour un usage perso, à refaire avec
  une vraie clé pour une distribution publique.
