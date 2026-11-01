/* ============================================================
   machines.js — parc machines, timers, changement de filament
   ============================================================ */

function renderMachines() {
  /* une machine qui imprime d'après son propre relevé compte aussi */
  const enDirect = m => m.printer && m.printer.host && Printers.fresh(m.id) &&
    Printers.state(m.id) && Printers.state(m.id).state === 'printing' &&
    !(Printers.stale(m.id) && Printers.endAt(m.id) && Printers.endAt(m.id) <= Date.now());
  const running = DB.machines.filter(m => m.status === 'running' || enDirect(m)).length;
  const done = DB.machines.filter(m => m.status === 'done').length;
  setTop('Machines',
    DB.machines.length
      ? running + ' en cours · ' + done + ' terminée' + (done > 1 ? 's' : '') + ' · ' + DB.machines.length + ' machine' + (DB.machines.length > 1 ? 's' : '')
      : 'Aucune machine pour l\'instant',
    '<button class="tb-btn" title="Heure de fin" onclick="calculetteFin()">' + iconClock() + '</button>' +
    (DB.machines.some(m => m.printer && m.printer.host)
      ? '<button class="tb-btn" id="poll-btn" onclick="pollPrinters()">' + iconSync() + '</button>' : '') +
    '<button class="tb-btn accent" onclick="editMachine()">' + iconPlus() + 'Machine</button>'
  );

  if (!DB.machines.length) {
    return emptyState(
      'Ton parc est vide',
      'Ajoute tes imprimantes une par une : nom, modèle, et le filament actuellement chargé.',
      'Ajouter une machine', 'editMachine()'
    );
  }

  const warn = nativeWarningBanner();

  return warn + bandeauServeur() + barreAtelier() + '<div class="stack">' +
    DB.machines.map(machineCard).join('') + '</div>';
}


/* ============================================================
   L'atelier en grand : les lumières de tout le parc
   ============================================================

   Le relais a aussi piloté le courant des machines, par multiprises
   connectées. Ça n'existe plus : ces multiprises lâchaient leurs relais
   sous l'appel de courant d'un plateau chauffant, et les machines sont
   maintenant sur une alimentation sans électronique. Le redémarrage à
   distance, si on y revient un jour, se fera par Moonraker et MQTT —
   logiciel, sans toucher au courant. */

/* Le serveur, en un bandeau.

   C'est la première chose à savoir quand plus rien ne répond : est-ce le
   serveur qui est éteint, ou autre chose ? L'écran le disait seulement en
   creux — un partage « arrêté », un délai qui ne bougeait plus — et il
   fallait deviner.

   Un point coloré et une phrase, sans bouton. Il y avait un « répond-il ? »
   qui allait le lui demander en direct : ça ne marchait qu'à l'atelier, et
   la ligne dit déjà s'il est là. Un bouton qui double une information déjà
   affichée est un bouton de trop.

   Vu de loin, la réponse est forcément datée : elle vaut ce que vaut le
   dernier relevé, et le bandeau le précise au lieu de faire comme si elle
   était d'instant. */
function bandeauServeur() {
  const st = piStatut();
  if (!st) return '';
  return '<div class="card tight" style="margin-bottom:10px;display:flex;' +
      'align-items:center;gap:10px">' +
    dot(st.couleur) +
    '<div class="grow">' +
      '<div style="font-size:14px;font-weight:600">Serveur — ' +
        '<span style="color:' + st.couleur + '">' + esc(st.dit) + '</span></div>' +
      (st.detail ? '<div class="card-meta">' + esc(st.detail) + '</div>' : '') +
    '</div>' +
  '</div>';
}

/* Les lumières de chambre, pour tout le parc.

   Elles étaient dans la même carte que l'état du serveur, ce qui mélangeait
   deux choses sans rapport : « le serveur est en ligne » et « allume les
   lumières ». Chacune sa carte. */
function barreAtelier() {
  if (!Relais.ok() || !Relais.sujet()) return '';
  etatRelaisAuBesoin();

  return '<div class="card" style="margin-bottom:10px">' +
    '<div class="spread" style="margin-bottom:9px">' +
      '<div class="card-name" style="font-size:15px">Les lumières</div>' +
      '<span class="card-meta">tout le parc</span>' +
    '</div>' +
    '<div class="btn-row">' +
      '<button class="btn sm" onclick="lumieresToutes(true)">Allumer</button>' +
      '<button class="btn sm ghost" onclick="lumieresToutes(false)">Éteindre</button>' +
    '</div>' +
    '<div class="hint" id="atelier-out" style="margin-top:8px">' + ATELIER_DIT + '</div>' +
  '</div>';
}


let ATELIER_DIT = '';

function atelierDire(html) {
  ATELIER_DIT = html || '';
  const o = $('#atelier-out');
  if (o) o.innerHTML = ATELIER_DIT;
}

/* L'app se souvient de ce qu'elle a demandé : le relais ne sait pas lire
   l'état d'une lampe, et un bouton qui ment sur ce qu'il va faire est pire
   qu'un bouton qui se trompe une fois. */
function lumiereRetenue(id) {
  return !!(DB.settings.lights || {})[id];
}

function retenirLumiere(id, allumee) {
  DB.settings.lights = DB.settings.lights || {};
  DB.settings.lights[id] = !!allumee;
  save();
}

