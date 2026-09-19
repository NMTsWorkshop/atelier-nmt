/* ============================================================
   orders.js — commandes Shopify, poids, besoins matière
   ============================================================ */

const ORDER_STATUS = {
  todo:     { label: 'À imprimer', cls: '' },
  printing: { label: 'En cours',   cls: 'acc' },
  done:     { label: 'Imprimée',   cls: 'ok' },
  shipped:  { label: 'Expédiée',   cls: 'info' }
};

function renderOrders() {
  const todo = DB.orders.filter(o => o.status !== 'shipped' && o.status !== 'done');
  const last = DB.settings.lastSync
    ? 'synchro ' + fmtDayClock(DB.settings.lastSync)
    : 'jamais synchronisé';

  setTop('Commandes',
    DB.orders.length ? todo.length + ' à produire · ' + last : 'Aucune commande',
    '<button class="tb-btn" onclick="addManualOrder()">' + iconPlus() + '</button>' +
    '<button class="tb-btn accent" id="sync-btn" onclick="syncShopify()">' + iconSync() + 'Shopify</button>'
  );

  if (!DB.orders.length) {
    return (DB.settings.token ? '' : '<div class="info-box" style="margin-bottom:12px">Renseigne ta boutique et ton jeton d\'accès dans Réglages pour récupérer les commandes automatiquement.</div>') +
      emptyState('Aucune commande', 'Récupère-les depuis Shopify, ou saisis-en une à la main.', 'Synchroniser Shopify', 'syncShopify()');
  }

  let out = '';
  const groups = [
    ['À produire', DB.orders.filter(o => o.status === 'todo' || o.status === 'printing')],
    ['Imprimées', DB.orders.filter(o => o.status === 'done')],
    ['Expédiées', DB.orders.filter(o => o.status === 'shipped')]
  ];

  groups.forEach(([title, list]) => {
    if (!list.length) return;
    list.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
    out += '<div class="sec-title">' + title + ' · ' + list.length + '</div><div class="stack">';
    out += list.map(orderCard).join('');
    out += '</div>';
  });

  return out;
}

function orderCard(o) {
  const st = ORDER_STATUS[o.status] || ORDER_STATUS.todo;
  const v = orderStockVerdict(o);
  const lines = o.lines || [];
  const doneN = lines.filter(l => l.done).length;
  const totalG = o.grams || 0;
  const noWeight = !totalG;

  return '<div class="card tight click" onclick="openOrder(\'' + o.id + '\')">' +
    '<div class="card-head">' +
      '<div class="grow">' +
        '<div class="card-name">' + esc(o.name) +
          (o.customer ? ' · <span class="muted" style="font-weight:500">' + esc(o.customer) + '</span>' : '') + '</div>' +
        '<div class="card-meta">' + (o.createdAt ? fmtDate(o.createdAt) + ' · ' : '') +
          lines.length + ' pièce' + (lines.length > 1 ? 's' : '') +
          (doneN ? ' · ' + doneN + ' faite' + (doneN > 1 ? 's' : '') : '') +
          (totalG ? ' · ' + fmtG(totalG) : '') +
        '</div>' +
      '</div>' +
      badge(st.cls, st.label) +
    '</div>' +
    '<div class="row wrap" style="margin-top:10px;gap:6px">' +
      (noWeight ? badge('warn', 'Poids à saisir') : badge(v.cls, v.label)) +
      lineMaterialBadges(o) +
    '</div>' +
  '</div>';
}

function lineMaterialBadges(o) {
  return '<span class="badge">' + (o.color ? '<span class="dot" style="background:' + colorHexOf(o.color) + '"></span>' : '') +
    esc(o.material || '?') + (o.color ? ' ' + esc(o.color) : '') + '</span>';
}

/* ---------- détail d'une commande ---------- */

function openOrder(id) {
  const o = orderById(id);
  if (!o) return;
  const v = orderStockVerdict(o);

  sheet(
    '<h2>' + esc(o.name) + '</h2>' +
    '<div class="sub">' + esc(o.customer || 'Commande Shopify') + (o.createdAt ? ' · ' + fmtDate(o.createdAt) : '') +
      (o.country ? ' · ' + esc(o.country) : '') + '</div>' +

    '<div class="chips" style="margin-bottom:14px">' +
      Object.keys(ORDER_STATUS).map(k =>
        '<button type="button" class="chip' + (o.status === k ? ' on' : '') + '" onclick="setOrderStatus(\'' + o.id + '\',\'' + k + '\')">' +
        ORDER_STATUS[k].label + '</button>').join('') +
    '</div>' +

    orderWeightBlock(o) +

    '<div class="card tight" style="margin-bottom:14px">' +
      '<div class="spread"><span class="small muted">Stock pour cette commande</span>' + badge(v.cls, v.label) + '</div>' +
      orderNeeds(o).map(n =>
        '<div class="kv"><span>' + esc(n.material) + (n.color ? ' · ' + esc(n.color) : '') + '</span>' +
        '<b class="mono">' + fmtG(n.grams) + ' / ' + fmtG(stockFor(n.material, n.color)) + '</b></div>'
      ).join('') +
    '</div>' +

    '<div class="sec-title">Pièces</div>' +
    (o.lines || []).map(l => orderLineRow(o, l)).join('') +
    '<div class="small muted" style="margin-top:6px">Touche une pièce pour la marquer comme imprimée.</div>' +

    '<div class="sheet-actions">' +
      '<button class="btn danger" onclick="deleteOrder(\'' + o.id + '\')">Supprimer</button>' +
      '<button class="btn ghost" onclick="closeSheet()">Fermer</button>' +
    '</div>',
    root => {
      const chips = bindChips(root);
      $$('[data-chips=o-material] .chip, [data-chips=o-color] .chip', root).forEach(c =>
        c.addEventListener('click', () => {
          const v = chips();
          o.material = v['o-material'] || o.material;
          o.color = v['o-color'] || o.color;
          save(); render();
        }));
      const g = $('#o-grams', root);
      if (g) g.addEventListener('keydown', e => { if (e.key === 'Enter') saveOrderWeight(o.id); });
    }
  );
}

