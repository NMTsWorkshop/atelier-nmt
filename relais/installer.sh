#!/bin/bash
# Installe le relais de l'atelier sur un Raspberry Pi fraîchement démarré.
#
#   curl -fsSLO https://raw.githubusercontent.com/NMTsWorkshop/atelier-nmt/main/relais/installer.sh
#   bash installer.sh
#
# Ne touche à rien d'autre que /opt/relais-atelier et à son service systemd.
# Si relais.json existe déjà, il est laissé tel quel : relancer l'installeur
# met seulement le programme à jour.

set -e

BASE="https://raw.githubusercontent.com/NMTsWorkshop/atelier-nmt/main/relais"
DOSSIER="/opt/relais-atelier"

echo
echo "=== Relais de l'atelier — installation ==="
echo

# --- vérifications qui évitent de chercher longtemps plus tard ---------------

command -v python3 >/dev/null || { echo "python3 manquant."; exit 1; }
command -v curl    >/dev/null || { echo "curl manquant : sudo apt install -y curl"; exit 1; }

annee=$(date +%Y)
if [ "$annee" -lt 2025 ]; then
  echo "ATTENTION : la date du Pi est fausse ($(date))."
  echo "Le Pi n'a pas d'horloge sauvegardée et remet l'heure par NTP au démarrage."
  echo "Tant qu'elle est fausse, HTTPS refuse tous les certificats et le relais"
  echo "ne pourra rien publier. Vérifie que le sortant UDP 123 passe le firewall."
  echo
fi

# --- programme et service ---------------------------------------------------

sudo mkdir -p "$DOSSIER"
sudo curl -fsSL "$BASE/relais_atelier.py" -o "$DOSSIER/relais_atelier.py"
sudo curl -fsSL "$BASE/relais-atelier.service" -o /etc/systemd/system/relais-atelier@.service
sudo chown -R "$USER:$USER" "$DOSSIER"
echo "Programme installé dans $DOSSIER."

# --- réglages ---------------------------------------------------------------

if [ -f "$DOSSIER/relais.json" ]; then
  echo "relais.json existe déjà, je n'y touche pas."
else
  cat > "$DOSSIER/relais.json" <<'JSON'
{
  "sujet": "A-REMPLIR",
  "periode": 60,
  "machines": [
    { "nom": "K2 Plus",    "type": "moonraker", "hote": "10.1.3.3" },
    { "nom": "Creality 2", "type": "moonraker", "hote": "10.1.3.2" },
    { "nom": "Bambu 1",    "type": "bambu", "hote": "10.1.3.11",
      "serie": "01P00C462500170", "code": "A-REMPLIR" },
    { "nom": "Bambu 2",    "type": "bambu", "hote": "10.1.3.10",
      "serie": "01P09C510800409", "code": "A-REMPLIR" }
  ]
}
JSON
  chmod 600 "$DOSSIER/relais.json"
  echo "relais.json créé avec le parc. Trois valeurs restent à remplir."
fi

echo
echo "=== Reste à faire, à la main ==="
echo
echo "1. Remplir les trois A-REMPLIR :"
echo "     nano $DOSSIER/relais.json"
echo "   - sujet : le même que dans l'app, Réglages > Relais de l'atelier"
echo "   - code  : le code d'accès LAN de chaque Bambu, lu sur son écran"
echo
echo "2. Essayer un relevé :"
echo "     python3 $DOSSIER/relais_atelier.py --une-fois"
echo
echo "3. Le lancer en permanence :"
echo "     sudo systemctl enable --now relais-atelier@$USER"
echo "     journalctl -u relais-atelier@$USER -f"
echo
