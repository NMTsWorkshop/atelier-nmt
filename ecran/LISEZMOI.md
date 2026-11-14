# L'ecran de l'atelier

Un Panda Touch (BigTreeTech, ESP32-S3, 800x480) accroche au mur, qui montre
l'etat des machines sans qu'on ait rien a toucher.

## Ce qu'il fait

Une page, pas de menu. Un bandeau en haut pour le serveur, une carte par
machine : nom, etat, fichier en cours, temps restant en gros, heure de fin,
avancement. Les machines qui demandent qu'on aille les voir — en pause,
en echec, terminees, injoignables — ont une bordure de couleur.

Un appui n'importe ou force une relecture.

## Ce qu'il ne fait pas

Il ne commande rien. C'est un moniteur.

Et il ne parle a aucune imprimante : il interroge `GET /etat` sur le
serveur, qui sait deja parler a chacune. Donc aucun code LAN Bambu sur
l'ecran, aucun protocole a maintenir ici, et le jour ou une marque casse
son API, c'est le serveur qu'on repare une seule fois.

## L'honnetete de l'affichage

Un moniteur qui a parfois tort est pire que pas de moniteur : on apprend a
ne plus le croire, et il devient de la decoration. D'ou deux regles tenues
dans tout le code :

- Quand une lecture date, l'ecran ecrit « lu il y a 14 min » a la place du
  fichier, et passe la machine en jaune. Il n'affiche jamais un chiffre
  vieux de vingt minutes comme s'il etait frais.
- Quand le serveur ne repond pas, il n'affiche aucun etat de machine. Pas
  le dernier connu, rien.

Une machine injoignable est en jaune, pas en rouge : ce n'est pas elle qui
a echoue, c'est nous qui ne savons pas.

## L'heure

Elle vient du serveur, pas d'un NTP. L'ecran n'a donc pas besoin d'Internet,
et il ne peut pas afficher une heure fausse faute de synchronisation. Le
fuseau de Lyon et sa regle d'heure d'ete sont dans `main.cpp`.

## Aucun secret dans le binaire

Ni le wifi, ni l'adresse du serveur, ni son jeton. Tout est demande au
premier demarrage, par un portail wifi, et garde dans la memoire de l'ecran.
Le binaire peut donc vivre dans un depot public sans precaution.

## Compiler et flasher

`ecran-flash.bat`, sur le PC. Il installe PlatformIO si besoin, clone le
support BigTreeTech a cote, compile et envoie par USB-C. Il sauvegarde la
flash d'origine avant la premiere ecriture.

## Tester la logique sans ecran

    sh test/tests.sh

Trois choses : les durees, heures de fin (passage de minuit et heure d'ete
compris), fraicheur et etats ; la lecture d'un vrai relevé de serveur, y
compris tronque, vide ou sans nom de machine ; et la vue, relue par le
compilateur contre les signatures de LVGL 9.3.

C'est tout ce qui se prouve sans l'ecran. L'affichage lui-meme se juge en
le regardant.