function lumiereMachine(id) {
  const m = machineById(id);
  if (!m) return;
  const allumer = !lumiereRetenue(id);
  atelierDire('Lumière…');
  Relais.lumiere(m.name, (m.printer && m.printer.host) || '', allumer)
    .then(r => {
      if (r && r.ok) {
        retenirLumiere(id, allumer);
        atelierDire('');
        toast('Lumière ' + (allumer ? 'allumée' : 'éteinte'), 'ok');
        render();
      } else if (r && r.differe && r.id) {
        suivreEtDire(r.id, () => { retenirLumiere(id, allumer); render(); });
      } else {
        toast('Échec — ' + ((r && r.error) || 'sans réponse'), 'bad');
        atelierDire('<span style="color:var(--bad)">' +
          esc((r && r.error) || 'sans réponse') + '</span>');
      }
    })
    .catch(e => toast('Échec — ' + e.message, 'bad'));
}

/* Une machine après l'autre, jamais les quatre d'un coup.

   Côté Bambu, chaque ordre ouvre une session MQTT sur la machine, et une
   P1S n'en accepte qu'un petit nombre à la fois : quatre connexions
   simultanées, et elle décroche. C'est ce qui est arrivé le premier soir.
   En série c'est un peu plus lent et ça ne bouscule personne. */
function lumieresToutes(allumer) {
  const cibles = DB.machines.filter(m => m.printer && m.printer.host);
  if (!cibles.length) { toast('Aucune machine branchée', 'bad'); return; }

  let ratees = 0;
  const suivante = (i) => {
    if (i >= cibles.length) {
      atelierDire(ratees
        ? '<span style="color:var(--bad)">' + ratees + ' machine(s) sans réponse</span>'
        : '');
      toast(ratees ? ratees + ' sans réponse' : 'Lumières ' +
            (allumer ? 'allumées' : 'éteintes'), ratees ? 'bad' : 'ok');
      render();
      return;
    }
    const m = cibles[i];
    atelierDire('Lumières… (' + (i + 1) + '/' + cibles.length + ' — ' +
                esc(m.name) + ')');
    Relais.lumiere(m.name, m.printer.host, allumer)
      .then(r => { if (!r || (!r.ok && !r.differe)) ratees++; else retenirLumiere(m.id, allumer); })
      .catch(() => { ratees++; })
      .then(() => suivante(i + 1));
  };
  suivante(0);
}

/* `dire` dit où écrire : la barre de l'atelier par défaut, ailleurs quand
   l'appel vient d'un autre écran. Sans ça la réponse du relais s'affichait
   toujours au même endroit, loin du bouton qu'on venait d'appuyer. */
function suivreEtDire(ident, apresSucces, surRefus, dire) {
  const ecrire = dire || atelierDire;
  ecrire('<span style="color:var(--txt-3)">Envoyé. Le relais répond dans la minute…</span>');
  return Biblio.suivreOrdre(ident).then(a => {
    if (!a) {
      ecrire('<span style="color:var(--bad)">Pas de réponse du relais.</span>');
      return;
    }
    ecrire('<span style="color:var(--' + (a.ok ? 'ok' : 'bad') + ')">' +
                esc(a.dit || (a.ok ? 'fait' : 'refusé')) + '</span>');
    if (a.ok) {
      toast('Le relais a pris en compte', 'ok');
      if (apresSucces) apresSucces();
    } else if (surRefus) {
      surRefus(a.dit || '');
    }
  }).catch(() => {});
}

