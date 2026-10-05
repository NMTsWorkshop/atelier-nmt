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
      '<div class="s">Le relais liste les fichiers, les plateaux et leur historique.</div>' +
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
  const commandes = BIB.commandes || [];
  const encours = commandes.filter(c => !c.termine).length;
  const reste = tous.reduce((n, f) => n + f.reste, 0);

  setTop('Fichiers',
    (commandes.length
      ? encours + ' commande' + (encours > 1 ? 's' : '') + ' en cours'
      : tous.length + ' fichier' + (tous.length > 1 ? 's' : '')) +
      (reste ? ' · ' + reste + ' plateau' + (reste > 1 ? 'x' : '') + ' à sortir' : ' · rien à sortir'),
    '<button class="tb-btn" onclick="biblioHistorique()">' + iconClock() + 'Historique</button>' +
    '<button class="tb-btn" onclick="biblioRafraichir()">' + iconSync() + '</button>');

  /* lue à distance : tout se voit et se coche, mais un gcode ne passe pas
     par le canal du relais */
  let out = BIB.canal
    ? '<div class="note" style="margin:0 2px 12px">Lu par le relais, à distance. ' +
      'Tout marche, y compris envoyer un fichier sur une machine — c\'est le relais ' +
      'qui s\'en charge, dans la minute.</div>'
    : '';

  if (!tous.length) {
    return out + emptyState('Bibliothèque vide',
      'Dépose tes fichiers tranchés dans le dossier partagé du relais. Un sous-dossier par commande, ' +
      'sous k2 ou p1s selon la machine.');
  }

  const q = BIB_FILTRE.trim().toLowerCase();
  out += '<div class="card tight">' +
    '<input id="bib-q" type="search" placeholder="Chercher un fichier ou une commande" ' +
      'oninput="biblioChercher(this.value)" value="' + esc(BIB_FILTRE) + '">' +
    '<div class="chips" style="margin-top:8px">' +
      '<button type="button" class="chip' + (BIB_RESTE ? '' : ' on') + '" onclick="biblioFiltreReste(false)">Tout</button>' +
      '<button type="button" class="chip' + (BIB_RESTE ? ' on' : '') + '" onclick="biblioFiltreReste(true)">À sortir</button>' +
    '</div></div>';

  const visibles = tous.filter(f => {
    if (BIB_RESTE && f.reste <= 0) return false;
    if (!q) return true;
    return (f.chemin + ' ' + f.nom + ' ' + (f.commande || '')).toLowerCase().indexOf(q) >= 0;
  });

  if (!visibles.length) {
    return out + '<div class="card"><div class="rowitem"><div class="grow"><div class="t">Rien de ce nom</div>' +
      '<div class="s">' + (BIB_RESTE ? 'Essaie sans le filtre « à sortir ».' : 'Aucun fichier ne correspond.') +
      '</div></div></div></div>';
  }

  /* une commande n'est finie que quand ses plateaux sont tous sortis, K2 et
     Bambu confondues : c'est ce que ce regroupement donne à voir */
  commandes.forEach(c => {
    const liste = visibles.filter(f => f.commande === c.nom);
    if (!liste.length) return;
    out += enteteCommande(c) +
      '<div class="stack" data-grp="' + esc(c.nom) + '">' + liste.map(ficheFichier).join('') + '</div>';
  });

  const orphelins = visibles.filter(f => !f.commande);
  if (orphelins.length) {
    out += '<div class="sec-title" data-grp="">Hors commande ' +
      '<span class="norm">— ' + orphelins.length + ' fichier' + (orphelins.length > 1 ? 's' : '') + '</span></div>' +
      '<div class="stack" data-grp="">' + orphelins.map(ficheFichier).join('') + '</div>';
  }

  return out;
}

function enteteCommande(c) {
  const machines = c.familles.map(familleCourte).join(' + ');
  return '<div class="cmd-head" data-grp="' + esc(c.nom) + '">' +
    '<div class="grow"><div class="cmd-nom">' + esc(c.nom) + '</div>' +
    '<div class="cmd-sub">' + c.faits + ' plateau' + (c.faits > 1 ? 'x' : '') + ' sur ' + c.plateaux +
      ' · ' + esc(machines) +
      (c.minutes ? ' · ' + fmtDurShort(c.minutes * 60000) + ' de machine' : '') + '</div></div>' +
    badge(c.termine ? 'ok' : (c.faits ? 'warn' : 'acc'),
          c.termine ? 'Terminée' : (c.faits ? 'En cours' : 'À faire')) +
    '</div>' + gauge(c.plateaux ? (c.faits / c.plateaux) * 100 : 0, c.termine ? 'ok' : 'warn');
}

