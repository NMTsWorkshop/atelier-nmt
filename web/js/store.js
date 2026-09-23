/* ============================================================
   store.js — état, persistance, modèle métier
   ============================================================ */

const KEY = 'nmt_atelier_v1';

const MATERIALS = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PA-CF', 'Autre'];

const COLORS = [
  { n: 'Noir',      h: '#1b1b1d' },
  { n: 'Blanc',     h: '#f2f2f0' },
  { n: 'Gris',      h: '#8a8f96' },
  { n: 'Argent',    h: '#c7ccd2' },
  { n: 'Rouge',     h: '#c8362f' },
  { n: 'Bordeaux',  h: '#6d1f28' },
  { n: 'Orange',    h: '#e0761f' },
  { n: 'Jaune',     h: '#e3b724' },
  { n: 'Vert',      h: '#3d8a4f' },
  { n: 'Kaki',      h: '#6a6b45' },
  { n: 'Bleu',      h: '#2f5fa8' },
  { n: 'Bleu clair',h: '#6fa8dc' },
  { n: 'Violet',    h: '#6b4a9e' },
  { n: 'Rose',      h: '#d06a92' },
  { n: 'Marron',    h: '#6b4a32' },
  { n: 'Beige',     h: '#cbb994' },
  { n: 'Or',        h: '#b8913c' },
  { n: 'Transparent', h: '#9fb3bf' }
];

const DEFAULT_DB = {
  v: 1,
  machines: [],
  spools: [],
  profiles: [],
  orders: [],
  weights: {},
  settings: {
    shop: '',
    token: '',
    apiVersion: '2026-04',
    notifyBefore: 0,
    lowThreshold: 15,
    lastSync: 0,
    lastUpdateCheck: 0,
    parcSeeded: 0
  }
};

let DB = null;

/* ---------- persistance ---------- */

let memFallback = null;

function load() {
  let raw = null;
  try { raw = localStorage.getItem(KEY); } catch (e) { raw = memFallback; }
  if (!raw) { DB = JSON.parse(JSON.stringify(DEFAULT_DB)); return; }
  try {
    const parsed = JSON.parse(raw);
    DB = Object.assign(JSON.parse(JSON.stringify(DEFAULT_DB)), parsed);
    DB.settings = Object.assign({}, DEFAULT_DB.settings, parsed.settings || {});
  } catch (e) {
    DB = JSON.parse(JSON.stringify(DEFAULT_DB));
  }
  migrate();
}

/* ancien format : une fiche = une bobine ({initial, left}) */
function migrate() {
  /* poids par pièce -> un poids pour toute la commande */
  (DB.orders || []).forEach(o => {
    if (o.grams !== undefined) return;
    const lines = o.lines || [];
    o.grams = lines.reduce((t, l) => t + (l.grams || 0) * (l.qty || 1), 0);
    o.used = lines.filter(l => l.done).reduce((t, l) => t + (l.grams || 0) * (l.qty || 1), 0);
    const ref = lines.find(l => l.material) || lines[0] || {};
    o.material = o.material || ref.material || 'PLA';
    o.color = o.color || ref.color || '';
  });
  (DB.spools || []).forEach(s => {
    if (s.spoolSize === undefined) {
      s.spoolSize = s.initial || 1000;
      s.open = s.left === undefined ? s.spoolSize : s.left;
      s.sealed = 0;
      delete s.initial;
      delete s.left;
    }
  });
}

function save() {
  const raw = JSON.stringify(DB);
  memFallback = raw;
  try { localStorage.setItem(KEY, raw); } catch (e) { /* mode privé / aperçu */ }
}

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

/* ---------- pont natif (APK) ---------- */

