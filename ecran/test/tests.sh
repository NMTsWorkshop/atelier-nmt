#!/bin/sh
# Tout ce qu'on peut prouver du firmware de l'ecran sans brancher l'ecran.
#   sh test/tests.sh
set -e
cd "$(dirname "$0")"

AJ=stubs/ArduinoJson.h
if [ ! -f "$AJ" ]; then
  echo "Recuperation d'ArduinoJson (en-tete unique, une seule fois)..."
  curl -sSL -o "$AJ" \
    https://github.com/bblanchon/ArduinoJson/releases/download/v7.2.0/ArduinoJson-v7.2.0.h
fi

echo ""
echo "### La logique : durees, heures de fin, fraicheur, etats"
g++ -std=c++17 -I ../src modele_test.cpp -o /tmp/nmt_modele_test
/tmp/nmt_modele_test

echo "### La lecture du serveur"
g++ -std=c++17 -I stubs -I ../src lecture_test.cpp -o /tmp/nmt_lecture_test
/tmp/nmt_lecture_test

echo "### La vue, relue contre les signatures de LVGL 9.3"
g++ -std=c++17 -fsyntax-only -I stubs -I ../src vue_syntaxe.cpp
echo "  ok   tous les appels LVGL existent avec ces signatures"
echo ""
echo "Rien d'autre ne se verifie d'ici : l'affichage lui-meme se juge"
echo "sur l'ecran, en le regardant."
echo ""
