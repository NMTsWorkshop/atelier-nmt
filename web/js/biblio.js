/* ============================================================
   biblio.js — les gcodes rangés sur le Pi

   Un fichier tranché vit à un seul endroit : dans la bibliothèque du
   relais, rangé par famille de machines. Cet écran dit ce qu'elle
   contient, ce qui a déjà été imprimé et par quelle machine, et envoie
   un fichier sur une machine sans repasser par le PC.

   Ça ne répond qu'à l'atelier. Ailleurs, l'écran le dit et s'arrête là :
   mieux vaut une phrase claire qu'une roue qui tourne.
   ============================================================ */

const FAMILLES = { k2: 'Creality K2 Plus', p1s: 'Bambu Lab P1S' };

let BIB = null;          // dernier index reçu
let BIB_ERREUR = '';
let BIB_CHARGE = false;  // une requête est en cours
let BIB_FILTRE = '';     // recherche
let BIB_RESTE = false;   // n'afficher que ce qui reste à imprimer

function familleLabel(f) {
  return FAMILLES[f] || String(f || '').toUpperCase();
}

function biblioCharger(silencieux) {
  if (BIB_CHARGE) return;
  BIB_CHARGE = true;
  if (!silencieux) BIB_ERREUR = '';
  Biblio.index().then(res => {
    BIB_CHARGE = false;
    if (res && res.ok) {
      BIB = res;
      BIB_ERREUR = '';
    } else {
      BIB_ERREUR = (res && res.error) || 'réponse vide du relais';
    }
    if (TAB === 'biblio') render();
  }).catch(e => {
    BIB_CHARGE = false;
    BIB_ERREUR = e && e.message ? e.message : String(e);
    if (TAB === 'biblio') render();
  });
}

function biblioRafraichir() {
  BIB = null;
  biblioCharger();
  render();
}

/* ---------- l'écran ---------- */

function renderBiblio() {
  if (!Biblio.ok()) {
    setTop('Fichiers', 'Hors de l\'application');
    return emptyState('Bibliothèque indisponible',
      'Cet écran a besoin de l\'application installée sur le téléphone.');
  }

  if (!Biblio.regle()) {
    setTop('Fichiers', 'Relais non réglé');
    return emptyState('Bibliothèque pas encore branchée',
      'Donne l\'adresse du relais de l\'atelier dans les réglages — c\'est lui qui garde les gcodes.',
      'Ouvrir les réglages', 'go(\'settings\')');
  }

  if (!BIB && !BIB_ERREUR) {
    biblioCharger();
    setTop('Fichiers', 'Lecture de la bibliothèque…');
    return '<div class="card"><div class="rowitem"><div class="grow">' +
      '<div class="t">Lecture de la bibliothèque…</div>' +
      '<div class="s">Le relais liste les fichiers et leur historique.</div>' +
      '</div></div></div>';
  }

  if (!BIB) {
    setTop('Fichiers', 'Relais injoignable',
      '<button class="tb-btn" onclick="biblioRafraichir()">' + iconSync() + 'Réessayer</button>');
    return '<div class="card"><div class="rowitem"><div class="grow">' +
      '<div class="t">' + esc(BIB_ERREUR) + '</div>' +
      '<div class="s">La bibliothèque ne répond que sur le réseau de l\'atelier. ' +
      'En déplacement, l\'état des machines reste visible, pas les fichiers.</div>' +
      '</div></div></div>';
  }

  const tous = BIB.fichiers || [];
  const aFaire = tous.filter(f => f.reste > 0).length;
  setTop('Fichiers',
    tous.length + ' fichier' + (tous.length > 1 ? 's' : '') +
      (aFaire ? ' · ' + aFaire + ' à imprimer' : ' · tout est imprimé'),
    '<button class="tb-btn" onclick="biblioHistorique()">' + iconClock() + 'Historique</button>' +
    '<button class="tb-btn" onclick="biblioRafraichir()">' + iconSync() + '</button>');

  if (!tous.length) {
    return emptyState('Bibliothèque vide',
      'Dépose tes fichiers tranchés dans le dossier partagé du relais, un sous-dossier par famille de machines.');
  }

  const q = BIB_FILTRE.trim().toLowerCase();
  let out = '<div class="card tight">' +
    '<input id="bib-q" type="search" placeholder="Chercher un fichier" ' +
      'oninput="biblioChercher(this.value)" value="' + esc(BIB_FILTRE) + '">' +
    '<div class="chips" style="margin-top:8px">' +
      '<button type="button" class="chip' + (BIB_RESTE ? '' : ' on') + '" onclick="biblioFiltreReste(false)">Tout</button>' +
      '<button type="button" class="chip' + (BIB_RESTE ? ' on' : '') + '" onclick="biblioFiltreReste(true)">À imprimer</button>' +
    '</div></div>';

  const visibles = tous.filter(f => {
    if (BIB_RESTE && f.reste <= 0) return false;
    if (!q) return true;
    return (f.chemin + ' ' + f.nom).toLowerCase().indexOf(q) >= 0;
  });

  if (!visibles.length) {
    out += '<div class="card"><div class="rowitem"><div class="grow"><div class="t">Rien de ce nom</div>' +
      '<div class="s">' + (BIB_RESTE ? 'Essaie sans le filtre « à imprimer ».' : 'Aucun fichier ne correspond.') +
      '</div></div></div></div>';
    return out;
  }

  const parFamille = {};
  visibles.forEach(f => { (parFamille[f.famille] = parFamille[f.famille] || []).push(f); });

  (BIB.familles || Object.keys(parFamille)).forEach(fam => {
    const liste = parFamille[fam];
    if (!liste || !liste.length) return;
    const reste = liste.filter(f => f.reste > 0).length;
    out += '<div class="sec-title" data-fam="' + esc(fam) + '">' + esc(familleLabel(fam)) +
      ' <span class="norm">— ' + liste.length + ' fichier' + (liste.length > 1 ? 's' : '') +
      (reste ? ', ' + reste + ' à imprimer' : '') + '</span></div>';
    out += '<div class="stack" data-fam="' + esc(fam) + '">' + liste.map(ficheFichier).join('') + '</div>';
  });

  return out;
}