const Native = {
  ok() { return typeof window.NMT !== 'undefined'; },

  scheduleTimer(id, title, text, endAt) {
    if (!this.ok()) return false;
    try { window.NMT.scheduleTimer(String(id), String(title), String(text), Number(endAt)); return true; }
    catch (e) { return false; }
  },

  cancelTimer(id) {
    if (!this.ok()) return false;
    try { window.NMT.cancelTimer(String(id)); return true; } catch (e) { return false; }
  },

  notifyNow(title, text) {
    if (!this.ok()) return false;
    try { window.NMT.notifyNow(String(title), String(text)); return true; } catch (e) { return false; }
  },

  saveFile(name, content) {
    if (!this.ok()) return null;
    try { return window.NMT.saveFile(String(name), String(content)); } catch (e) { return null; }
  },

  exactAlarmsOk() {
    if (!this.ok()) return true;
    try { return !!window.NMT.exactAlarmsAllowed(); } catch (e) { return true; }
  },

  openExactAlarmSettings() {
    if (!this.ok()) return;
    try { window.NMT.openExactAlarmSettings(); } catch (e) {}
  },

  notificationsOk() {
    if (!this.ok()) return true;
    try { return !!window.NMT.notificationsAllowed(); } catch (e) { return true; }
  },

  askNotifications() {
    if (!this.ok()) return;
    try { window.NMT.requestNotifications(); } catch (e) {}
  },

  openBatterySettings() {
    if (!this.ok()) return;
    try { window.NMT.openBatterySettings(); } catch (e) {}
  },

  version() {
    if (!this.ok() || typeof window.NMT.appVersion !== 'function') return '—';
    try { return window.NMT.appVersion(); } catch (e) { return '—'; }
  },

  openInstallPermission() {
    if (!this.ok()) return;
    try { window.NMT.openInstallPermission(); } catch (e) {}
  },

  copy(text) {
    if (!this.ok() || typeof window.NMT.copyToClipboard !== 'function') return false;
    try { return !!window.NMT.copyToClipboard(String(text)); } catch (e) { return false; }
  }
};

/* ---------- requêtes HTTP via la coque native ----------
   La WebView ne peut pas appeler l'API Shopify directement (CORS) :
   la couche Java fait la requête et rappelle window.NMTcb. */

let cbSeq = 0;
const cbMap = {};

window.NMTcb = function (id, json) {
  const fn = cbMap[id];
  delete cbMap[id];
  if (!fn) return;
  let res;
  try { res = JSON.parse(json); } catch (e) { res = { ok: false, error: 'réponse illisible' }; }
  fn(res);
};

function nativeHttp(method, url, headers, body) {
  return new Promise((resolve, reject) => {
    if (!Native.ok()) { reject(new Error('coque native absente')); return; }
    const id = 'c' + (++cbSeq);
    cbMap[id] = resolve;
    setTimeout(() => {
      if (cbMap[id]) { delete cbMap[id]; reject(new Error('délai dépassé')); }
    }, 30000);
    try {
      window.NMT.httpAsync(method, url, JSON.stringify(headers || {}), body || '', id);
    } catch (e) {
      delete cbMap[id];
      reject(new Error(String(e)));
    }
  });
}

/* ---------- appels natifs avec rappel ---------- */

function nativeCall(fn, args) {
  return new Promise((resolve, reject) => {
    if (!Native.ok() || typeof window.NMT[fn] !== 'function') {
      reject(new Error('indisponible hors de l\'application'));
      return;
    }
    const id = 'c' + (++cbSeq);
    cbMap[id] = resolve;
    setTimeout(() => {
      if (cbMap[id]) { delete cbMap[id]; reject(new Error('délai dépassé')); }
    }, 60000);
    try {
      window.NMT[fn].apply(window.NMT, (args || []).concat([id]));
    } catch (e) {
      delete cbMap[id];
      reject(new Error(String(e)));
    }
  });
}

/* ---------- imprimantes du réseau local ---------- */

let PSTATES = {};