function machineCard(m) {
  const sp = refMachine(m);
  const now = Date.now();
  let cls = 'card mach', clock = '', sub = '', actions = '';

  /* si la machine est branchée et qu'on a une relève fraîche,
     c'est elle qui parle — le timer manuel passe au second plan */
  const live = (m.printer && m.printer.host && Printers.fresh(m.id)) ? Printers.state(m.id) : null;

  if (live && live.state === 'printing') {
    const pct = live.percent >= 0 ? live.percent : 0;
    const vieux = Printers.stale(m.id);
    const fin = Printers.endAt(m.id);
    /* le temps restant se recalcule à partir de l'heure de fin prévue :
       il continue de décompter même sans nouveau relevé */
    const resteMin = fin ? Math.max(0, Math.round((fin - now) / 60000)) : -1;

    if (vieux && fin && fin <= now) {
      cls += ' done';
      clock = '<div class="clock done" style="font-size:22px">Sans doute fini</div>' +
              '<div class="clock-sub">prévu vers ' + fmtDayClock(fin) + '</div>';
      actions =
        '<button class="btn sm ghost" onclick="pollPrinters()">Actualiser</button>' +
        '<button class="btn sm primary" onclick="finishJob(\'' + m.id + '\')">Décharger</button>';
      if (live.file) sub = '<div class="card-meta nowrap" style="margin-top:6px;color:var(--txt-2)">' + esc(live.file) + '</div>';
      return machineShell(m, cls, clock, sub, actions, sp, live);
    }

    cls += ' running';
    const rest = fmtRemaining(resteMin);
    /* le temps restant d'abord, c'est lui qui sert ; le pourcentage en dessous */
    clock = '<div class="clock">' + (rest ? (vieux ? '≈ ' : '') + esc(rest) : pct + ' %') + '</div>' +
            '<div class="clock-sub">' +
              (rest ? pct + ' %' + (vieux ? ' au relevé' : '') : 'en cours') +
              (fin ? ' · fin vers ' + fmtDayClock(fin) : '') +
            '</div>';
    actions =
      pilotage(m, 'printing') +
      '<button class="btn sm ghost" onclick="pollPrinters()">Actualiser</button>' +
      '<button class="btn sm primary" onclick="finishJob(\'' + m.id + '\')">Terminer</button>';
    if (live.file) sub = '<div class="card-meta nowrap" style="margin-top:6px;color:var(--txt-2)">' + esc(live.file) + '</div>';
    return machineShell(m, cls, clock, sub, actions, sp, live);
  }

  /* la machine dit elle-même qu'elle est en pause */
  if (live && live.state === 'paused') {
    cls += ' paused';
    clock = '<div class="clock">En pause</div>' +
            '<div class="clock-sub">' + (live.percent >= 0 ? live.percent + ' %' : '') + '</div>';
    actions =
      pilotage(m, 'paused') +
      '<button class="btn sm ghost" onclick="pollPrinters()">Actualiser</button>';
    if (live.file) sub = '<div class="card-meta nowrap" style="margin-top:6px;color:var(--txt-2)">' + esc(live.file) + '</div>';
    return machineShell(m, cls, clock, sub, actions, sp, live);
  }

  if (live && (live.state === 'finished' || live.state === 'idle') && m.status !== 'idle') {
    cls += ' done';
    clock = '<div class="clock done">Terminé</div>' +
            '<div class="clock-sub">' + esc(live.file || '') + '</div>';
    actions =
      '<button class="btn sm primary" onclick="finishJob(\'' + m.id + '\')">Décharger</button>' +
      '<button class="btn sm ghost" onclick="pollPrinters()">Actualiser</button>';
    return machineShell(m, cls, clock, sub, actions, sp, live);
  }

  if (m.status === 'running' && m.timer) {
    const left = m.timer.endAt - now;
    cls += ' running';
    clock = '<div class="clock" id="clk-' + m.id + '">' + fmtDur(left) + '</div>' +
            '<div class="clock-sub">fin vers ' + fmtDayClock(m.timer.endAt) + '</div>';
    actions =
      '<button class="btn sm" onclick="addTime(\'' + m.id + '\',15)">+15 min</button>' +
      '<button class="btn sm" onclick="addTime(\'' + m.id + '\',60)">+1 h</button>' +
      '<button class="btn sm ghost" onclick="stopTimer(\'' + m.id + '\')">Arrêter</button>' +
      '<button class="btn sm primary" onclick="finishJob(\'' + m.id + '\')">Terminer</button>';
  } else if (m.status === 'done') {
    cls += ' done';
    clock = '<div class="clock done" id="clk-' + m.id + '">Terminé</div>' +
            '<div class="clock-sub">' + (m.timer ? 'à ' + fmtDayClock(m.timer.endAt) : '') + '</div>';
    actions =
      '<button class="btn sm primary" onclick="finishJob(\'' + m.id + '\')">Décharger</button>' +
      '<button class="btn sm" onclick="startTimer(\'' + m.id + '\')">Relancer</button>';
  } else if (m.status === 'paused') {
    cls += ' paused';
    clock = '<div class="clock">En pause</div>';
    actions =
      '<button class="btn sm primary" onclick="startTimer(\'' + m.id + '\')">Reprendre</button>' +
      '<button class="btn sm ghost" onclick="setStatus(\'' + m.id + '\',\'idle\')">Libérer</button>';
  } else {
    clock = '<div class="clock muted" style="font-size:22px">Libre</div>';
    actions =
      '<button class="btn sm primary" onclick="startTimer(\'' + m.id + '\')">Lancer une impression</button>' +
      '<button class="btn sm" onclick="setStatus(\'' + m.id + '\',\'paused\')">Pause</button>';
  }

  if (m.job && m.job.label && m.status !== 'idle') {
    sub = '<div class="card-meta nowrap" style="margin-top:6px;color:var(--txt-2)">' + esc(m.job.label) + '</div>';
  }

  return machineShell(m, cls, clock, sub, actions, sp, live);
}

/* Panne annoncée par la machine : code HMS côté Bambu, message de Klipper
   côté Creality. C'est l'information qui fait descendre à l'atelier, donc
   elle passe avant tout le reste de la fiche. */
function panneLigne(m) {
  const p = (m.printer && m.printer.host) ? Printers.panne(m.id) : '';
  if (!p) return '';
  return '<div class="card-meta" style="margin-top:8px;color:var(--bad);font-weight:600">' +
    esc(p) + '</div>';
}

/* Boutons de pilotage, seulement sur une machine branchée et jamais sur un
   relevé périmé : agir d'après une image vieille d'une heure n'a pas de sens. */
function pilotage(m, etat) {
  if (!m.printer || !m.printer.host || !Printers.ok()) return '';
  if (Printers.stale(m.id)) return '';
  if (etat === 'printing') {
    return '<button class="btn sm" onclick="piloter(\'' + m.id + '\',\'pause\')">Pause</button>' +
           '<button class="btn sm ghost" onclick="piloter(\'' + m.id + '\',\'cancel\')">Arrêter</button>';
  }
  return '<button class="btn sm primary" onclick="piloter(\'' + m.id + '\',\'resume\')">Reprendre</button>' +
         '<button class="btn sm ghost" onclick="piloter(\'' + m.id + '\',\'cancel\')">Arrêter</button>';
}


/* La lumière d'une machine. Le libellé dit ce que l'appui va faire, pas
   l'état supposé : c'est la seule chose dont on soit sûr, le relais ne
   sachant pas lire l'état d'une lampe. */
function boutonsAtelier(m) {
  if (!Relais.ok() || !Relais.sujet()) return '';
  return '<button class="btn sm" onclick="lumiereMachine(\'' + m.id + '\')">' +
         (lumiereRetenue(m.id) ? 'Éteindre la lumière' : 'Allumer la lumière') +
         '</button>';
}