function biblioFiltreReste(v) {
  BIB_RESTE = !!v;
  render();
}

/* On masque les cartes au lieu de redessiner l'écran : sinon le champ de
   recherche perd le curseur à chaque lettre tapée. */
function biblioChercher(valeur) {
  BIB_FILTRE = String(valeur || '');
  const q = BIB_FILTRE.trim().toLowerCase();
  $$('#view [data-bib]').forEach(carte => {
    const va = !q || carte.getAttribute('data-bib').indexOf(q) >= 0;
    carte.style.display = va ? '' : 'none';
  });
  $$('#view .stack[data-fam]').forEach(pile => {
    const reste = $$('[data-bib]', pile).some(c => c.style.display !== 'none');
    pile.style.display = reste ? '' : 'none';
    const titre = $('#view .sec-title[data-fam="' + pile.getAttribute('data-fam') + '"]');
    if (titre) titre.style.display = reste ? '' : 'none';
  });
}

/* ---------- une ligne de fichier ---------- */

function etatFichier(f) {
  if (f.reste <= 0 && f.faits > 0) {
    return { cls: 'ok', mot: f.faits > 1 ? 'Fait ×' + f.faits : 'Fait' };
  }
  if (f.faits === 0) {
    return { cls: 'acc', mot: f.exemplaires > 1 ? 'À faire ×' + f.exemplaires : 'Jamais imprimé' };
  }
  return { cls: 'warn', mot: 'Reste ' + f.reste + ' sur ' + f.exemplaires };
}