const Printers = {

  ok() {
    return Native.ok() && typeof window.NMT.printerStates === 'function';
  },

  /* relit le dernier état connu, tel que la relève l'a stocké */
  refresh() {
    if (!this.ok()) return PSTATES;
    try { PSTATES = JSON.parse(window.NMT.printerStates() || '{}'); }
    catch (e) { PSTATES = {}; }
    return PSTATES;
  },

  /* état d'une machine, ou null si injoignable ou jamais relevée */
  state(machineId) {
    const s = PSTATES[machineId];
    if (!s || !s.ok) return null;
    return s;
  },

  /* erreur de la dernière relève, pour l'afficher telle quelle */
  error(machineId) {
    const s = PSTATES[machineId];
    return (s && !s.ok) ? (s.error || 'injoignable') : '';
  },

  /* vrai quand la panne vient de la fiche, pas du réseau */
  reglage(machineId) {
    const s = PSTATES[machineId];
    return !!(s && !s.ok && s.reglage);
  },

  /* comptage après une relève : combien répondent, et qui ne répond pas */
  bilan() {
    const branchees = DB.machines.filter(m => m.printer && m.printer.kind && m.printer.host);
    const muettes = branchees.filter(m => !this.state(m.id) || (PSTATES[m.id] || {}).stale);
    return { total: branchees.length, muettes: muettes.map(m => m.name) };
  },

  /* la configuration est dérivée des machines : une seule source de vérité */
  push() {
    if (!this.ok()) return;
    const conf = DB.machines
      .filter(m => m.printer && m.printer.kind && m.printer.host)
      .map(m => Object.assign({ machineId: m.id, name: m.name }, m.printer));
    try { window.NMT.savePrinters(JSON.stringify(conf)); } catch (e) {}
  },

  sync() {
    return nativeCall('syncPrinters', []).then(res => {
      PSTATES = res && typeof res === 'object' ? res : {};
      return PSTATES;
    });
  },

  probe(conf) {
    return nativeCall('probePrinter', [JSON.stringify(conf)]);
  },

  /* un relevé reste affiché 24 h : hors du wifi, c'est lui qui fait foi,
     la fin estimée continue d'avancer à partir de l'heure où il a été pris */
  fresh(machineId) {
    const s = PSTATES[machineId];
    return !!(s && s.at && Date.now() - s.at < 24 * 3600000);
  },

  /* vrai quand la machine ne répond plus et qu'on affiche l'ancien relevé */
  stale(machineId) {
    const s = PSTATES[machineId];
    return !!(s && s.ok && (s.stale || Date.now() - s.at > 40 * 60000));
  },

  /* heure de fin prévue, calculée depuis le relevé et non depuis maintenant */
  endAt(machineId) {
    const s = PSTATES[machineId];
    if (!s || !s.ok) return 0;
    if (s.endAt) return s.endAt;
    return s.remaining > 0 && s.at ? s.at + s.remaining * 60000 : 0;
  }
};

/* ---------- relais de l'atelier ---------- */

const Relais = {
  ok() { return Native.ok() && typeof window.NMT.relayTopic === 'function'; },

  sujet() {
    if (!this.ok()) return '';
    try { return window.NMT.relayTopic() || ''; } catch (e) { return ''; }
  },

  save(sujet) {
    if (!this.ok()) return false;
    try { window.NMT.saveRelay(String(sujet || '')); return true; } catch (e) { return false; }
  },

  test() { return nativeCall('testRelay', []); },

  /* lots : tableau de chaines JSON, une par message ntfy */
  publier(lots) { return nativeCall('publishCompta', [JSON.stringify(lots)]); }
};

/* ============================================================
   Compta — ce que l'app envoie au tableur Argent.xlsx
   ============================================================

   L'app publie ses commandes sur le canal du relais ; un script resté
   sur le PC les reprend et ajoute les lignes manquantes au tableur.
   Rien ne revient dans l'autre sens : le tableur garde tout ce qui y
   est saisi à la main.

   ntfy limite un message à quelques kilo-octets, d'où les lots. Chaque
   envoi porte la liste complète : un seul lot récent suffit au script,
   même s'il a manqué les précédents. */

const COMPTA_STATUTS = { todo: 'not started', printing: 'started', done: 'finished', shipped: 'delivered' };
const COMPTA_TAILLE_LOT = 3000;   // octets par message, marge comprise

function comptaRef(o) {
  return o.shopifyId ? (o.name || o.shopifyId) : 'M-' + o.id;
}

function comptaLigne(o) {
  const l = { r: comptaRef(o), d: o.createdAt || Date.now(), s: COMPTA_STATUTS[o.status] || 'not started' };
  if (o.customer) l.n = o.customer;
  if (o.country) l.p = o.country;
  if (o.price) l.e = o.price;
  if (o.grams) l.g = o.grams;
  if (o.material) l.m = o.material;
  const objet = (o.lines || []).map(x => x.title + (x.qty > 1 ? ' x' + x.qty : '')).join(' + ');
  if (objet) l.o = objet.slice(0, 60);
  return l;
}

