#!/bin/bash
# Installe le relais de l'atelier sur un Raspberry Pi fraîchement démarré.
#
#   curl -fsSLO https://raw.githubusercontent.com/NMTsWorkshop/atelier-nmt/main/relais/installer.sh
#   bash installer.sh
#
# Ne touche à rien d'autre que /opt/relais-atelier et à son service systemd.
# Si relais.json existe déjà, ses valeurs sont gardées : relancer l'installeur
# met le programme à jour et ajoute seulement les réglages qui manquent.

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
sudo curl -fsSL "$BASE/biblio.py" -o "$DOSSIER/biblio.py"
sudo curl -fsSL "$BASE/bambu_diag.py" -o "$DOSSIER/bambu_diag.py"
sudo curl -fsSL "$BASE/relais-atelier.service" -o /etc/systemd/system/relais-atelier@.service
sudo systemctl daemon-reload
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
    { "nom": "K2 Plus 1", "type": "moonraker", "hote": "10.1.2.57" },
    { "nom": "K2 Plus 2", "type": "moonraker", "hote": "10.1.2.59" },
    { "nom": "P1S 1",     "type": "bambu", "hote": "10.1.3.10",
      "serie": "01P09C510800409", "code": "A-REMPLIR" },
    { "nom": "P1S 2",     "type": "bambu", "hote": "10.1.3.11",
      "serie": "01P00C462500170", "code": "A-REMPLIR" }
  ]
}
JSON
  chmod 600 "$DOSSIER/relais.json"
  echo "relais.json créé avec le parc. Trois valeurs restent à remplir."
fi

echo
# --- bibliothèque de gcodes -------------------------------------------------
#
# Les réglages qui manquent sont ajoutés sans toucher aux autres : un relais
# déjà configuré garde son sujet et ses codes d'accès.

python3 - "$DOSSIER" <<'REGLAGES'
import json, os, secrets, sys

dossier = sys.argv[1]
chemin = os.path.join(dossier, "relais.json")
with open(chemin, encoding="utf-8-sig") as f:
    c = json.load(f)

ajouts = []
if not c.get("biblio"):
    c["biblio"] = os.path.join(dossier, "gcodes")
    ajouts.append("biblio")
if not c.get("port_api"):
    c["port_api"] = 8765
    ajouts.append("port_api")
if not c.get("jeton"):
    c["jeton"] = secrets.token_urlsafe(18)
    ajouts.append("jeton")

if ajouts:
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    print("relais.json complete : " + ", ".join(ajouts))
else:
    print("relais.json a deja tout ce qu'il faut.")

racine = c["biblio"]
for m in c.get("machines") or []:
    f = (m.get("famille") or ("k2" if m.get("type") == "moonraker" else "p1s")).lower()
    os.makedirs(os.path.join(racine, f), exist_ok=True)
print("Bibliotheque : " + racine)
REGLAGES

chmod 600 "$DOSSIER/relais.json"

lire_reglage() {
  python3 -c "import json,io;print(json.load(io.open('$DOSSIER/relais.json',encoding='utf-8-sig')).get('$1',''))"
}

RACINE=$(lire_reglage biblio)
ADRESSE=$(hostname -I | awk '{print $1}')

# --- partage réseau, pour déposer les gcodes depuis le PC -------------------
#
# Sans lui, il faudrait copier chaque fichier en ligne de commande. Avec, la
# bibliothèque s'ouvre comme un lecteur réseau depuis Windows et on y
# enregistre directement depuis le trancheur.

if [ "${1:-}" = "--sans-partage" ]; then
  echo "Partage réseau laissé de côté."
elif grep -q "^\[gcodes\]" /etc/samba/smb.conf 2>/dev/null; then
  echo "Partage réseau déjà en place."
else
  echo
  echo "Le partage réseau permet d'enregistrer un fichier tranché depuis le PC"
  echo "directement dans la bibliothèque, comme sur un lecteur réseau."
  printf "L'installer ? [O/n] "
  read -r reponse </dev/tty 2>/dev/null || reponse="n"
  case "$reponse" in
    [nN]*) echo "Partage laissé de côté." ;;
    *)
      sudo apt-get install -y samba >/dev/null
      sudo tee -a /etc/samba/smb.conf >/dev/null <<SAMBA

[gcodes]
   comment = Bibliotheque de gcodes de l'atelier
   path = $RACINE
   browseable = yes
   read only = no
   guest ok = no
   valid users = $USER
   create mask = 0664
   directory mask = 0775
SAMBA
      echo
      echo "Choisis le mot de passe que le PC demandera pour ce partage :"
      sudo smbpasswd -a "$USER"
      sudo systemctl restart smbd
      echo "Partage prêt. Depuis Windows : \\\\$ADRESSE\\gcodes"
      ;;
  esac
fi

echo
if grep -q "A-REMPLIR" "$DOSSIER/relais.json"; then
  echo "=== Reste à faire, à la main ==="
  echo
  echo "1. Remplir les A-REMPLIR :"
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
else
  echo "=== Relais déjà configuré ==="
  echo
  echo "Rien à remplir. Pour prendre en compte cette mise à jour :"
  echo "     sudo systemctl restart relais-atelier@$USER"
  echo
fi

echo "Dans l'app, Réglages > Bibliothèque de gcodes :"
echo "     adresse : $ADRESSE"
echo "     jeton   : $(lire_reglage jeton)"
echo
echo "Déposer les fichiers tranchés dans $RACINE :"
echo "   k2  pour les Creality, p1s pour les Bambu,"
echo "   un sous-dossier par commande à l'intérieur."
echo