const PILOTAGE_MOTS = {
  pause:  { verbe: 'Mettre en pause', fait: 'Mise en pause demandée' },
  resume: { verbe: 'Reprendre',       fait: 'Reprise demandée' },
  cancel: { verbe: 'Arrêter',         fait: 'Arrêt demandé' }
};

function piloter(id, action) {
  const m = machineById(id);
  if (!m) return;
  const mots = PILOTAGE_MOTS[action];

  const lancer = () => {
    toast(mots.verbe + '…');
    Printers.commande(m, action)
      .then(r => {
        if (r && r.ok) {
          toast(mots.fait, 'ok');
          /* la machine met une seconde ou deux à changer d'état */
          setTimeout(() => pollPrinters(true), 2500);
        } else {
          toast('Échec — ' + ((r && r.error) || 'sans réponse'), 'bad');
        }
      })
      .catch(e => toast('Échec — ' + e.message, 'bad'));
  };

  /* arrêter perd l'impression : on demande confirmation, les deux autres non */
  if (action === 'cancel') {
    confirmSheet('Arrêter l\'impression sur ' + m.name + ' ?',
      'La pièce en cours est perdue et le filament déjà posé avec.',
      'Arrêter', lancer, true);
  } else {
    lancer();
  }
}

/* enveloppe commune : en-tête, ligne filament, rangée d'actions */
function machineShell(m, cls, clock, sub, actions, sp, live) {
  const err = (m.printer && m.printer.host) ? Printers.error(m.id) : '';

  return '<div class="' + cls + '">' +
    '<div class="card-head tap" onclick="editMachine(\'' + m.id + '\')">' +
      '<div class="grow">' +
        '<div class="card-name">' + esc(m.name) +
          (live
            ? (live.relais && !Printers.stale(m.id)
                ? ' <span class="badge info" style="vertical-align:middle">via le relais</span>'
                : Printers.stale(m.id)
                  ? ' <span class="badge" style="vertical-align:middle">relevé de ' + fmtDayClock(live.at) + '</span>'
                  : ' <span class="badge ok" style="vertical-align:middle">en direct</span>')
            : '') +
        '</div>' +
        '<div class="card-meta">' + esc(m.model || '—') + '</div>' +
        sub +
      '</div>' +
      '<div style="text-align:right">' + clock + '</div>' +
    '</div>' +
    (live && live.stale
      ? '<div class="card-meta" style="margin-top:8px">Hors de portée' +
          (live.staleAt ? ' depuis ' + fmtDayClock(live.staleAt) : '') +
          ' — dernier relevé affiché</div>'
      : '') +
    (err
      ? '<div class="card-meta" style="margin-top:8px;color:var(--warn)">' +
          (Printers.reglage(m.id) ? 'Réglage à compléter — ' : 'Machine injoignable — ') +
          esc(err) + '</div>'
      : '') +
    panneLigne(m) +
    blocBobines(m, live, sp) +
    '<div class="row wrap" style="margin-top:12px">' + actions + boutonsAtelier(m) + '</div>' +
  '</div>';
}

/* Les bobines que la machine détecte, avec ce qu'il reste sur chacune.

   La machine dit ce qu'elle a dans son AMS : type, couleur, emplacement.
   Elle ne dit pas combien il en reste — aucune ne pèse ses bobines. Donc
   on tape dessus et on le renseigne, emplacement par emplacement. Ensuite
   chaque impression retire son poids de l'emplacement qui a servi.

   Une machine sans AMS a un seul emplacement, le même mécanisme. */
function blocBobines(m, live, sp) {
  const trays = (live && Array.isArray(live.ams) && live.ams.length)
    ? live.ams.filter(t => !t.inconnue)
    : [];

  /* rien de détecté : un seul emplacement, celui de la bobine posée à la
     main sur la machine */
  if (!trays.length) {
    return '<div style="margin-top:10px">' +
      pastilleBobine(m, SLOT_SEUL, sp ? spoolLabel(sp) : 'Bobine', sp && sp.colorHex) +
      (sp ? '' : '<div class="card-meta" style="margin-top:6px">Aucune bobine ' +
                 'détectée ni renseignée.</div>') +
    '</div>';
  }

  const inconnues = (live.ams || []).filter(t => t.inconnue).length;
  return '<div class="row wrap" style="gap:6px;margin-top:10px">' +
      trays.map(t => pastilleBobine(m, t.slot,
        esc(t.type) + (t.color ? ' ' + colorNameOf(t.color).toLowerCase() : ''),
        t.color)).join('') +
      (inconnues
        ? '<span class="badge" title="Bobine présente mais non renseignée sur la machine">' +
          '? ' + inconnues + ' non renseignée' + (inconnues > 1 ? 's' : '') + '</span>'
        : '') +
    '</div>';
}

/* Une bobine : ce qu'elle est, ce qu'il en reste, et on peut taper dessus. */
function pastilleBobine(m, slot, libelle, couleur) {
  const reste = niveauAms(m.id, slot);
  const taille = tailleAms(m.id, slot);
  const pct = reste === null ? 0 : Math.min(100, (reste / taille) * 100);
  const teinte = reste === null ? 'var(--txt-3)'
    : pct < DB.settings.lowThreshold ? 'var(--bad)'
    : pct < 40 ? 'var(--warn)' : 'var(--ok)';

  return '<button class="chip" style="gap:6px;align-items:center" ' +
      'onclick="reglerBobine(\'' + m.id + '\',\'' + esc(String(slot)) + '\')">' +
      (couleur ? '<span class="dot" style="background:' + esc(couleur) + '"></span>' : '') +
      '<span>' + libelle + '</span>' +
      '<b class="mono" style="font-size:12px;color:' + teinte + '">' +
        (reste === null ? 'niveau ?' : fmtG(reste)) + '</b>' +
    '</button>';
}