function orderLineRow(o, l) {
  return '<div class="rowitem tap" onclick="toggleLine(\'' + o.id + '\',\'' + l.id + '\')">' +
    '<div class="grow" style="' + (l.done ? 'opacity:.5' : '') + '">' +
      '<div class="t">' + esc(l.title) + (l.qty > 1 ? ' ×' + l.qty : '') + '</div>' +
      '<div class="s">' + esc(l.variant || '') + '</div>' +
    '</div>' +
    badge(l.done ? 'ok' : '', l.done ? 'Imprimée' : 'À faire') +
  '</div>';
}

/* poids total, matière et couleur : une fois pour toute la commande */
function orderWeightBlock(o) {
  const rem = rememberedOrderWeight(o);
  return '<div class="card tight" style="margin-bottom:14px">' +
    '<label class="field" style="margin-bottom:10px"><span>Poids total de la commande (g)</span>' +
      '<div class="row" style="gap:8px">' +
        '<input type="number" id="o-grams" inputmode="numeric" value="' + esc(o.grams || '') + '" placeholder="' + (rem || 0) + '" style="flex:1">' +
        '<button class="btn sm primary" onclick="saveOrderWeight(\'' + o.id + '\')">OK</button>' +
      '</div>' +
      '<div class="hint">Toutes pièces et quantités comprises.' +
        (rem && rem !== o.grams ? ' Même commande déjà vue : ' + fmtG(rem) + '.' : '') +
        (o.used ? ' Déjà imprimé : ' + fmtG(o.used) + ', reste ' + fmtG(orderRemaining(o)) + '.' : '') +
      '</div>' +
    '</label>' +
    '<label class="field" style="margin-bottom:10px"><span>Matière</span>' + materialChips('o-material', o.material || 'PLA') + '</label>' +
    '<label class="field" style="margin:0"><span>Couleur</span>' + colorChips('o-color', o.color || '') + '</label>' +
  '</div>';
}

function saveOrderWeight(id) {
  const o = orderById(id);
  const el = $('#o-grams');
  if (!o || !el) return;
  const rem = rememberedOrderWeight(o);
  o.grams = num(el.value) || rem || 0;
  rememberOrderWeight(o);
  save(); render(); openOrder(id);
  toast(o.grams ? 'Poids enregistré : ' + fmtG(o.grams) : 'Poids effacé', 'ok');
}

function toggleLine(orderId, lineId) {
  const o = orderById(orderId);
  const l = o && (o.lines || []).find(x => x.id === lineId);
  if (!l) return;
  l.done = !l.done;
  const lines = o.lines || [];
  if (lines.length && lines.every(x => x.done) && o.status !== 'shipped') o.status = 'done';
  else if (o.status === 'done' && lines.some(x => !x.done)) o.status = 'printing';
  save(); render(); openOrder(orderId);
}

function setOrderStatus(id, st) {
  const o = orderById(id);
  if (!o) return;
  o.status = st;
  if (st === 'done' || st === 'shipped') (o.lines || []).forEach(l => l.done = true);
  save(); closeSheet(); render(); toast(ORDER_STATUS[st].label, 'ok');
}

function deleteOrder(id) {
  const o = orderById(id);
  if (!o) return;
  closeSheet();
  confirmSheet('Supprimer ' + o.name + ' ?', 'La commande reste bien sûr dans Shopify.', 'Supprimer', () => {
    DB.orders = DB.orders.filter(x => x.id !== id);
    save(); render(); toast('Commande retirée');
  }, true);
}

