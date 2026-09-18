/* ============================================================
   settings.js — Shopify, notifications, sauvegarde
   ============================================================ */

function renderSettings() {
  const st = DB.settings;
  setTop('Réglages', Native.ok() ? 'Application Android' : 'Aperçu navigateur', '');

  let out = '';

  /* ---- Shopify ---- */
  out += '<div class="sec-title">Boutique Shopify</div>' +
    '<div class="card">' +
      '<label class="field"><span>Domaine myshopify</span>' +
        '<input type="text" name="shop" value="' + esc(st.shop) + '" placeholder="hedjfd-9e.myshopify.com" autocapitalize="off" autocorrect="off">' +
        '<div class="hint">Le domaine technique, pas nmtsworkshop.com.</div>' +
      '</label>' +
      '<label class="field"><span>Jeton d\'accès Admin API</span>' +
        '<input type="password" name="token" value="' + esc(st.token) + '" placeholder="shpat_…" autocapitalize="off" autocorrect="off">' +
        '<div class="hint">Jeton de l\'app Atelier NMT. Seule autorisation nécessaire : read_orders. Le jeton reste sur le téléphone.</div>' +
      '</label>' +
      '<label class="field"><span>Version d\'API</span>' +
        '<input type="text" name="apiVersion" value="' + esc(st.apiVersion) + '" placeholder="2026-04">' +
      '</label>' +
      '<div class="btn-row">' +
        '<button class="btn" onclick="saveSettings()">Enregistrer</button>' +
        '<button class="btn primary" onclick="testShopify()">Tester</button>' +
      '</div>' +
    '</div>';

  /* ---- notifications ---- */
  out += '<div class="sec-title">Notifications</div>' +
    '<div class="card">' +
      '<label class="field"><span>Prévenir avant la fin</span>' +
        '<select name="notifyBefore">' +
          [0, 5, 10, 15, 30].map(v =>
            '<option value="' + v + '"' + (st.notifyBefore === v ? ' selected' : '') + '>' +
            (v === 0 ? 'Non, seulement à la fin' : v + ' minutes avant') + '</option>').join('') +
        '</select>' +
      '</label>' +
      '<label class="field"><span>Seuil « bientôt vide »</span>' +
        '<select name="lowThreshold">' +
          [10, 15, 20, 25].map(v =>
            '<option value="' + v + '"' + (st.lowThreshold === v ? ' selected' : '') + '>' + v + ' % de la bobine</option>').join('') +
        '</select>' +
      '</label>' +
      '<div class="btn-row">' +
        '<button class="btn" onclick="saveSettings()">Enregistrer</button>' +
        '<button class="btn primary" onclick="testNotif()">Tester</button>' +
      '</div>' +
      (Native.ok()
        ? '<div class="sp"></div><div class="hint">Si les notifications arrivent en retard, retire l\'app de l\'optimisation de batterie.' +
          '<br><button class="btn sm" style="margin-top:9px" onclick="Native.openBatterySettings()">Ouvrir les réglages batterie</button></div>'
        : '<div class="sp"></div><div class="warn-box">Dans un navigateur, les notifications en arrière-plan ne fonctionnent pas. C\'est tout l\'intérêt de la version Android.</div>')
    + '</div>';

  /* ---- données ---- */
  const counts = DB.machines.length + ' machines · ' + activeSpools().length + ' bobines · ' +
                 DB.orders.length + ' commandes · ' + DB.profiles.length + ' profils';
  out += '<div class="sec-title">Sauvegarde</div>' +
    '<div class="card">' +
      '<div class="small muted" style="margin-bottom:12px">' + esc(counts) + '</div>' +
      '<div class="btn-row">' +
        '<button class="btn" onclick="exportData()">Exporter</button>' +
        '<button class="btn" onclick="importData()">Importer</button>' +
      '</div>' +
      '<div class="sp"></div>' +
      '<button class="btn wide danger" onclick="resetData()">Tout effacer</button>' +
    '</div>';

  out += '<div class="sec-title">À propos</div>' +
    '<div class="card">' +
      '<div class="kv"><span>Application</span><b>Atelier NMT</b></div>' +
      '<div class="kv"><span>Version</span><b>1.0</b></div>' +
      '<div class="kv"><span>Données</span><b>Stockées sur l\'appareil</b></div>' +
    '</div>';

  return out;
}

