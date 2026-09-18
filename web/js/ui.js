/* ============================================================
   ui.js — briques d'interface : feuilles, toasts, sélecteurs
   ============================================================ */

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function $(sel, root) { return (root || document).querySelector(sel); }
function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

/* ---------- toast ---------- */

function toast(msg, kind) {
  const host = $('#toast-host');
  const el = document.createElement('div');
  el.className = 'toast' + (kind ? ' ' + kind : '');
  el.textContent = msg;
  host.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .25s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 260);
  }, 2100);
}

/* ---------- feuille modale ---------- */

let sheetCloser = null;

function sheet(html, onMount) {
  closeSheet();
  const bg = document.createElement('div');
  bg.className = 'sheet-bg';
  bg.innerHTML = '<div class="sheet"><div class="sheet-grip"></div>' + html + '</div>';
  bg.addEventListener('click', e => { if (e.target === bg) closeSheet(); });
  $('#sheet-host').appendChild(bg);
  sheetCloser = () => bg.remove();
  if (onMount) onMount($('.sheet', bg));
  return bg;
}

function closeSheet() {
  if (sheetCloser) { sheetCloser(); sheetCloser = null; }
}

function confirmSheet(title, sub, okLabel, onOk, danger) {
  sheet(
    '<h2>' + esc(title) + '</h2>' +
    (sub ? '<div class="sub">' + esc(sub) + '</div>' : '<div class="sp"></div>') +
    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn ' + (danger ? 'danger' : 'primary') + '" data-x="yes">' + esc(okLabel) + '</button>' +
    '</div>',
    root => {
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=yes]', root).onclick = () => { closeSheet(); onOk(); };
    }
  );
}

/* ---------- sélecteurs réutilisables ---------- */

function materialChips(name, current) {
  return '<div class="chips" data-chips="' + name + '">' +
    MATERIALS.map(m =>
      '<button type="button" class="chip' + (m === current ? ' on' : '') + '" data-v="' + esc(m) + '">' + esc(m) + '</button>'
    ).join('') + '</div>';
}

function colorChips(name, current) {
  return '<div class="chips" data-chips="' + name + '">' +
    COLORS.map(c =>
      '<button type="button" class="chip sw' + (c.n === current ? ' on' : '') + '" data-v="' + esc(c.n) + '" title="' + esc(c.n) + '">' +
      '<i style="background:' + c.h + '"></i></button>'
    ).join('') + '</div>' +
    '<div class="hint" data-colorname="' + name + '">' + esc(current || 'Aucune couleur choisie') + '</div>';
}

/* branche les groupes de chips d'une feuille : renvoie un getter de valeurs */
function bindChips(root) {
  const vals = {};
  $$('[data-chips]', root).forEach(group => {
    const key = group.getAttribute('data-chips');
    const on = $('.chip.on', group);
    vals[key] = on ? on.getAttribute('data-v') : '';
    group.addEventListener('click', e => {
      const btn = e.target.closest('.chip');
      if (!btn) return;
      $$('.chip', group).forEach(c => c.classList.remove('on'));
      btn.classList.add('on');
      vals[key] = btn.getAttribute('data-v');
      const label = $('[data-colorname=' + key + ']', root);
      if (label) label.textContent = vals[key];
    });
  });
  return () => vals;
}

function selectOpts(items, current, labelFn, valFn, placeholder) {
  let out = placeholder ? '<option value="">' + esc(placeholder) + '</option>' : '';
  items.forEach(it => {
    const v = valFn(it);
    out += '<option value="' + esc(v) + '"' + (v === current ? ' selected' : '') + '>' + esc(labelFn(it)) + '</option>';
  });
  return out;
}

function spoolSelect(name, current, material) {
  let list = activeSpools().filter(s => spoolTotal(s) > 0);
  if (material) {
    const same = list.filter(s => s.material === material);
    if (same.length) list = same;
  }
  return '<select name="' + name + '">' +
    selectOpts(list, current, s => spoolLabel(s) + ' — ' + fmtG(spoolTotal(s)), s => s.id, 'Aucun') +
    '</select>';
}

/* ---------- blocs d'affichage ---------- */

function badge(cls, text) {
  return '<span class="badge ' + cls + '">' + esc(text) + '</span>';
}

function dot(hex, big) {
  return '<span class="dot' + (big ? ' lg' : '') + '" style="background:' + esc(hex || '#8a8f96') + '"></span>';
}

function emptyState(title, text, btnLabel, btnAction) {
  return '<div class="empty"><h3>' + esc(title) + '</h3><p>' + esc(text) + '</p>' +
    (btnLabel ? '<button class="btn primary" onclick="' + btnAction + '">' + esc(btnLabel) + '</button>' : '') +
    '</div>';
}

function gauge(pct, cls) {
  const w = Math.max(0, Math.min(100, pct));
  return '<div class="gauge"><i class="' + (cls === 'ok' ? '' : cls) + '" style="width:' + w + '%"></i></div>';
}

/* lit les champs nommés d'une feuille */
function formValues(root) {
  const o = {};
  $$('[name]', root).forEach(i => {
    o[i.getAttribute('name')] = i.type === 'checkbox' ? i.checked : i.value;
  });
  return o;
}

function num(v, def) {
  const n = parseFloat(String(v).replace(',', '.'));
  return isNaN(n) ? (def || 0) : n;
}