/* Le réglage d'une bobine : son niveau, sa référence, et « elle est neuve ». */
function reglerBobine(machineId, slot) {
  const m = machineById(machineId);
  if (!m) return;
  const f = amsFiche(machineId, slot) || {};
  const reste = niveauAms(machineId, slot);
  const ou = slot === SLOT_SEUL ? 'Bobine de ' + m.name
                                : 'Emplacement ' + slot + ' de ' + m.name;

  sheet(
    '<h2>' + esc(ou) + '</h2>' +
    '<div class="sub">La machine dit ce qu\'elle a, pas ce qu\'il en reste. ' +
      'Renseigne-le une fois : ensuite chaque impression le diminue toute seule.</div>' +

    '<label class="field"><span>Grammes restants</span>' +
      '<input type="number" name="restant" inputmode="numeric" min="0" placeholder="1000" value="' +
        (reste === null ? '' : reste) + '">' +
      '<div class="hint">Laisse vide pour revenir à « inconnu » — rien ne s\'en ' +
        'déduira plutôt que de partir d\'un chiffre inventé.</div>' +
    '</label>' +

    '<label class="field"><span>Référence en stock</span>' +
      spoolSelect('refId', f.refId || '') +
      '<div class="hint">Facultatif. Renseignée, « Neuve » retire une bobine de ' +
        'ta réserve, et le stock compte ces grammes dans le total de la référence.</div>' +
    '</label>' +

    '<div class="btn-row">' +
      '<button class="btn" data-x="neuve">Elle est neuve</button>' +
    '</div>' +

    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Valider</button>' +
    '</div>',

    root => {
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=neuve]', root).onclick = () => {
        const r = amsNeuve(machineId, slot, formValues(root).refId);
        closeSheet(); render();
        toast(r.prise ? 'Neuve, −1 en réserve' : 'Remise à ' + fmtG(r.grammes), 'ok');
      };
      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root);
        const saisi = String(v.restant || '').trim();
        poserAms(machineId, slot, saisi === '' ? null : num(saisi), v.refId || '');
        closeSheet(); render(); toast('Niveau enregistré', 'ok');
      };
    }
  );
}

/* nom de la teinte la plus proche dans la palette de l'appli :
   un point noir sur fond sombre ne se lit pas, « noir » si */