function familleCourte(f) {
  return { k2: 'K2', p1s: 'P1S' }[f] || String(f).toUpperCase();
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
  $$('#view .stack[data-grp]').forEach(pile => {
    const grp = pile.getAttribute('data-grp');
    const reste = $$('[data-bib]', pile).some(c => c.style.display !== 'none');
    pile.style.display = reste ? '' : 'none';
    $$('#view [data-grp]').forEach(tete => {
      if (tete !== pile && tete.getAttribute('data-grp') === grp) {
        tete.style.display = reste ? '' : 'none';
      }
    });
  });
}

/* ---------- une ligne de fichier ---------- */

function etatFichier(f) {
  if (f.reste <= 0 && f.faits > 0) {
    return { cls: 'ok', mot: f.multi ? 'Tous sortis' : (f.faits > 1 ? 'Fait ×' + f.faits : 'Fait') };
  }
  if (f.faits === 0) {
    return { cls: 'acc', mot: f.exemplaires > 1 ? 'À faire ×' + f.exemplaires : 'Jamais imprimé' };
  }
  return { cls: 'warn', mot: 'Reste ' + f.reste + ' sur ' + f.exemplaires };
}

function ficheFichier(f) {
  const e = etatFichier(f);
  const parts = [];
  if (f.multi) parts.push(f.plateaux.length + ' plateaux');
  if (f.dossier && !f.commande) parts.push(f.dossier);
  parts.push(fmtOctets(f.taille));
  if (f.minutes) parts.push(fmtDurShort(f.minutes * 60000));
  if (f.faits > 0 && f.dernier) {
    parts.push('dernière le ' + fmtDate(f.dernier) +
      (f.machines.length ? ' · ' + f.machines.join(', ') : ''));
  }
  return '<div class="card click" data-bib="' +
    esc((f.chemin + ' ' + f.nom + ' ' + (f.commande || '')).toLowerCase()) + '"' +
    ' onclick="ficheFichierSheet(' + JSON.stringify(f.chemin).replace(/"/g, '&quot;') + ')">' +
    '<div class="rowitem"><div class="grow">' +
      '<div class="t">' + esc(nomCourt(f.nom)) + ' ' + badge('info', familleCourte(f.famille)) + '</div>' +
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

function fichierDe(chemin) {
  return (BIB && BIB.fichiers || []).find(x => x.chemin === chemin);
}

function ficheFichierSheet(chemin) {
  const f = fichierDe(chemin);
  if (!f) return;
  const dest = Biblio.destinataires(f.famille);
  const cle = JSON.stringify(chemin).replace(/"/g, '&quot;');

  let html = '<h2>' + esc(nomCourt(f.nom)) + '</h2>' +
    '<div class="sub">' + esc(f.chemin) + '</div>';

  html += '<div class="card tight">' +
    ligneInfo('Machines', familleLabel(f.famille)) +
    ligneInfo('Commande', f.commande || 'aucune') +
    ligneInfo('Taille', fmtOctets(f.taille)) +
    (f.minutes ? ligneInfo('Durée prévue', fmtDurShort(f.minutes * 60000)) : '') +
    ligneInfo('Déposé le', fmtDate(f.modifie)) +
    '</div>' +
    '<div class="btn-row"><button class="btn ghost" onclick="biblioRattacher(' + cle + ')">' +
      (f.commande ? 'Changer de commande' : 'Rattacher à une commande') + '</button></div>';

  /* ---- les plateaux ---- */
  if (f.multi) {
    html += '<div class="sec-title">Plateaux</div><div class="stack">' +
      f.plateaux.map(p => ligneplateau(chemin, p)).join('') + '</div>';
  } else {
    const p = f.plateaux[0];
    html += '<div class="sec-title">Exemplaires voulus</div>' +
      '<div class="card tight"><div class="rowitem">' +
        '<button class="btn ghost" onclick="biblioExemplaires(' + cle + ',-1)">−</button>' +
        '<div class="grow" style="text-align:center"><div class="t" id="bib-ex">' + p.exemplaires + '</div>' +
        '<div class="s">' + (p.faits ? p.faits + ' sorti' + (p.faits > 1 ? 's' : '') : 'aucun sorti') + '</div></div>' +
        '<button class="btn ghost" onclick="biblioExemplaires(' + cle + ',1)">+</button>' +
      '</div></div>';
  }

  /* ---- envoyer ---- */
  html += '<div class="sec-title">Envoyer sur une machine</div>';
  if (!dest.length) {
    html += '<div class="card tight"><div class="s">Aucune machine de cette famille dans le parc.</div></div>';
  } else {
    html += '<div class="stack">';
    dest.forEach(m => {
      const moonraker = m.printer.kind === 'moonraker';
      const n = JSON.stringify(m.name).replace(/"/g, '&quot;');
      html += '<div class="card tight"><div class="rowitem"><div class="grow">' +
        '<div class="t">' + esc(m.name) + '</div>' +
        '<div class="s">' + esc(m.model || '') + '</div></div>' +
        '<button class="btn ghost" onclick="biblioPousser(' + cle + ',' + n + ',false)">Déposer</button>' +
        (moonraker ? '<button class="btn primary" onclick="biblioPousser(' + cle + ',' + n + ',true)">Lancer</button>' : '') +
        '</div></div>';
    });
    html += '</div>';
    if (BIB.canal) {
      html += '<div class="note">C\'est le relais qui enverra le fichier : il l\'a déjà, et il est ' +
        'sur le réseau des machines. Compte une minute avant qu\'il s\'y mette.</div>';
    }
    if (f.multi) {
      html += '<div class="note">Le fichier part entier, ses plateaux avec. Tu choisis le plateau ' +
        'sur l\'écran de la machine, puis tu le coches ici — la machine ne dit pas encore lequel ' +
        'elle a fait.</div>';
    } else if (dest.some(m => m.printer.kind === 'bambu')) {
      html += '<div class="note">Sur les Bambu, le fichier est déposé sur la carte de la machine : ' +
        'il se lance ensuite d\'un geste sur son écran. Lancer d\'ici reviendrait à choisir ' +
        'le plateau et les bobines à l\'aveugle.</div>';
    }
  }

  sheet(html, () => { if (f.multi && !BIB.canal) chargerApercus(f); });
}

function ligneplateau(chemin, p) {
  const cle = JSON.stringify(chemin).replace(/"/g, '&quot;');
  const fini = p.reste <= 0;
  const infos = [];
  if (p.minutes) infos.push(fmtDurShort(p.minutes * 60000));
  if (p.grammes) infos.push(p.grammes + ' g');
  if (p.exemplaires > 1) infos.push(p.faits + ' sur ' + p.exemplaires);
  const objets = (p.objets || []).join(', ');

  return '<div class="card tight plateau' + (fini ? ' fini' : '') + '" data-plateau="' + p.idx + '">' +
    '<div class="rowitem">' +
      '<img class="vignette" id="vg-' + p.idx + '" alt="" style="display:none">' +
      '<div class="grow">' +
        '<div class="t">Plateau ' + p.idx + '</div>' +
        '<div class="s">' + esc(objets || infos.join(' · ')) + '</div>' +
        (objets && infos.length ? '<div class="s">' + esc(infos.join(' · ')) + '</div>' : '') +
      '</div>' +
      (fini
        ? '<button class="btn ghost" onclick="biblioMarquer(' + cle + ',' + p.idx + ',false)">Annuler</button>'
        : '<button class="btn primary" onclick="biblioMarquer(' + cle + ',' + p.idx + ',true)">Fait</button>') +
    '</div></div>';
}

/* les aperçus arrivent du relais un par un : la feuille s'affiche tout de
   suite et les images se posent après */
function chargerApercus(f) {
  f.plateaux.forEach(p => {
    Biblio.apercu(f.chemin, p.idx).then(res => {
      if (!res || !res.ok || !res.png) return;
      const img = document.getElementById('vg-' + p.idx);
      if (!img) return;
      img.src = 'data:image/png;base64,' + res.png;
      img.style.display = '';
    }).catch(() => {});
  });
}

function ligneInfo(cle, valeur) {
  return '<div class="rowitem"><div class="grow"><div class="s">' + esc(cle) + '</div></div>' +
    '<div class="t">' + esc(valeur) + '</div></div>';
}

/* ---------- actions ---------- */

function biblioExemplaires(chemin, delta) {
  const f = fichierDe(chemin);
  if (!f || !f.plateaux.length) return;
  const p = f.plateaux[0];
  const voulu = Math.max(1, Math.min(999, p.exemplaires + delta));
  if (voulu === p.exemplaires) return;
  p.exemplaires = voulu;
  p.reste = Math.max(0, voulu - p.faits);
  f.exemplaires = voulu;
  f.reste = p.reste;
  const el = $('#bib-ex');
  if (el) el.textContent = voulu;
  Biblio.exemplaires(chemin, voulu).then(res => {
    if (!res || !res.ok) toast((res && res.error) || 'réglage refusé', 'bad');
    else biblioCharger(true);
  }).catch(e => toast(e.message || 'réglage refusé', 'bad'));
}

function biblioMarquer(chemin, plateau, fait) {
  const f = fichierDe(chemin);
  const nom = f ? nomCourt(f.nom) : chemin;
  Biblio.marquer(chemin, plateau, fait, '').then(res => {
    if (!res || !res.ok) {
      toast((res && res.error) || 'refusé par le relais', 'bad');
      return;
    }
    const mot = fait ? 'Plateau ' + plateau + ' de ' + nom + ' marqué fait'
                     : 'Plateau ' + plateau + ' remis à faire';
    toast(res.differe ? mot + ' — le relais suit dans la minute' : mot, 'ok');
    closeSheet();
    /* à distance l'ordre met une relève à arriver : on laisse au relais le
       temps de l'appliquer avant de relire, sinon on réaffiche l'ancien état */
    if (res.differe) setTimeout(() => biblioCharger(), 70000);
    else biblioCharger();
  }).catch(e => toast(e.message || 'refusé', 'bad'));
}

/* Le dossier fait la commande par défaut. Ce rattachement-là sert aux
   fichiers rangés ailleurs, ou quand une commande déborde sur un autre
   dossier. */
function biblioRattacher(chemin) {
  const f = fichierDe(chemin);
  if (!f) return;
  const connues = (BIB.commandes || []).map(c => c.nom);
  const ouvertes = DB.orders
    .filter(o => o.status !== 'shipped')
    .map(o => comptaRef(o).replace(/^#/, '') + (o.customer ? ' ' + o.customer : ''));
  ouvertes.forEach(n => { if (connues.indexOf(n) < 0) connues.push(n); });

  sheet('<h2>Rattacher à une commande</h2>' +
    '<div class="sub">' + esc(nomCourt(f.nom)) + '</div>' +
    '<label class="field"><span>Commande</span>' +
      '<input type="text" name="cmd" value="' + esc(f.commande || '') + '" placeholder="1045 Mando">' +
      '<div class="hint">Vide pour la détacher. Par défaut c\'est le nom du sous-dossier.</div>' +
    '</label>' +
    (connues.length
      ? '<div class="chips">' + connues.slice(0, 12).map(n =>
          '<button type="button" class="chip" data-v="' + esc(n) + '">' + esc(n) + '</button>').join('') +
        '</div>'
      : '') +
    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Enregistrer</button>' +
    '</div>',
    root => {
      $$('.chip', root).forEach(c => {
        c.onclick = () => { $('[name=cmd]', root).value = c.getAttribute('data-v'); };
      });
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        const v = $('[name=cmd]', root).value.trim();
        closeSheet();
        Biblio.rattacher(chemin, v).then(res => {
          if (!res || !res.ok) { toast((res && res.error) || 'refusé', 'bad'); return; }
          toast((v ? 'Rattaché à ' + v : 'Détaché') +
                (res.differe ? ' — le relais suit dans la minute' : ''), 'ok');
          if (res.differe) setTimeout(() => biblioCharger(), 70000);
          else biblioCharger();
        }).catch(e => toast(e.message || 'refusé', 'bad'));
      };
    });
}

function biblioPousser(chemin, machine, lancer) {
  const f = fichierDe(chemin);
  const nom = f ? nomCourt(f.nom) : chemin;
  const faire = () => {
    closeSheet();
    toast('Envoi de ' + nom + ' vers ' + machine + '…');
    Biblio.pousser(chemin, machine, lancer).then(res => {
      if (res && res.differe) {
        toast('Demandé au relais — ' + nom + ' part vers ' + machine + ' dans la minute', 'ok');
        setTimeout(() => biblioCharger(true), 70000);
      } else if (res && res.ok) {
        toast(res.lance ? nom + ' lancé sur ' + machine : nom + ' déposé sur ' + machine, 'ok');
        biblioCharger(true);
      } else {
        toast((res && res.error) || 'envoi refusé', 'bad');
      }
    }).catch(e => toast(e.message || 'envoi refusé', 'bad'));
  };

  if (lancer) {
    confirmSheet('Lancer sur ' + machine + ' ?',
      nom + ' part sur la machine et l\'impression démarre' +
      (BIB.canal ? ' dès que le relais aura relayé, dans la minute.' : ' tout de suite.') +
      ' Vérifie que le plateau est vide.', 'Lancer', faire);
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
  'envoyé': { cls: 'info', mot: 'envoyé' },
  'refusé': { cls: 'bad', mot: 'refusé' }
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
          (l.pourquoi ? '<div class="s" style="color:var(--bad)">' + esc(l.pourquoi) + '</div>' : '') +
          '</div>' + badge(i.cls, i.mot) + '</div>';
      });
      html += '</div>';
      sheet(html);
    })
    .catch(e => sheet('<h2>Historique de la farm</h2><div class="sub">' +
      esc(e.message || String(e)) + '</div>'));
}