function addManualOrder() {
  sheet(
    '<h2>Commande manuelle</h2>' +
    '<div class="sub">Pour une pièce hors boutique : commission, prototype, rechange.</div>' +
    '<label class="field"><span>Référence</span><input type="text" name="name" placeholder="Commission Rémi"></label>' +
    '<label class="field"><span>Client</span><input type="text" name="customer" placeholder="Nom"></label>' +
    '<label class="field"><span>Pièce</span><input type="text" name="title" placeholder="Casque Mando"></label>' +
    '<div class="field-2">' +
      '<label class="field"><span>Poids total (g)</span><input type="number" name="grams" inputmode="numeric" placeholder="450"></label>' +
      '<label class="field"><span>Quantité</span><input type="number" name="qty" inputmode="numeric" value="1"></label>' +
    '</div>' +
    '<label class="field"><span>Matière</span>' + materialChips('material', 'PLA') + '</label>' +
    '<label class="field"><span>Couleur</span>' + colorChips('color', '') + '</label>' +
    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Créer</button>' +
    '</div>',
    root => {
      const chips = bindChips(root);
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root), c = chips();
        if (!v.name.trim() && !v.title.trim()) { toast('Il faut au moins une référence', 'bad'); return; }
        DB.orders.push({
          id: uid(), shopifyId: '', name: v.name.trim() || v.title.trim(),
          customer: v.customer.trim(), createdAt: Date.now(), source: 'manual', status: 'todo',
          grams: num(v.grams), used: 0, material: c.material || 'PLA', color: c.color || '',
          lines: [{
            id: uid(), title: v.title.trim() || v.name.trim(), variant: '',
            qty: parseInt(v.qty, 10) || 1, done: false
          }]
        });
        save(); closeSheet(); render(); toast('Commande ajoutée', 'ok');
      };
    }
  );
}

/* ============================================================
   Synchronisation Shopify (API Admin GraphQL)
   ============================================================ */

/* Requete volontairement minimale : elle ne demande que ce que couvre
   read_orders. Pas de bloc customer (read_customers) ni variant
   (read_products) — variantTitle porte deja la matiere. */
const ORDERS_QUERY =
  'query($n:Int!,$q:String){orders(first:$n,query:$q,sortKey:CREATED_AT,reverse:true){edges{node{' +
  'id name createdAt displayFulfillmentStatus ' +
  'lineItems(first:50){edges{node{id title quantity sku variantTitle}}}' +
  '}}}}';

let syncing = false;

async function syncShopify() {
  if (syncing) return;
  const st = DB.settings;
  if (!st.shop || !st.token) {
    toast('Configure la boutique dans Réglages', 'bad');
    go('settings');
    return;
  }
  if (!Native.ok()) {
    toast('La synchro ne fonctionne que dans l\'app Android', 'bad');
    return;
  }

  syncing = true;
  const btn = $('#sync-btn');
  if (btn) { btn.textContent = 'Synchro…'; btn.disabled = true; }

  try {
    const url = 'https://' + st.shop.replace(/^https?:\/\//, '').replace(/\/$/, '') +
                '/admin/api/' + st.apiVersion + '/graphql.json';
    const res = await nativeHttp('POST', url,
      { 'X-Shopify-Access-Token': st.token, 'Content-Type': 'application/json' },
      JSON.stringify({ query: ORDERS_QUERY, variables: { n: 50, q: 'fulfillment_status:unfulfilled' } })
    );

    if (!res.ok) throw new Error(res.error || ('HTTP ' + res.status));
    const data = JSON.parse(res.body);
    if (data.errors) throw new Error(data.errors[0] && data.errors[0].message || 'Erreur GraphQL');
    if (!data.data || !data.data.orders) throw new Error('Réponse inattendue — vérifie les autorisations du jeton');

    const n = mergeShopifyOrders(data.data.orders.edges.map(e => e.node));
    DB.settings.lastSync = Date.now();
    save(); render();
    toast(n.added ? n.added + ' nouvelle' + (n.added > 1 ? 's' : '') + ' commande' + (n.added > 1 ? 's' : '') : 'Tout est à jour', 'ok');
  } catch (e) {
    toast('Échec : ' + e.message, 'bad');
  } finally {
    syncing = false;
    render();
  }
}

function mergeShopifyOrders(nodes) {
  let added = 0;
  nodes.forEach(nd => {
    const existing = DB.orders.find(o => o.shopifyId === nd.id);
    const cust = nd.customer ? [nd.customer.firstName, nd.customer.lastName].filter(Boolean).join(' ') : '';
    const lines = (nd.lineItems.edges || []).map(e => {
      const li = e.node;
      const variant = li.variantTitle || (li.variant ? li.variant.title : '');
      const base = {
        id: li.id, title: li.title, variant: variant,
        qty: li.quantity || 1, material: materialFromVariant(variant),
        color: '', done: false
      };
      return base;
    });

    if (existing) {
      existing.customer = cust || existing.customer;
      if (nd.shippingAddress) existing.country = nd.shippingAddress.country;
      lines.forEach(nl => {
        if (!(existing.lines || []).some(x => x.id === nl.id)) (existing.lines = existing.lines || []).push(nl);
      });
    } else {
      added++;
      const ref = lines.find(l => l.material) || {};
      const o = {
        id: uid(), shopifyId: nd.id, name: nd.name, customer: cust,
        createdAt: new Date(nd.createdAt).getTime(),
        country: nd.shippingAddress ? nd.shippingAddress.country : '',
        source: 'shopify', status: 'todo', lines: lines,
        grams: 0, used: 0, material: ref.material || 'PLA', color: ''
      };
      o.grams = rememberedOrderWeight(o) || 0;
      DB.orders.push(o);
    }
  });
  return { added: added };
}
