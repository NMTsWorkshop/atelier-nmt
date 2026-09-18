/* ============================================================
   stock.js — références de filament, niveaux, besoins matière

   Une fiche = une référence (marque + matière + couleur), avec le
   nombre de bobines neuves d'un côté et la bobine entamée de l'autre.
   Enregistrer 10 kg de noir prend donc dix secondes, pas dix fiches.
   ============================================================ */

function renderStock() {
  const list = activeSpools();
  const total = list.reduce((t, s) => t + spoolTotal(s), 0);
  const spools = list.reduce((t, s) => t + spoolCount(s), 0);
  const restock = list.filter(needsRestock).length;

  setTop('Stock',
    list.length
      ? fmtG(total) + ' · ' + spools + ' bobine' + (spools > 1 ? 's' : '') +
        (restock ? ' · ' + restock + ' à racheter' : '')
      : 'Aucun filament enregistré',
    '<button class="tb-btn accent" onclick="editSpool()">' + iconPlus() + 'Filament</button>'
  );

  if (!list.length) {
    return emptyState(
      'Pas encore de filament',
      'Une fiche par référence : marque, matière, couleur, et le nombre de bobines que tu as en réserve.',
      'Ajouter du filament', 'editSpool()'
    );
  }

  let out = '';

  /* ---- ce que réclament les commandes en cours ---- */
  const needs = globalNeeds();
  if (needs.length) {
    out += '<div class="sec-title">Ce qu\'il faut pour les commandes</div><div class="card tight">';
    needs.forEach(n => {
      const have = stockFor(n.material, n.color);
      const ok = have >= n.grams;
      const tight = ok && have < n.grams * 1.25;
      out += '<div class="rowitem">' +
        dot(colorHexOf(n.color)) +
        '<div class="grow"><div class="t">' + esc(n.material) + (n.color ? ' · ' + esc(n.color) : '') + '</div>' +
        '<div class="s">' + fmtG(n.grams) + ' nécessaires · ' + fmtG(have) + ' en stock</div></div>' +
        badge(ok ? (tight ? 'warn' : 'ok') : 'bad', ok ? (tight ? 'Juste' : 'OK') : 'Manque ' + fmtG(n.grams - have)) +
        '</div>';
    });
    out += '</div>';
  }

  /* ---- références regroupées par matière ---- */
  const byMat = {};
  list.forEach(s => { (byMat[s.material] = byMat[s.material] || []).push(s); });

  Object.keys(byMat).sort().forEach(mat => {
    const refs = byMat[mat].sort((a, b) => spoolTotal(b) - spoolTotal(a));
    const t = refs.reduce((x, s) => x + spoolTotal(s), 0);
    out += '<div class="sec-title">' + esc(mat) + ' <span class="norm">— ' + fmtG(t) + '</span></div>';
    out += '<div class="stack">' + refs.map(spoolCard).join('') + '</div>';
  });

  const arch = DB.spools.filter(s => s.archived).length;
  if (arch) {
    out += '<div class="sec-title">Archives</div>' +
      '<button class="btn wide ghost" onclick="showArchived()">Voir les ' + arch +
      ' référence' + (arch > 1 ? 's' : '') + ' épuisée' + (arch > 1 ? 's' : '') + '</button>';
  }

  return out;
}

function spoolCard(s) {
  const lvl = spoolLevel(s);
  const used = DB.machines.filter(m => m.filamentId === s.id).map(m => m.name);
  const sealed = s.sealed || 0;
  const open = s.open || 0;

  /* ligne du bas : l'état réel de la réserve, en français d'atelier */
  let detail;
  if (open > 0 && sealed > 0) {
    detail = '~' + fmtG(open) + ' entamés + ' + sealed + ' neuve' + (sealed > 1 ? 's' : '');
  } else if (open > 0) {
    detail = '~' + fmtG(open) + ' sur la bobine entamée, aucune d\'avance';
  } else if (sealed > 0) {
    detail = sealed + ' bobine' + (sealed > 1 ? 's' : '') + ' neuve' + (sealed > 1 ? 's' : '') + ', aucune entamée';
  } else {
    detail = 'Plus rien en stock';
  }

  return '<div class="card tight">' +
    '<div class="card-head tap" onclick="editSpool(\'' + s.id + '\')">' +
      '<div class="row grow" style="gap:9px">' + dot(s.colorHex, true) +
        '<div class="grow">' +
          '<div class="card-name" style="font-size:15px">' + esc(s.color || 'Sans couleur') +
            (spoolCount(s) > 1 ? ' <span class="muted" style="font-weight:500">×' + spoolCount(s) + '</span>' : '') +
          '</div>' +
          '<div class="card-meta">' + esc(s.brand || 'Marque ?') + ' · ' + esc(s.material) +
            (used.length ? ' · sur ' + esc(used.join(', ')) : '') + '</div>' +
        '</div>' +
      '</div>' +
      '<div style="text-align:right">' +
        badge(lvl.cls, lvl.label) +
        '<div class="card-meta mono" style="margin-top:5px">' + fmtG(spoolTotal(s)) + '</div>' +
      '</div>' +
    '</div>' +
    gauge(lvl.pct, lvl.cls) +
    '<div class="spread" style="margin-top:9px">' +
      '<div class="small muted">' + esc(detail) + '</div>' +
      '<button class="btn sm ghost" onclick="quickLevel(\'' + s.id + '\')">Ajuster</button>' +
    '</div>' +
    (needsRestock(s) ? '<div class="fil-line"><span class="grow small" style="color:var(--bad)">À racheter</span></div>' : '') +
  '</div>';
}