function colorNameOf(hex) {
  const rgb = h => {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(h || '').trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const c = rgb(hex);
  if (!c) return '';
  let best = '', d = Infinity;
  COLORS.forEach(k => {
    const r = rgb(k.h);
    if (!r) return;
    const e = (r[0] - c[0]) ** 2 * 2 + (r[1] - c[1]) ** 2 * 4 + (r[2] - c[2]) ** 2 * 3;
    if (e < d) { d = e; best = k.n; }
  });
  return best;
}

/* ---------- actions ---------- */

function setStatus(id, st) {
  const m = machineById(id);
  if (!m) return;
  if (st === 'idle' || st === 'paused') {
    Native.cancelTimer(m.id);
    m.timer = null;
  }
  m.status = st;
  save(); render();
}

function editMachine(id) {
  const m = id ? machineById(id) : null;
  const pc = (m && m.printer) ? m.printer : {};
  const pk = pc.kind || '';
  sheet(
    '<h2>' + (m ? 'Modifier la machine' : 'Nouvelle machine') + '</h2>' +
    '<div class="sub">Le filament chargé se change directement depuis la fiche machine.</div>' +
    '<label class="field"><span>Nom</span><input type="text" name="name" placeholder="K2 Plus" value="' + esc(m ? m.name : '') + '"></label>' +
    '<label class="field"><span>Modèle</span><input type="text" name="model" placeholder="Creality K2 Plus" value="' + esc(m ? m.model : '') + '"></label>' +
    '<div class="sec-title">Liaison réseau</div>' +
    '<div class="hint" style="margin-bottom:10px">Renseignée, l\'app lit l\'avancement directement sur la machine et te notifie à la vraie fin, sans timer à saisir.</div>' +
    '<label class="field"><span>Marque</span>' +
      '<div class="chips" data-chips="kind">' +
        '<button type="button" class="chip' + (pk === '' ? ' on' : '') + '" data-v="">Aucune</button>' +
        PRINTER_KINDS.map(k =>
          '<button type="button" class="chip' + (pk === k.v ? ' on' : '') + '" data-v="' + k.v + '">' + k.label + '</button>'
        ).join('') +
      '</div>' +
    '</label>' +
    '<label class="field"><span>Adresse IP</span>' +
      '<input type="text" name="host" inputmode="decimal" placeholder="192.168.1.42" value="' + esc(pc.host || '') + '">' +
    '</label>' +
    '<div id="bambu-fields" style="display:' + (pk === 'bambu' ? 'block' : 'none') + '">' +
      '<label class="field"><span>Numéro de série</span>' +
        '<input type="text" name="serial" autocapitalize="characters" placeholder="01P00A…" value="' + esc(pc.serial || '') + '">' +
      '</label>' +
      '<label class="field"><span>Code d\'accès LAN</span>' +
        '<input type="text" name="code" placeholder="8 caractères" value="' + esc(pc.code || '') + '">' +
        '<div class="hint">Écran de l\'imprimante : Réglages → Réseau.</div>' +
      '</label>' +
    '</div>' +
    '<button class="btn wide" style="margin-bottom:6px" data-x="probe">Tester la liaison</button>' +
    '<div id="probe-out" class="hint"></div>' +

    '<div class="sheet-actions">' +
      (m ? '<button class="btn danger" data-x="del">Supprimer</button>' : '') +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Enregistrer</button>' +
    '</div>',
    root => {
      const chips = bindChips(root);
      const bambu = $('#bambu-fields', root);
      $$('[data-chips=kind] .chip', root).forEach(c => c.addEventListener('click', () => {
        bambu.style.display = c.getAttribute('data-v') === 'bambu' ? 'block' : 'none';
      }));

      $('[data-x=probe]', root).onclick = () => {
        const out = $('#probe-out', root);
        const conf = buildPrinter(chips(), formValues(root));
        if (!conf) { out.textContent = 'Choisis une marque et renseigne l\'adresse IP.'; return; }
        out.textContent = 'Connexion…';
        Printers.probe(conf).then(r => {
          if (r && r.ok) {
            out.innerHTML = '<span style="color:var(--ok)">Liaison établie — ' +
              esc(r.state || '?') + (r.percent >= 0 ? ' · ' + r.percent + ' %' : '') +
              (r.file ? ' · ' + esc(r.file) : '') + '</span>';
          } else {
            out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc((r && r.error) || 'sans réponse') + '</span>';
          }
        }).catch(e => { out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>'; });
      };

      $('[data-x=no]', root).onclick = closeSheet;
      const del = $('[data-x=del]', root);
      if (del) del.onclick = () => {
        closeSheet();
        confirmSheet('Supprimer ' + m.name + ' ?', 'La machine disparaît du parc. Le stock n\'est pas touché.', 'Supprimer', () => {
          Native.cancelTimer(m.id);
          DB.machines = DB.machines.filter(x => x.id !== m.id);
          save(); Printers.push(); render(); toast('Machine supprimée');
        }, true);
      };
      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root);
        if (!v.name.trim()) { toast('Il faut un nom', 'bad'); return; }
        const printer = buildPrinter(chips(), v);
        if (m) {
          m.name = v.name.trim(); m.model = v.model.trim();
          m.printer = printer;
        } else {
          DB.machines.push({
            id: uid(), name: v.name.trim(), model: v.model.trim(),
            status: 'idle', timer: null,
            job: null, printer: printer
          });
        }
        save(); Printers.push(); closeSheet(); render(); toast('Enregistré', 'ok');
      };
    }
  );
}

/* ---------- timer ---------- */

function startTimer(id) {
  const m = machineById(id);
  if (!m) return;
  const sp = refMachine(m);
  const openLines = pendingLines();

  sheet(
    '<h2>Lancer sur ' + esc(m.name) + '</h2>' +
    '<div class="sub">' + (sp ? 'Filament : ' + esc(spoolLabel(sp)) : 'Aucun filament renseigné sur cette machine.') + '</div>' +

    '<label class="field"><span>Durée</span>' +
      '<div class="chips" data-chips="preset">' +
        [30, 60, 120, 240, 480, 720].map(min =>
          '<button type="button" class="chip" data-v="' + min + '">' + (min < 60 ? min + ' min' : (min / 60) + ' h') + '</button>'
        ).join('') +
      '</div>' +
    '</label>' +

    '<div class="field-2">' +
      '<label class="field"><span>Heures</span><input type="number" name="h" inputmode="numeric" placeholder="0" min="0"></label>' +
      '<label class="field"><span>Minutes</span><input type="number" name="min" inputmode="numeric" placeholder="0" min="0"></label>' +
    '</div>' +

    '<label class="field"><span>Pièce en cours</span>' +
      '<input type="text" name="label" placeholder="Casque Mando — coque" value="' + esc(m.job ? m.job.label : '') + '">' +
    '</label>' +

    (openLines.length
      ? '<label class="field"><span>Rattacher à une commande</span>' +
          '<select name="lineRef">' +
          '<option value="">Aucune</option>' +
          openLines.map(x =>
            '<option value="' + x.ref + '">' + esc(x.order.name + ' · ' + x.line.title + (x.line.variant ? ' (' + x.line.variant + ')' : '')) + '</option>'
          ).join('') +
          '</select>' +
          '<div class="hint">Le poids restant de la commande sera proposé à la fin.</div>' +
        '</label>'
      : '') +

    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Démarrer</button>' +
    '</div>',

    root => {
      const getChips = bindChips(root);
      $$('.chip', root).forEach(c => c.addEventListener('click', () => {
        const min = parseInt(c.getAttribute('data-v'), 10);
        $('[name=h]', root).value = Math.floor(min / 60) || '';
        $('[name=min]', root).value = min % 60 || '';
      }));
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root);
        const mins = num(v.h) * 60 + num(v.min);
        if (mins <= 0) { toast('Indique une durée', 'bad'); return; }
        const endAt = Date.now() + mins * 60000;

        let job = { label: v.label.trim(), orderId: '', lineId: '', grams: 0 };
        if (v.lineRef) {
          const cut = v.lineRef.indexOf('::');
          const o = orderById(v.lineRef.slice(0, cut));
          const lid = v.lineRef.slice(cut + 2);
          const l = o && (o.lines || []).find(x => x.id === lid);
          if (l) {
            /* poids proposé : ce qui reste de la commande, réparti sur les pièces à faire */
            const aFaire = (o.lines || []).filter(x => !x.done).length || 1;
            job.orderId = o.id; job.lineId = l.id;
            job.grams = Math.round(orderRemaining(o) / aFaire);
            if (!job.label) job.label = l.title + (l.variant ? ' — ' + l.variant : '');
            if (o.status === 'todo') o.status = 'printing';
          }
        }

        m.job = job;
        m.timer = { startedAt: Date.now(), endAt: endAt, dur: mins * 60000 };
        m.status = 'running';

        scheduleFor(m);
        save(); closeSheet(); render();
        toast('Fin prévue à ' + fmtClock(endAt), 'ok');
      };
    }
  );
}

