/* ============================================================
   app.js — navigation, horloges, démarrage
   ============================================================ */

let TAB = 'machines';

const VIEWS = {
  machines: renderMachines,
  stock: renderStock,
  orders: renderOrders,
  profiles: renderProfiles,
  settings: renderSettings
};

function setTop(title, sub, actions) {
  $('#tb-title').textContent = title;
  $('#tb-sub').textContent = sub || '';
  $('#tb-actions').innerHTML = actions || '';
}

function go(tab) {
  TAB = tab;
  closeSheet();
  render();
  window.scrollTo(0, 0);
}

function render() {
  $('#view').innerHTML = (VIEWS[TAB] || renderMachines)();
  $$('#tabbar .tab').forEach(b => b.classList.toggle('on', b.getAttribute('data-tab') === TAB));
  paintTabBadges();
}

function paintTabBadges() {
  const done = DB.machines.filter(m => m.status === 'done').length;
  const tab = $('#tabbar .tab[data-tab=machines]');
  const old = $('.badge-n', tab);
  if (old) old.remove();
  if (done > 0 && TAB !== 'machines') {
    const b = document.createElement('span');
    b.className = 'badge-n';
    b.textContent = done;
    tab.appendChild(b);
  }
}

/* ---------- horloges ---------- */

function tick() {
  const now = Date.now();
  let needsRender = false;

  DB.machines.forEach(m => {
    if (m.status !== 'running' || !m.timer) return;
    const left = m.timer.endAt - now;
    if (left <= 0) {
      m.status = 'done';
      needsRender = true;
      save();
    } else if (TAB === 'machines') {
      const el = document.getElementById('clk-' + m.id);
      if (el) el.textContent = fmtDur(left);
    }
  });

  if (needsRender) render();
}

/* replanifie les alarmes natives d'après l'état courant
   (après une restauration de sauvegarde par exemple) */
function rescheduleAll() {
  DB.machines.forEach(m => {
    if (m.status === 'running' && m.timer && m.timer.endAt > Date.now()) scheduleFor(m);
  });
}

/* ---------- retour Android ---------- */

window.NMTonBack = function () {
  if (sheetCloser) { closeSheet(); return 1; }
  if (TAB !== 'machines') { go('machines'); return 1; }
  return 0;
};

/* ---------- démarrage ---------- */

function boot() {
  load();

  $$('#tabbar .tab').forEach(b => {
    b.addEventListener('click', () => go(b.getAttribute('data-tab')));
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { load(); render(); }
  });

  render();
  setInterval(tick, 1000);

  if (Native.ok() && !Native.notificationsOk()) {
    setTimeout(() => Native.askNotifications(), 600);
  }
}

document.addEventListener('DOMContentLoaded', boot);