function saveSettings() {
  const v = formValues($('#view'));
  DB.settings.shop = (v.shop || '').trim();
  DB.settings.token = (v.token || '').trim();
  DB.settings.apiVersion = (v.apiVersion || '2026-04').trim();
  DB.settings.notifyBefore = parseInt(v.notifyBefore, 10) || 0;
  DB.settings.lowThreshold = parseInt(v.lowThreshold, 10) || 15;
  save();
  toast('Réglages enregistrés', 'ok');
}

async function testShopify() {
  saveSettings();
  const st = DB.settings;
  if (!st.shop || !st.token) { toast('Domaine et jeton obligatoires', 'bad'); return; }
  if (!Native.ok()) { toast('Test possible seulement dans l\'app Android', 'bad'); return; }
  toast('Connexion…');
  try {
    const url = 'https://' + st.shop.replace(/^https?:\/\//, '').replace(/\/$/, '') +
                '/admin/api/' + st.apiVersion + '/graphql.json';
    const res = await nativeHttp('POST', url,
      { 'X-Shopify-Access-Token': st.token, 'Content-Type': 'application/json' },
      JSON.stringify({ query: '{shop{name}}' }));
    if (!res.ok) throw new Error(res.error || ('HTTP ' + res.status));
    const d = JSON.parse(res.body);
    if (d.errors) throw new Error(d.errors[0].message);
    toast('Connecté à ' + d.data.shop.name, 'ok');
  } catch (e) {
    toast('Échec : ' + e.message, 'bad');
  }
}

function testNotif() {
  saveSettings();
  if (!Native.ok()) { toast('Disponible seulement dans l\'app Android', 'bad'); return; }
  if (!Native.notificationsOk()) { Native.askNotifications(); return; }
  Native.scheduleTimer('test', 'Atelier NMT — test', 'Si tu lis ça écran verrouillé, tout est bon.', Date.now() + 60000);
  sheet(
    '<h2>Test lancé</h2>' +
    '<div class="sub">Une notification arrivera dans une minute. Verrouille l\'écran et laisse le téléphone de côté : c\'est exactement la situation d\'une fin d\'impression.</div>' +
    '<div class="sheet-actions"><button class="btn primary" onclick="closeSheet()">Compris</button></div>'
  );
}

function exportData() {
  const json = JSON.stringify(DB, null, 2);
  const name = 'atelier-nmt-' + new Date().toISOString().slice(0, 10) + '.json';
  const path = Native.saveFile(name, json);
  if (path) {
    sheet('<h2>Sauvegarde enregistrée</h2><div class="sub">' + esc(path) + '</div>' +
      '<div class="sheet-actions"><button class="btn primary" onclick="closeSheet()">Fermer</button></div>');
  } else {
    sheet(
      '<h2>Sauvegarde</h2><div class="sub">Copie ce texte et garde-le au chaud.</div>' +
      '<textarea style="min-height:200px" readonly>' + esc(json) + '</textarea>' +
      '<div class="sheet-actions"><button class="btn primary" onclick="closeSheet()">Fermer</button></div>',
      root => { const t = $('textarea', root); t.focus(); t.select(); }
    );
  }
}

function importData() {
  sheet(
    '<h2>Restaurer une sauvegarde</h2>' +
    '<div class="sub">Colle ici le contenu d\'un export. Les données actuelles seront remplacées.</div>' +
    '<textarea name="json" style="min-height:160px" placeholder="{ … }"></textarea>' +
    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Restaurer</button>' +
    '</div>',
    root => {
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        try {
          const parsed = JSON.parse($('[name=json]', root).value);
          if (!parsed || !Array.isArray(parsed.machines)) throw new Error('format inattendu');
          DB = Object.assign(JSON.parse(JSON.stringify(DEFAULT_DB)), parsed);
          DB.settings = Object.assign({}, DEFAULT_DB.settings, parsed.settings || {});
          save(); closeSheet(); rescheduleAll(); render();
          toast('Sauvegarde restaurée', 'ok');
        } catch (e) {
          toast('Fichier illisible : ' + e.message, 'bad');
        }
      };
    }
  );
}

function resetData() {
  confirmSheet('Tout effacer ?', 'Machines, bobines, commandes et profils seront perdus. Pense à exporter avant.', 'Effacer', () => {
    DB.machines.forEach(m => Native.cancelTimer(m.id));
    DB = JSON.parse(JSON.stringify(DEFAULT_DB));
    save(); render(); toast('Données effacées');
  }, true);
}