function scheduleFor(m) {
  if (!m.timer) return;
  const title = m.name + ' — impression terminée';
  const text = (m.job && m.job.label) ? m.job.label : 'Le timer est arrivé à son terme.';
  Native.scheduleTimer(m.id, title, text, m.timer.endAt);
  const before = DB.settings.notifyBefore;
  if (before > 0) {
    const pre = m.timer.endAt - before * 60000;
    if (pre > Date.now() + 5000) {
      Native.scheduleTimer(m.id + '-pre', m.name + ' — bientôt fini', 'Fin dans ' + before + ' min · ' + text, pre);
    }
  }
}

function addTime(id, mins) {
  const m = machineById(id);
  if (!m || !m.timer) return;
  m.timer.endAt += mins * 60000;
  if (m.status === 'done') m.status = 'running';
  scheduleFor(m);
  save(); render();
  toast('+' + mins + ' min — fin à ' + fmtClock(m.timer.endAt));
}

function stopTimer(id) {
  const m = machineById(id);
  if (!m) return;
  Native.cancelTimer(m.id);
  Native.cancelTimer(m.id + '-pre');
  m.timer = null; m.status = 'idle'; m.job = null;
  save(); render(); toast('Timer arrêté');
}

/* fin d'impression : on décompte le filament et on solde la ligne de commande */
function finishJob(id) {
  const m = machineById(id);
  if (!m) return;
  const sp = refMachine(m);
  const guess = (m.job && m.job.grams) ? m.job.grams : '';

  sheet(
    '<h2>Impression terminée</h2>' +
    '<div class="sub">' + esc(m.name) + (m.job && m.job.label ? ' · ' + esc(m.job.label) : '') + '</div>' +

    '<label class="field"><span>Filament consommé</span>' +
      '<input type="number" name="grams" inputmode="numeric" placeholder="0" value="' + esc(guess) + '">' +
      '<div class="hint">Normalement le relais s\'en charge tout seul. Ce champ ne sert ' +
        'que pour une impression qu\'il n\'a pas vue — et il faut alors qu\'un seul ' +
        'emplacement de ' + esc(m.name) + ' ait un niveau connu, sinon personne ne sait ' +
        'lequel a imprimé.</div>' +
    '</label>' +

    (m.job && m.job.lineId
      ? '<label class="field row" style="gap:9px;align-items:center">' +
          '<input type="checkbox" name="lineDone" checked style="width:auto">' +
          '<span style="margin:0">Marquer la pièce comme faite dans la commande</span>' +
        '</label>'
      : '') +

    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Valider</button>' +
    '</div>',

    root => {
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root);
        const g = num(v.grams);
        if (g > 0) {
          /* un seul emplacement renseigné : c'est lui. Plusieurs, et on ne
             sait pas lequel a imprimé — on le dit plutôt que de tirer au
             sort sur la bobine de quelqu'un d'autre. */
          const connus = amsConnusDe(m.id);
          if (connus.length === 1) {
            const r = retirerAms(m.id, connus[0].slot, g);
            if (r && r.manque > 0) {
              toast('Il manquait ' + fmtG(r.manque) + ' — la bobine a dû être ' +
                    'changée en route', 'bad');
            }
            const ref = spoolById(connus[0].fiche.refId);
            if (ref && needsRestock(ref)) toast(spoolLabel(ref) + ' : à racheter', 'bad');
          } else if (connus.length === 0) {
            toast('Aucun niveau renseigné sur ' + m.name + ' — rien n\'a été retiré', 'bad');
          } else {
            toast(connus.length + ' bobines renseignées sur ' + m.name + ' — indique ' +
                  'laquelle en tapant dessus', 'bad');
          }
        }
        if (m.job && m.job.orderId && g > 0) {
          const oc = orderById(m.job.orderId);
          if (oc) oc.used = (oc.used || 0) + g;
        }
        if (m.job && m.job.lineId && v.lineDone) {
          const o = orderById(m.job.orderId);
          const l = o && (o.lines || []).find(x => x.id === m.job.lineId);
          if (l) {
            l.done = true;
            if ((o.lines || []).every(x => x.done)) o.status = 'done';
          }
        }
        Native.cancelTimer(m.id);
        Native.cancelTimer(m.id + '-pre');
        m.timer = null; m.job = null; m.status = 'idle';
        save(); closeSheet(); render(); toast('Machine libérée', 'ok');
      };
    }
  );
}

/* lignes de commande encore à imprimer, pour le rattachement */
function pendingLines() {
  const out = [];
  DB.orders.forEach(o => {
    if (o.status === 'done' || o.status === 'shipped') return;
    (o.lines || []).forEach(l => {
      if (!l.done) out.push({ ref: o.id + '::' + l.id, order: o, line: l });
    });
  });
  return out;
}