/* ---------- ajustements rapides ---------- */

function quickLevel(id) {
  const s = spoolById(id);
  if (!s) return;
  const size = s.spoolSize || 1000;
  const steps = [
    { l: 'Pleine', r: 1 }, { l: '3/4', r: .75 }, { l: 'Moitié', r: .5 },
    { l: '1/4', r: .25 }, { l: 'Bientôt vide', r: .1 }, { l: 'Vide', r: 0 }
  ];

  sheet(
    '<h2>' + esc(spoolLabel(s)) + '</h2>' +
    '<div class="sub">' + fmtG(spoolTotal(s)) + ' au total · ' + (s.sealed || 0) +
      ' bobine' + ((s.sealed || 0) > 1 ? 's' : '') + ' d\'avance</div>' +

    '<div class="sec-title">Bobine entamée</div>' +
    '<div class="chips">' + steps.map(st =>
      '<button type="button" class="chip" data-r="' + st.r + '">' + st.l + '</button>').join('') + '</div>' +
    '<div class="sp"></div>' +
    '<div class="chips">' + [50, 100, 250, 500].map(g =>
      '<button type="button" class="chip" data-g="' + g + '">−' + g + ' g</button>').join('') + '</div>' +

    '<div class="sec-title">Bobines neuves en réserve</div>' +
    '<div class="row" style="gap:10px">' +
      '<button class="btn" data-sealed="-1">−1</button>' +
      '<div class="grow" style="text-align:center">' +
        '<div class="clock" id="sealed-n" style="font-size:26px">' + (s.sealed || 0) + '</div>' +
        '<div class="card-meta">soit ' + fmtG(size) + ' chacune</div>' +
      '</div>' +
      '<button class="btn" data-sealed="1">+1</button>' +
    '</div>' +
    '<div class="sp"></div>' +
    '<div class="chips">' + [5, 10].map(n =>
      '<button type="button" class="chip" data-sealed="' + n + '">+' + n + ' bobines</button>').join('') +
      ((s.sealed || 0) > 0 ? '<button type="button" class="chip" data-open="1">Ouvrir une neuve</button>' : '') +
    '</div>' +

    '<div class="sheet-actions"><button class="btn primary" data-x="no">Terminé</button></div>',

    root => {
      const refresh = () => { $('#sealed-n', root).textContent = s.sealed || 0; save(); };
      $('[data-x=no]', root).onclick = () => { closeSheet(); render(); afterLevel(s); };

      $$('[data-r]', root).forEach(b => b.onclick = () => {
        s.open = Math.round(size * parseFloat(b.getAttribute('data-r')));
        closeSheet(); save(); render(); afterLevel(s);
      });
      $$('[data-g]', root).forEach(b => b.onclick = () => {
        consumeSpool(s, parseInt(b.getAttribute('data-g'), 10));
        closeSheet(); save(); render(); afterLevel(s);
      });
      $$('[data-sealed]', root).forEach(b => b.onclick = () => {
        const d = parseInt(b.getAttribute('data-sealed'), 10);
        s.sealed = Math.max(0, (s.sealed || 0) + d);
        refresh();
        toast(s.sealed + ' bobine' + (s.sealed > 1 ? 's' : '') + ' en réserve');
      });
      const openBtn = $('[data-open]', root);
      if (openBtn) openBtn.onclick = () => {
        if ((s.sealed || 0) <= 0) return;
        s.sealed--;
        s.open = size;
        closeSheet(); save(); render();
        toast('Nouvelle bobine ouverte', 'ok');
      };
    }
  );
}

function afterLevel(s) {
  if (spoolTotal(s) <= 0) {
    confirmSheet('Référence épuisée', spoolLabel(s) + ' — la ranger dans les archives ?', 'Archiver', () => {
      s.archived = true;
      DB.machines.forEach(m => { if (m.filamentId === s.id) m.filamentId = ''; });
      save(); render(); toast('Référence archivée');
    });
  } else if (needsRestock(s)) {
    toast(spoolLabel(s) + ' : à racheter', 'bad');
  }
}

/* ---------- fiche ---------- */