function ficheFichier(f) {
  const e = etatFichier(f);
  const parts = [];
  if (f.dossier) parts.push(f.dossier);
  parts.push(fmtOctets(f.taille));
  if (f.faits > 0 && f.dernier) {
    parts.push('dernière le ' + fmtDate(f.dernier) +
      (f.machines.length ? ' · ' + f.machines.join(', ') : ''));
  }
  return '<div class="card click" data-bib="' + esc((f.chemin + ' ' + f.nom).toLowerCase()) + '"' +
    ' onclick="ficheFichierSheet(' + JSON.stringify(f.chemin).replace(/"/g, '&quot;') + ')">' +
    '<div class="rowitem"><div class="grow">' +
      '<div class="t">' + esc(nomCourt(f.nom)) + '</div>' +
      '<div class="s">' + esc(parts.join(' · ')) + '</div>' +
    '</div>' + badge(e.cls, e.mot) + '</div></div>';
}

/* le « _x3 » du nom dit le nombre d'exemplaires : le badge le porte déjà,
   autant ne pas l'afficher deux fois */
function nomCourt(nom) {
  return String(nom || '')
    .replace(/\.(gcode\.3mf|gcode|3mf|gco|g)$/i, '')
    .replace(/[ _(\[-]x\s*\d{1,3}\)?\]?$/i, '')
    .trim() || String(nom || '');
}

function fmtOctets(o) {
  o = Number(o) || 0;
  if (o >= 1048576) return (o / 1048576).toFixed(o >= 10485760 ? 0 : 1).replace('.', ',') + ' Mo';
  if (o >= 1024) return Math.round(o / 1024) + ' Ko';
  return o + ' o';
}

/* ---------- la fiche détaillée ---------- */

function ficheFichierSheet(chemin) {
  const f = (BIB && BIB.fichiers || []).find(x => x.chemin === chemin);
  if (!f) return;
  const dest = Biblio.destinataires(f.famille);

  let html = '<h2>' + esc(nomCourt(f.nom)) + '</h2>' +
    '<div class="sub">' + esc(f.chemin) + '</div>';

  html += '<div class="card tight" style="margin-top:10px">' +
    ligneInfo('Famille', familleLabel(f.famille)) +
    ligneInfo('Taille', fmtOctets(f.taille)) +
    ligneInfo('Déposé le', fmtDate(f.modifie)) +
    ligneInfo('Imprimé', f.faits === 0 ? 'jamais'
      : f.faits + ' fois' + (f.minutes ? ' · ' + fmtDurShort(f.minutes * 60000) + ' de machine' : '')) +
    (f.faits && f.dernier ? ligneInfo('Dernière', fmtDate(f.dernier) +
      (f.machines.length ? ' · ' + f.machines.join(', ') : '')) : '') +
    '</div>';

  html += '<div class="sec-title">Exemplaires voulus</div>' +
    '<div class="card tight"><div class="rowitem">' +
      '<button class="btn ghost" onclick="biblioExemplaires(' + JSON.stringify(chemin).replace(/"/g, '&quot;') + ',-1)">−</button>' +
      '<div class="grow" style="text-align:center"><div class="t" id="bib-ex">' + f.exemplaires + '</div>' +
      '<div class="s">' + (f.reste > 0 ? 'il en reste ' + f.reste : 'compte atteint') + '</div></div>' +
      '<button class="btn ghost" onclick="biblioExemplaires(' + JSON.stringify(chemin).replace(/"/g, '&quot;') + ',1)">+</button>' +
    '</div></div>';

  html += '<div class="sec-title">Envoyer sur une machine</div>';
  if (!dest.length) {
    html += '<div class="card tight"><div class="s">Aucune machine de cette famille dans le parc.</div></div>';
  } else {
    html += '<div class="stack">';
    dest.forEach(m => {
      const moonraker = m.printer.kind === 'moonraker';
      const c = JSON.stringify(chemin).replace(/"/g, '&quot;');
      const n = JSON.stringify(m.name).replace(/"/g, '&quot;');
      html += '<div class="card tight"><div class="rowitem"><div class="grow">' +
        '<div class="t">' + esc(m.name) + '</div>' +
        '<div class="s">' + esc(m.model || '') + '</div></div>' +
        '<button class="btn ghost" onclick="biblioPousser(' + c + ',' + n + ',false)">Déposer</button>' +
        (moonraker ? '<button class="btn primary" onclick="biblioPousser(' + c + ',' + n + ',true)">Lancer</button>' : '') +
        '</div></div>';
    });
    html += '</div>';
    if (dest.some(m => m.printer.kind === 'bambu')) {
      html += '<div class="note">Sur les Bambu, le fichier est déposé sur la carte de la machine : ' +
        'il se lance ensuite d\'un geste sur son écran. Lancer d\'ici reviendrait à choisir ' +
        'le plateau et les bobines à l\'aveugle.</div>';
    }
  }

  sheet(html);
}

function ligneInfo(cle, valeur) {
  return '<div class="rowitem"><div class="grow"><div class="s">' + esc(cle) + '</div></div>' +
    '<div class="t">' + esc(valeur) + '</div></div>';
}

/* ---------- actions ---------- */

function biblioExemplaires(chemin, delta) {
  const f = (BIB && BIB.fichiers || []).find(x => x.chemin === chemin);
  if (!f) return;
  const voulu = Math.max(1, Math.min(999, f.exemplaires + delta));
  if (voulu === f.exemplaires) return;
  f.exemplaires = voulu;
  f.reste = Math.max(0, voulu - f.faits);
  const el = $('#bib-ex');
  if (el) el.textContent = voulu;
  Biblio.exemplaires(chemin, voulu).then(res => {
    if (!res || !res.ok) toast((res && res.error) || 'réglage refusé', 'bad');
  }).catch(e => toast(e.message || 'réglage refusé', 'bad'));
}

function biblioPousser(chemin, machine, lancer) {
  const f = (BIB && BIB.fichiers || []).find(x => x.chemin === chemin);
  const nom = f ? nomCourt(f.nom) : chemin;
  const faire = () => {
    closeSheet();
    toast('Envoi de ' + nom + ' vers ' + machine + '…');
    Biblio.pousser(chemin, machine, lancer).then(res => {
      if (res && res.ok) {
        toast(res.lance ? nom + ' lancé sur ' + machine : nom + ' déposé sur ' + machine, 'ok');
        biblioCharger(true);
      } else {
        toast((res && res.error) || 'envoi refusé', 'bad');
      }
    }).catch(e => toast(e.message || 'envoi refusé', 'bad'));
  };

  if (lancer) {
    confirmSheet('Lancer sur ' + machine + ' ?',
      nom + ' part sur la machine et l\'impression démarre tout de suite. ' +
      'Vérifie que le plateau est vide.', 'Lancer', faire);
    return;
  }
  faire();
}


/* ---------- l'historique de la farm ----------

   Toutes machines confondues, dans l'ordre : ce que le relais a vu
   partir et arriver au bout. C'est ce qui alimente le « déjà imprimé »
   de chaque fichier. */

const ISSUES = {
  fini: { cls: 'ok', mot: 'fini' },
  'échec': { cls: 'bad', mot: 'échec' },
  interrompu: { cls: 'warn', mot: 'interrompu' },
  'envoyé': { cls: 'info', mot: 'envoyé' }
};

function biblioHistorique() {
  sheet('<h2>Historique de la farm</h2>' +
    '<div class="sub">Lecture du relais…</div>');
  Biblio.historique(80)
    .then(res => {
      if (!res || !res.ok) {
        sheet('<h2>Historique de la farm</h2><div class="sub">' +
          esc((res && res.error) || 'sans réponse') + '</div>');
        return;
      }
      const lignes = res.lignes || [];
      if (!lignes.length) {
        sheet('<h2>Historique de la farm</h2>' +
          '<div class="sub">Rien encore. Le relais note chaque impression qu\'il voit ' +
          'commencer et finir, donc l\'historique part de son installation.</div>');
        return;
      }
      let html = '<h2>Historique de la farm</h2>' +
        '<div class="sub">' + lignes.length + ' dernières impressions, toutes machines</div>' +
        '<div class="card tight">';
      lignes.forEach(l => {
        const i = ISSUES[l.etat] || { cls: 'info', mot: l.etat || '?' };
        const quand = l.fin || l.at || 0;
        const duree = l.minutes ? ' · ' + fmtDurShort(l.minutes * 60000) : '';
        html += '<div class="rowitem"><div class="grow">' +
          '<div class="t">' + esc(nomCourt(l.fichier)) + '</div>' +
          '<div class="s">' + esc(l.machine || '') + ' · ' + (quand ? fmtDate(quand) : '') + duree + '</div>' +
          '</div>' + badge(i.cls, i.mot) + '</div>';
      });
      html += '</div>';
      sheet(html);
    })
    .catch(e => sheet('<h2>Historique de la farm</h2><div class="sub">' +
      esc(e.message || String(e)) + '</div>'));
}