/* ---------- bandeau d'avertissement natif ---------- */

function nativeWarningBanner() {
  if (!Native.ok()) return '';
  let out = '';
  if (!Native.notificationsOk()) {
    out += '<div class="warn-box" style="margin-bottom:12px">Les notifications sont bloquées : tu ne seras pas prévenu en fin d\'impression. ' +
      '<button class="btn sm" style="margin-top:8px" onclick="Native.askNotifications()">Autoriser</button></div>';
  }
  if (!Native.exactAlarmsOk()) {
    out += '<div class="warn-box" style="margin-bottom:12px">Android n\'autorise pas encore les alarmes précises pour cette app, les notifications risquent d\'être en retard. ' +
      '<button class="btn sm" style="margin-top:8px" onclick="Native.openExactAlarmSettings()">Régler</button></div>';
  }
  return out;
}

function iconPlus() { return '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>'; }
function iconGear() { return '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 4v2M12 18v2M4 12h2M18 12h2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M17.7 6.3l-1.4 1.4M7.7 16.3l-1.4 1.4"/></svg>'; }
function iconSync() { return '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 1-15.5 6.2M3 12A9 9 0 0 1 18.5 5.8"/><path d="M3 4v5h5M21 20v-5h-5"/></svg>'; }

function iconClock() { return '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'; }

/* ---------- calculette : à quelle heure ça finit ? ---------- */

function calculetteFin() {
  sheet(
    '<h2>Heure de fin</h2>' +
    '<div class="sub">La durée annoncée par le trancheur, pour savoir avant de lancer à quelle heure ça se termine.</div>' +

    '<label class="field"><span>Durée d\'impression</span>' +
      '<div class="chips" id="calc-presets">' +
        [30, 60, 120, 240, 480, 720, 1440].map(min =>
          '<button type="button" class="chip" data-min="' + min + '">' +
          (min < 60 ? min + ' min' : (min / 60) + ' h') + '</button>').join('') +
      '</div>' +
    '</label>' +

    '<div class="field-2">' +
      '<label class="field"><span>Heures</span>' +
        '<input type="number" id="calc-h" inputmode="numeric" placeholder="0" min="0"></label>' +
      '<label class="field"><span>Minutes</span>' +
        '<input type="number" id="calc-min" inputmode="numeric" placeholder="0" min="0"></label>' +
    '</div>' +

    '<div class="card tight" style="text-align:center">' +
      '<div class="small muted">Fin prévue</div>' +
      '<div class="clock" id="calc-fin" style="margin:4px 0">—</div>' +
      '<div class="small muted" id="calc-detail">Indique une durée.</div>' +
    '</div>' +

    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Fermer</button>' +
    '</div>',

    root => {
      const h = $('#calc-h', root), mn = $('#calc-min', root);
      const fin = $('#calc-fin', root), detail = $('#calc-detail', root);

      const calcule = () => {
        const mins = num(h.value) * 60 + num(mn.value);
        if (mins <= 0) {
          fin.textContent = '—';
          detail.textContent = 'Indique une durée.';
          return;
        }
        const t = Date.now() + mins * 60000;
        fin.textContent = fmtClock(t);
        const jours = Math.floor((new Date(t).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
        detail.textContent = fmtRemaining(mins) + ' à partir de ' + fmtClock(Date.now()) +
          (jours === 1 ? ' · demain' : jours > 1 ? ' · dans ' + jours + ' jours' : '');
      };

      [h, mn].forEach(el => el.addEventListener('input', calcule));
      $$('#calc-presets .chip', root).forEach(c => c.addEventListener('click', () => {
        const min = parseInt(c.getAttribute('data-min'), 10);
        h.value = Math.floor(min / 60) || '';
        mn.value = min % 60 || '';
        calcule();
      }));

      $('[data-x=no]', root).onclick = closeSheet;
      /* l'horloge de départ avance : on recalcule chaque minute */
      const tic = setInterval(() => { if (!document.body.contains(root)) clearInterval(tic); else calcule(); }, 30000);
      calcule();
      h.focus();
    }
  );
}


/* assemble la liaison réseau depuis les champs de la fiche */
function buildPrinter(chipVals, v) {
  const kind = (chipVals && chipVals.kind) || '';
  const host = (v.host || '').trim();
  if (!kind || !host) return null;
  const p = { kind: kind, host: host };
  if (kind === 'bambu') {
    p.serial = (v.serial || '').trim();
    p.code = (v.code || '').trim();
  }
  return p;
}

/* relève immédiate de toutes les machines branchées */
/* discret : relève de confirmation après une commande, sans le bilan
   habituel — le message de la commande vient déjà de s'afficher */
function pollPrinters(discret) {
  const btn = $('#poll-btn');
  if (btn) btn.textContent = '…';
  Printers.sync()
    .then(() => {
      render();
      if (discret) return;
      const b = Printers.bilan();
      if (b.total === 0) {
        toast('Aucune machine n\'a d\'adresse réseau', 'warn');
      } else if (b.muettes.length === 0) {
        toast(b.total + (b.total > 1 ? ' machines relevées' : ' machine relevée'), 'ok');
      } else if (b.muettes.length === b.total) {
        toast('Aucune machine ne répond — voir le détail sur les cartes', 'bad');
      } else {
        toast((b.total - b.muettes.length) + ' sur ' + b.total + ' — sans réponse : ' +
              b.muettes.join(', '), 'warn');
      }
    })
    .catch(e => { render(); toast('Relève impossible : ' + e.message, 'bad'); });
}