function editSpool(id) {
  const s = id ? spoolById(id) : null;
  sheet(
    '<h2>' + (s ? 'Modifier la référence' : 'Nouveau filament') + '</h2>' +
    (s ? '' : '<div class="sub">Une seule fiche par référence : indique combien de bobines tu as, pas besoin d\'en créer une par une.</div>') +

    '<label class="field"><span>Marque</span>' +
      '<input type="text" name="brand" placeholder="Sunlu, Creality…" value="' + esc(s ? s.brand : '') + '"></label>' +
    '<label class="field"><span>Matière</span>' + materialChips('material', s ? s.material : 'PLA') + '</label>' +
    '<label class="field"><span>Couleur</span>' + colorChips('color', s ? s.color : '') + '</label>' +

    '<div class="field-2">' +
      '<label class="field"><span>Bobines neuves</span>' +
        '<input type="number" name="sealed" inputmode="numeric" min="0" value="' + esc(s ? (s.sealed || 0) : 1) + '">' +
        '<div class="hint">Celles encore sous vide.</div>' +
      '</label>' +
      '<label class="field"><span>Poids d\'une bobine (g)</span>' +
        '<input type="number" name="spoolSize" inputmode="numeric" value="' + esc(s ? s.spoolSize : 1000) + '">' +
        '<div class="hint">1000 le plus souvent.</div>' +
      '</label>' +
    '</div>' +

    '<label class="field"><span>Restant sur la bobine entamée (g)</span>' +
      '<input type="number" name="open" inputmode="numeric" min="0" value="' + esc(s ? (s.open || 0) : 0) + '">' +
      '<div class="hint">Laisse à 0 si aucune n\'est ouverte. Ça s\'ajuste ensuite d\'un geste avec « Ajuster ».</div>' +
    '</label>' +

    '<label class="field"><span>Note</span>' +
      '<input type="text" name="note" placeholder="Matte, silk, lot…" value="' + esc(s ? s.note : '') + '"></label>' +

    '<div class="sheet-actions">' +
      (s ? '<button class="btn danger" data-x="del">Supprimer</button>' : '') +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Enregistrer</button>' +
    '</div>',

    root => {
      const chips = bindChips(root);
      $('[data-x=no]', root).onclick = closeSheet;

      const del = $('[data-x=del]', root);
      if (del) del.onclick = () => {
        closeSheet();
        confirmSheet('Supprimer cette référence ?', spoolLabel(s), 'Supprimer', () => {
          DB.spools = DB.spools.filter(x => x.id !== s.id);
          DB.machines.forEach(m => { if (m.filamentId === s.id) m.filamentId = ''; });
          save(); render(); toast('Référence supprimée');
        }, true);
      };

      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root), c = chips();
        const size = num(v.spoolSize, 1000) || 1000;
        const data = {
          brand: v.brand.trim(),
          material: c.material || 'PLA',
          color: c.color || '',
          colorHex: colorHexOf(c.color),
          spoolSize: size,
          sealed: Math.max(0, Math.round(num(v.sealed))),
          open: Math.max(0, num(v.open)),
          note: v.note.trim()
        };
        if (data.sealed === 0 && data.open === 0) {
          toast('Indique au moins une bobine', 'bad');
          return;
        }
        if (s) {
          Object.assign(s, data);
          if (spoolTotal(s) > 0) s.archived = false;
        } else {
          DB.spools.push(Object.assign({ id: uid(), archived: false, createdAt: Date.now() }, data));
        }
        save(); closeSheet(); render();
        toast(fmtG(data.sealed * size + data.open) + ' enregistrés', 'ok');
      };
    }
  );
}

/* ---------- archives ---------- */

function showArchived() {
  const arch = DB.spools.filter(s => s.archived);
  sheet(
    '<h2>Références épuisées</h2>' +
    '<div class="sub">' + arch.length + ' référence' + (arch.length > 1 ? 's' : '') + ' sortie' +
      (arch.length > 1 ? 's' : '') + ' du stock.</div>' +
    arch.map(s =>
      '<div class="rowitem">' + dot(s.colorHex) +
      '<div class="grow"><div class="t">' + esc(spoolLabel(s)) + '</div>' +
      '<div class="s">' + (s.note ? esc(s.note) + ' · ' : '') + fmtG(s.spoolSize || 1000) + ' la bobine</div></div>' +
      '<button class="btn sm ghost" onclick="restock(\'' + s.id + '\')">Racheté</button>' +
      '</div>'
    ).join('') +
    '<div class="sheet-actions"><button class="btn ghost" data-x="no">Fermer</button></div>',
    root => { $('[data-x=no]', root).onclick = closeSheet; }
  );
}

function restock(id) {
  const s = spoolById(id);
  if (!s) return;
  closeSheet();
  s.archived = false;
  if (spoolTotal(s) <= 0) s.sealed = 1;
  save(); render();
  editSpool(id);
}