/* découpe la liste en messages qui tiennent dans une notification ntfy */
function comptaLots(commandes) {
  const lignes = commandes.map(comptaLigne);
  const paquets = [];
  let cour = [], taille = 0;
  lignes.forEach(l => {
    const n = JSON.stringify(l).length + 1;
    if (cour.length && taille + n > COMPTA_TAILLE_LOT) { paquets.push(cour); cour = []; taille = 0; }
    cour.push(l); taille += n;
  });
  if (cour.length) paquets.push(cour);

  const at = Date.now();
  return paquets.map((p, i) =>
    JSON.stringify({ t: 'compta', at: at, lot: i + 1, lots: paquets.length, c: p }));
}

let comptaEnAttente = null;

/* Envoi immédiat. Renvoie le nombre de commandes parties. */
async function comptaEnvoyer() {
  if (!Relais.ok() || !Relais.sujet()) throw new Error('aucun relais configuré');
  const commandes = DB.orders.slice().sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
  if (!commandes.length) return 0;
  const lots = comptaLots(commandes);
  const res = await Relais.publier(lots);
  if (!res || !res.ok) throw new Error((res && res.error) || 'envoi refusé');
  DB.settings.comptaSentAt = Date.now();
  save();
  return commandes.length;
}

/* Envoi discret, groupé, après une modification de commande. */
function comptaPlanifier() {
  if (!Relais.ok() || !Relais.sujet()) return;
  clearTimeout(comptaEnAttente);
  comptaEnAttente = setTimeout(() => { comptaEnvoyer().catch(() => {}); }, 5000);
}

const PRINTER_KINDS = [
  { v: 'bambu', label: 'Bambu Lab' },
  { v: 'moonraker', label: 'Creality / Klipper' }
];

function fmtRemaining(min) {
  if (min == null || min < 0) return '';
  if (min < 60) return min + ' min';
  const h = Math.floor(min / 60), m = min % 60;
  return h + ' h ' + String(m).padStart(2, '0');
}

/* ---------- parc de l'atelier, pré-rempli ----------
   Les adresses sont privées (10.x) et sans valeur hors du réseau.
   Les codes d'accès Bambu, eux, sont des mots de passe : ils ne
   figurent pas ici et se saisissent une fois sur le téléphone. */

const PARC = [
  { name: 'K2 Plus',    model: 'Creality K2 Plus',
    printer: { kind: 'moonraker', host: '10.1.3.3' } },
  { name: 'Creality 2', model: 'Creality',
    printer: { kind: 'moonraker', host: '10.1.3.2' } },
  { name: 'Bambu 1',    model: 'Bambu Lab P1S',
    printer: { kind: 'bambu', host: '10.1.3.11', serial: '01P00C462500170', code: '' } },
  { name: 'Bambu 2',    model: 'Bambu Lab P1S',
    printer: { kind: 'bambu', host: '10.1.3.10', serial: '01P09C510800409', code: '' } }
];

/* Posé une seule fois. Complète les machines déjà créées plutôt que
   d'en ajouter en double, et ne touche jamais à un code déjà saisi. */
function seedParc() {
  if (DB.settings.parcSeeded) return;
  DB.settings.parcSeeded = Date.now();

  PARC.forEach(def => {
    const existing =
      DB.machines.find(m => m.printer && m.printer.host === def.printer.host) ||
      DB.machines.find(m => (m.name || '').trim().toLowerCase() === def.name.toLowerCase());

    if (existing) {
      /* un code déjà saisi ne se perd pas — mais seulement s'il a
         encore un sens, c'est-à-dire sur une Bambu */
      const kept = (def.printer.kind === 'bambu' && existing.printer)
        ? (existing.printer.code || '') : '';
      existing.printer = Object.assign({}, def.printer);
      if (kept) existing.printer.code = kept;
      if (!existing.model) existing.model = def.model;
    } else {
      DB.machines.push({
        id: uid(), name: def.name, model: def.model,
        profileId: '', filamentId: '', status: 'idle',
        timer: null, job: null,
        printer: Object.assign({}, def.printer)
      });
    }
  });

  save();
}

/* ---------- helpers modèle ---------- */

