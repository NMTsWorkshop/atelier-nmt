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

  return warn + '<div class="stack">' + DB.machines.map(machineCard).join('') + '</div>';
}

function machineCard(m) {
  const sp = spoolById(m.filamentId);
  const pr = profileById(m.profileId);
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
      '<button class="btn sm ghost" onclick="pollPrinters()">Actualiser</button>' +
      '<button class="btn sm primary" onclick="finishJob(\'' + m.id + '\')">Terminer</button>';
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

/* enveloppe commune : en-tête, ligne filament, rangée d'actions */
function machineShell(m, cls, clock, sub, actions, sp, live) {
  const pr = profileById(m.profileId);
  const lvl = sp ? spoolLevel(sp) : null;
  const err = (m.printer && m.printer.host) ? Printers.error(m.id) : '';

  return '<div class="' + cls + '">' +
    '<div class="card-head tap" onclick="editMachine(\'' + m.id + '\')">' +
      '<div class="grow">' +
        '<div class="card-name">' + esc(m.name) +
          (live
            ? (Printers.stale(m.id)
                ? ' <span class="badge" style="vertical-align:middle">relevé de ' + fmtDayClock(live.at) + '</span>'
                : ' <span class="badge ok" style="vertical-align:middle">en direct</span>')
            : '') +
        '</div>' +
        '<div class="card-meta">' + esc(m.model || '—') + (pr ? ' · ' + esc(pr.name) : '') + '</div>' +
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
    amsLine(live) +
    '<div class="fil-line">' +
      (sp
        ? dot(sp.colorHex) + '<span class="grow nowrap">' + esc(spoolLabel(sp)) + '</span>' +
          badge(lvl.cls, lvl.label)
        : '<span class="grow muted">Aucun filament renseigné</span>') +
      '<button class="btn sm ghost" onclick="loadFilament(\'' + m.id + '\')">Changer</button>' +
    '</div>' +
    '<div class="row wrap" style="margin-top:12px">' + actions + '</div>' +
  '</div>';
}

/* ce que l'AMS rapporte, tel quel — la couleur vient de la machine */
function amsLine(live) {
  if (!live || !live.ams || !live.ams.length) return '';
  return '<div class="row wrap" style="gap:6px;margin-top:10px">' +
    live.ams.map(t =>
      t.inconnue
        ? '<span class="badge" title="Bobine présente mais non renseignée sur la machine">? non renseignée</span>'
        : '<span class="badge">' +
            (t.color ? '<span class="dot" style="background:' + esc(t.color) + '"></span>' : '') +
            esc(t.type) + (t.color ? ' ' + esc(colorNameOf(t.color).toLowerCase()) : '') + '</span>'
    ).join('') + '</div>';
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
    '<label class="field"><span>Profil d\'impression par défaut</span>' +
      '<select name="profileId">' + selectOpts(DB.profiles, m ? m.profileId : '', p => p.name, p => p.id, 'Aucun') + '</select>' +
    '</label>' +

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
          m.name = v.name.trim(); m.model = v.model.trim(); m.profileId = v.profileId;
          m.printer = printer;
        } else {
          DB.machines.push({
            id: uid(), name: v.name.trim(), model: v.model.trim(),
            profileId: v.profileId, filamentId: '', status: 'idle', timer: null,
            job: null, printer: printer
          });
        }
        save(); Printers.push(); closeSheet(); render(); toast('Enregistré', 'ok');
      };
    }
  );
}

function loadFilament(id) {
  const m = machineById(id);
  if (!m) return;
  const list = activeSpools().filter(s => spoolTotal(s) > 0);
  if (!list.length) {
    confirmSheet('Aucun filament en stock', 'Ajoute d\'abord une référence dans l\'onglet Stock.', 'Ajouter du filament', () => {
      go('stock'); editSpool();
    });
    return;
  }
  sheet(
    '<h2>Filament sur ' + esc(m.name) + '</h2>' +
    '<div class="sub">Ce que tu renseignes ici sert au calcul de stock quand l\'impression est terminée.</div>' +
    '<label class="field"><span>Bobine chargée</span>' + spoolSelect('filamentId', m.filamentId) + '</label>' +
    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Valider</button>' +
    '</div>',
    root => {
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        m.filamentId = formValues(root).filamentId;
        save(); closeSheet(); render(); toast('Filament mis à jour', 'ok');
      };
    }
  );
}

/* ---------- timer ---------- */

function startTimer(id) {
  const m = machineById(id);
  if (!m) return;
  const sp = spoolById(m.filamentId);
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
  const sp = spoolById(m.filamentId);
  const guess = (m.job && m.job.grams) ? m.job.grams : '';

  sheet(
    '<h2>Impression terminée</h2>' +
    '<div class="sub">' + esc(m.name) + (m.job && m.job.label ? ' · ' + esc(m.job.label) : '') + '</div>' +

    (sp
      ? '<label class="field"><span>Filament consommé</span>' +
          '<input type="number" name="grams" inputmode="numeric" placeholder="0" value="' + esc(guess) + '">' +
          '<div class="hint">Déduit de ' + esc(spoolLabel(sp)) + ' — il reste ' + fmtG(spoolTotal(sp)) + '. Laisse vide si tu ne veux rien déduire.</div>' +
        '</label>'
      : '<div class="warn-box">Aucun filament n\'est associé à cette machine, rien ne sera déduit du stock.</div><div class="sp"></div>'
    ) +

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
        if (sp && g > 0) {
          const r = consumeSpool(sp, g);
          if (r.missing > 0) {
            toast('Il manquait ' + fmtG(r.missing) + ' de ' + spoolLabel(sp), 'bad');
          } else if (r.opened > 0) {
            toast(r.opened > 1 ? r.opened + ' bobines entamées' : 'Nouvelle bobine entamée');
          }
          if (spoolTotal(sp) <= 0) toast(spoolLabel(sp) + ' est épuisé', 'bad');
          else if (needsRestock(sp)) toast(spoolLabel(sp) + ' : à racheter', 'bad');
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
function pollPrinters() {
  const btn = $('#poll-btn');
  if (btn) btn.textContent = '…';
  Printers.sync()
    .then(() => {
      render();
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
