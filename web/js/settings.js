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

  /* ---- relais de l'atelier ---- */
  const sujet = Relais.sujet();
  out += '<div class="sec-title">Relais de l\'atelier</div>' +
    '<div class="card">' +
      '<div class="hint" style="margin-bottom:10px">Un appareil resté à l\'atelier publie l\'état des imprimantes. ' +
        'Hors du wifi de l\'atelier, l\'application lit ce relevé — en 4G comme sur n\'importe quel wifi.</div>' +
      '<label class="field"><span>Sujet publié par le relais</span>' +
        '<input type="text" name="relayTopic" value="' + esc(sujet) + '" placeholder="nmt-atelier-…" autocapitalize="off" autocorrect="off">' +
        '<div class="hint">Le même que dans le fichier relais.json du Pi. Laisse vide pour ne pas utiliser de relais.</div>' +
      '</label>' +
      '<div class="btn-row">' +
        '<button class="btn" onclick="saveRelais()">Enregistrer</button>' +
        '<button class="btn primary" onclick="testRelais()">Tester</button>' +
      '</div>' +
      '<div class="hint" id="relais-out" style="margin-top:9px"></div>' +
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

  out += '<div class="sec-title">Mise à jour</div>' +
    '<div class="card">' +
      '<div class="kv"><span>Version installée</span><b>' + esc(Native.version()) + '</b></div>' +
      '<div id="maj-out" class="small muted" style="margin:12px 0 0">' +
        (Native.ok() ? 'Appuie pour voir s\'il y a du nouveau.' : 'Disponible seulement dans l\'application.') +
      '</div>' +
      '<div class="sp"></div>' +
      '<button class="btn wide primary" onclick="checkUpdate()">Rechercher une mise à jour</button>' +
    '</div>';

  out += '<div class="sec-title">À propos</div>' +
    '<div class="card">' +
      '<div class="kv"><span>Application</span><b>Atelier NMT</b></div>' +
      '<div class="kv"><span>Données</span><b>Stockées sur l\'appareil</b></div>' +
      '<div class="kv"><span>Machines branchées</span><b>' +
        DB.machines.filter(m => m.printer && m.printer.host).length + ' sur ' + DB.machines.length + '</b></div>' +
    '</div>';

  return out;
}

/* ---------- mise à jour ---------- */

function checkUpdate(silencieux) {
  const out = $('#maj-out');
  if (!Native.ok()) { if (out) out.textContent = 'Disponible seulement dans l\'application.'; return; }
  if (out && !silencieux) out.textContent = 'Recherche…';

  DB.settings.lastUpdateCheck = Date.now();
  save();

  nativeCall('checkUpdate', []).then(r => {
    if (!r || !r.ok) {
      if (out && !silencieux) out.innerHTML = '<span style="color:var(--bad)">Échec — ' +
        esc((r && r.error) || 'sans réponse') + '</span>';
      return;
    }
    if (!r.available) {
      if (out && !silencieux) out.textContent = 'Tu es à jour (version ' + esc(r.current) + ').';
      return;
    }
    proposeUpdate(r);
  }).catch(e => {
    if (out && !silencieux) out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>';
  });
}

function proposeUpdate(r) {
  sheet(
    '<h2>Version ' + esc(r.version) + ' disponible</h2>' +
    '<div class="sub">Tu es en ' + esc(r.current) + '. L\'installation se fait sur place, tes données sont conservées.</div>' +
    (r.notes ? '<div class="card tight small" style="margin-bottom:14px;white-space:pre-wrap">' +
        esc(String(r.notes).slice(0, 400)) + '</div>' : '') +
    '<div class="sheet-actions">' +
      '<button class="btn ghost" data-x="no">Plus tard</button>' +
      '<button class="btn primary" data-x="ok">Installer</button>' +
    '</div>',
    root => {
      $('[data-x=no]', root).onclick = closeSheet;
      $('[data-x=ok]', root).onclick = () => {
        const btn = $('[data-x=ok]', root);
        btn.textContent = 'Téléchargement…';
        btn.disabled = true;
        nativeCall('installUpdate', [r.url]).then(res => {
          if (res && res.ok) {
            closeSheet();
            toast('Installateur ouvert', 'ok');
          } else if (res && res.needPermission) {
            closeSheet();
            confirmSheet('Autorisation requise',
              'Android demande la permission d\'installer des applications depuis Atelier NMT. Une fois accordée, relance la mise à jour.',
              'Ouvrir les réglages', () => Native.openInstallPermission());
          } else {
            btn.textContent = 'Réessayer';
            btn.disabled = false;
            toast('Échec : ' + ((res && res.error) || 'inconnu'), 'bad');
          }
        }).catch(e => {
          btn.textContent = 'Réessayer';
          btn.disabled = false;
          toast('Échec : ' + e.message, 'bad');
        });
      };
    }
  );
}

/* vérification discrète au démarrage, une fois par jour */
function autoCheckUpdate() {
  if (!Native.ok()) return;
  const last = DB.settings.lastUpdateCheck || 0;
  if (Date.now() - last < 20 * 3600000) return;
  checkUpdate(true);
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

function saveRelais() {
  const el = $('[name=relayTopic]');
  if (!el) return;
  if (!Relais.save(el.value)) { toast('Le relais ne marche que dans l\'app Android', 'bad'); return; }
  toast(el.value.trim() ? 'Relais enregistré' : 'Relais désactivé', 'ok');
  render();
}

function testRelais() {
  const out = $('#relais-out');
  saveRelais();
  if (out) out.textContent = 'Lecture du relais…';
  Relais.test()
    .then(r => {
      if (!out) return;
      if (r && r.ok) {
        const noms = (r.machines || []).join(', ');
        out.innerHTML = '<span style="color:var(--ok)">Relevé reçu — ' + r.joignables + ' machine(s) joignable(s) sur ' +
          (r.machines || []).length + (r.at ? ', publié à ' + fmtDayClock(r.at) : '') + '</span>' +
          (noms ? '<br>' + esc(noms) : '');
      } else {
        out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc((r && r.error) || 'sans réponse') + '</span>';
      }
    })
    .catch(e => { if (out) out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>'; });
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
  const copied = Native.copy(json);

  if (path) {
    sheet('<h2>Sauvegarde faite</h2>' +
      '<div class="sub">Fichier : ' + esc(path) + '</div>' +
      (copied
        ? '<div class="info-box">Elle est aussi dans le presse-papiers. Le presse-papiers survit à une désinstallation : si tu réinstalles l\'app, tu pourras la recoller directement dans Importer.</div>'
        : '<div class="warn-box">Le presse-papiers n\'a pas pu être rempli — garde bien le fichier.</div>') +
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
    '<div class="sub">Colle ici une sauvegarde — appui long dans le champ, puis Coller. Les données actuelles seront remplacées.</div>' +
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