function machineById(id) { return DB.machines.find(m => m.id === id) || null; }
function spoolById(id) { return DB.spools.find(s => s.id === id) || null; }
function profileById(id) { return DB.profiles.find(p => p.id === id) || null; }
function orderById(id) { return DB.orders.find(o => o.id === id) || null; }

function activeSpools() { return DB.spools.filter(s => !s.archived); }

/* Une entrée de stock = une référence de filament, pas une bobine physique :
   - sealed : le nombre de bobines encore sous vide
   - open   : ce qui reste, en grammes, sur celle qui est entamée
   C'est ce qui permet d'enregistrer « 10 kg de noir » d'un coup. */

function spoolTotal(s) {
  return Math.max(0, s.sealed || 0) * (s.spoolSize || 1000) + Math.max(0, s.open || 0);
}

function spoolCount(s) {
  return (s.sealed || 0) + ((s.open || 0) > 0 ? 1 : 0);
}

/* niveau de la bobine entamée : on raisonne en paliers, pas au gramme près */
function spoolLevel(s) {
  const size = s.spoolSize || 1000;
  const open = s.open || 0;
  const sealed = s.sealed || 0;

  if (spoolTotal(s) <= 0) return { key: 'empty', label: 'Vide', cls: 'bad', pct: 0 };
  if (open <= 0) return { key: 'sealed', label: 'Neuve', cls: 'ok', pct: 100 };

  const pct = (open / size) * 100;
  /* avec des bobines d'avance, une fin de bobine n'a rien d'alarmant */
  const soft = sealed > 0;
  if (pct < DB.settings.lowThreshold)
    return { key: 'low', label: 'Bientôt vide', cls: soft ? 'warn' : 'bad', pct };
  if (pct < 40) return { key: 'quarter', label: 'Faible', cls: soft ? 'ok' : 'warn', pct };
  if (pct < 75) return { key: 'half', label: 'Entamée', cls: 'ok', pct };
  return { key: 'full', label: 'Pleine', cls: 'ok', pct };
}

/* à racheter : plus de bobine d'avance et l'entamée touche à sa fin */
function needsRestock(s) {
  return (s.sealed || 0) === 0 &&
         (s.open || 0) < (s.spoolSize || 1000) * (DB.settings.lowThreshold / 100);
}

/* ouvre une bobine neuve si besoin, puis retire les grammes demandés.
   Renvoie ce qu'on n'a pas pu couvrir et le nombre de bobines ouvertes. */
function consumeSpool(s, grams) {
  const size = s.spoolSize || 1000;
  let left = grams, opened = 0;

  while (left > 0) {
    if ((s.open || 0) <= 0) {
      if ((s.sealed || 0) <= 0) break;
      s.sealed--;
      s.open = size;
      opened++;
    }
    const take = Math.min(s.open, left);
    s.open -= take;
    left -= take;
  }
  if (s.open < 0) s.open = 0;
  return { missing: left, opened: opened };
}

function spoolLabel(s) {
  if (!s) return 'Aucun filament';
  return [s.brand, s.material, s.color].filter(Boolean).join(' · ');
}

function colorHexOf(name) {
  const c = COLORS.find(c => c.n.toLowerCase() === String(name || '').toLowerCase());
  return c ? c.h : '#8a8f96';
}

/* stock disponible pour un couple matière + couleur (en g, approximatif) */
function stockFor(material, color) {
  return activeSpools()
    .filter(s => s.material === material && (!color || s.color === color))
    .reduce((t, s) => t + spoolTotal(s), 0);
}

/* mémorisation du poids d'une commande : même contenu = même poids.
   La signature, c'est la liste des pièces et de leurs quantités. */
function orderSignature(o) {
  return (o.lines || [])
    .map(l => (l.title || '') + '||' + (l.variant || '') + '×' + (l.qty || 1))
    .sort().join('##');
}

function rememberedOrderWeight(o) {
  const w = DB.weights['cmd:' + orderSignature(o)];
  if (typeof w === 'number') return w;
  /* ancien mémo, par pièce : on additionne s'il couvre toutes les pièces */
  const lines = o.lines || [];
  if (!lines.length) return null;
  let t = 0;
  for (const l of lines) {
    const x = rememberedWeight(l);
    if (x == null) return null;
    t += x * (l.qty || 1);
  }
  return t;
}

function rememberOrderWeight(o) {
  if (o.grams > 0 && (o.lines || []).length) DB.weights['cmd:' + orderSignature(o)] = o.grams;
}

/* ce qui reste à imprimer d'une commande, en grammes */
function orderRemaining(o) {
  if (o.status === 'done' || o.status === 'shipped') return 0;
  return Math.max(0, (o.grams || 0) - (o.used || 0));
}

/* clé de mémorisation des poids : produit + variante */
function weightKey(line) {
  return (line.title || '') + '||' + (line.variant || '');
}

function rememberedWeight(line) {
  const w = DB.weights[weightKey(line)];
  return typeof w === 'number' ? w : null;
}

function rememberWeight(line, grams) {
  if (grams > 0) { DB.weights[weightKey(line)] = grams; }
}

/* besoins matière d'une commande, regroupés par matière + couleur */
function orderNeeds(order) {
  const g = orderRemaining(order);
  if (!g) return [];
  return [{ material: order.material || '?', color: order.color || '', grams: g }];
}

/* verdict stock d'une commande */
function orderStockVerdict(order) {
  const needs = orderNeeds(order);
  if (!needs.length) return { cls: '', label: 'Poids à saisir', short: 'Poids ?' };
  let worst = 'ok', missing = 0;
  needs.forEach(n => {
    const have = stockFor(n.material, n.color);
    if (have < n.grams) { worst = 'bad'; missing += n.grams - have; }
    else if (have < n.grams * 1.25 && worst !== 'bad') { worst = 'warn'; }
  });
  if (worst === 'bad') return { cls: 'bad', label: 'Manque ~' + fmtG(missing), short: 'Manque ' + fmtG(missing) };
  if (worst === 'warn') return { cls: 'warn', label: 'Stock juste', short: 'Juste' };
  return { cls: 'ok', label: 'Stock OK', short: 'OK' };
}

/* besoins de TOUTES les commandes à produire */
function globalNeeds() {
  const map = {};
  DB.orders.forEach(o => {
    if (o.status === 'done' || o.status === 'shipped') return;
    orderNeeds(o).forEach(n => {
      const k = n.material + '|' + n.color;
      if (!map[k]) map[k] = { material: n.material, color: n.color, grams: 0 };
      map[k].grams += n.grams;
    });
  });
  return Object.values(map).sort((a, b) => b.grams - a.grams);
}

/* ---------- formats ---------- */

function fmtG(g) {
  g = Math.round(g);
  if (g >= 1000) {
    const kg = g / 1000;
    return (kg >= 10 ? kg.toFixed(1) : kg.toFixed(2))
      .replace(/\.?0+$/, '')
      .replace('.', ',') + ' kg';
  }
  return g + ' g';
}

function fmtDur(ms) {
  if (ms < 0) ms = 0;
  const t = Math.floor(ms / 1000);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  if (h > 0) return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  return m + ':' + String(s).padStart(2, '0');
}

function fmtDurShort(ms) {
  const t = Math.floor(ms / 60000);
  const h = Math.floor(t / 60), m = t % 60;
  if (h > 0) return h + ' h ' + (m ? String(m).padStart(2, '0') : '00');
  return m + ' min';
}

function fmtClock(ts) {
  const d = new Date(ts);
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function fmtDate(ts) {
  const d = new Date(ts);
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
}

function fmtDayClock(ts) {
  const d = new Date(ts), now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const tomorrow = new Date(now.getTime() + 86400000).toDateString() === d.toDateString();
  if (sameDay) return fmtClock(ts);
  if (tomorrow) return 'demain ' + fmtClock(ts);
  return fmtDate(ts) + ' ' + fmtClock(ts);
}

/* détecte la matière dans un titre de variante Shopify
   ex. "Covert / Without Visor / PLA" · "DC-15s / PETG / Yes" */
function materialFromVariant(variantTitle) {
  const parts = String(variantTitle || '').split('/').map(p => p.trim());
  for (const p of parts) {
    const up = p.toUpperCase().replace(/\s+/g, '');
    const hit = MATERIALS.find(m => m !== 'Autre' && m.replace('-', '') === up.replace('-', ''));
    if (hit) return hit;
  }
  return '';
}
