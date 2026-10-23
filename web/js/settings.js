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

  /* ---- bibliothèque de gcodes ---- */
  out += '<div class="sec-title">Bibliothèque de gcodes</div>' +
    '<div class="card">' +
      '<div class="hint" style="margin-bottom:10px">Le relais garde les fichiers tranchés, rangés par commande, ' +
        'et dit quels plateaux sont déjà sortis. Il publie tout ça sur le canal ci-dessus : ' +
        'la bibliothèque se lit et se coche de n\'importe où, sans rien régler ici.<br><br>' +
        'L\'adresse et le jeton ne servent qu\'à l\'atelier, pour y parler en direct : ' +
        'affichage instantané, aperçus des plateaux, et envoi d\'un fichier sur une machine — ' +
        'ça, ça ne peut pas passer par Internet.</div>' +
      '<label class="field"><span>Adresse du relais</span>' +
        '<input type="text" name="biblioHost" value="' + esc(Biblio.hote()) + '" placeholder="10.1.2.60" autocapitalize="off" autocorrect="off">' +
        '<div class="hint">L\'adresse du Pi sur le réseau. Le port 8765 est ajouté tout seul. ' +
          'Facultatif : sans elle, la bibliothèque passe par le canal.</div>' +
      '</label>' +
      '<label class="field"><span>Jeton</span>' +
        '<input type="password" name="biblioToken" value="' + esc(Biblio.jeton()) + '" placeholder="…" autocapitalize="off" autocorrect="off">' +
        '<div class="hint">Le même que dans relais.json du Pi. Il empêche un appareil de passage ' +
          'de lancer une impression, et signe ce que tu coches à distance.</div>' +
      '</label>' +
      '<div class="btn-row">' +
        '<button class="btn" onclick="saveBiblio()">Enregistrer</button>' +
        '<button class="btn primary" onclick="testBiblio()">Tester</button>' +
      '</div>' +
      '<div class="hint" id="biblio-out" style="margin-top:9px"></div>' +
    '</div>';

  /* ---- tableur de compta ---- */
  if (sujet) {
    const envoye = DB.settings.comptaSentAt;
    out += '<div class="sec-title">Tableur de compta</div>' +
      '<div class="card">' +
        '<div class="hint" style="margin-bottom:10px">L\'app envoie ses commandes sur le même canal que le relais. ' +
          'Le script <b>compta_xlsx.py</b>, resté sur le PC, les ajoute en bas de la feuille Compta d\'Argent.xlsx. ' +
          'Rien n\'est jamais écrit par-dessus ce que tu as saisi à la main.</div>' +
        '<div class="kv"><span>Commandes dans l\'app</span><b class="mono">' + DB.orders.length + '</b></div>' +
        '<div class="kv"><span>Dernier envoi</span><b class="mono">' +
          (envoye ? fmtDayClock(envoye) : 'jamais') + '</b></div>' +
        '<div class="btn-row">' +
          '<button class="btn primary" onclick="envoyerCompta()">Envoyer maintenant</button>' +
        '</div>' +
        '<div class="hint" id="compta-out" style="margin-top:9px"></div>' +
      '</div>';
  }

  /* ---- remettre le Pi d'aplomb ---- */
  if (sujet) {
    etatRelaisAuBesoin();
    const pi = PI_VU;
    const partage = pi && pi.partage;
    out += '<div class="sec-title">Le Pi</div>' +
      '<div class="card">' +
        '<div class="hint" style="margin-bottom:10px">Quand le partage ne répond plus ' +
          'alors que le Pi est allumé, inutile d\'aller débrancher : relancer le partage ' +
          'suffit presque toujours, et ça n\'interrompt rien d\'autre.</div>' +
        (pi === null
          ? '<div class="hint">Lecture du relais…</div>'
          : '<div class="kv"><span>Partage de fichiers</span><b class="mono"' +
              (partage === 'arrêté' ? ' style="color:var(--bad)"' : '') + '>' +
              esc(partage || 'inconnu') + '</b></div>' +
            '<div class="kv"><span>Debout depuis</span><b class="mono">' +
              (pi.debout ? dureeRonde(pi.debout) : '—') + '</b></div>') +
        '<div class="btn-row">' +
          '<button class="btn primary" onclick="piGeste(\'partage\')">Relancer le partage</button>' +
          '<button class="btn" onclick="piGeste(\'relais\')">Relancer le relais</button>' +
        '</div>' +
        '<div class="btn-row">' +
          '<button class="btn" onclick="piGeste(\'pi\')">Redémarrer le Pi</button>' +
        '</div>' +
        '<div class="hint" id="pi-out" style="margin-top:9px">' + PI_DIT + '</div>' +
      '</div>';
  }

  /* ---- délai annoncé dans la boutique ---- */
  if (sujet) {
    etatRelaisAuBesoin();
    const v = VITRINE_VUE;
    const p = (v && v.peinture) || {};
    const ouverte = p.ouverte !== false;
    const jours = p.jours || 0;
    const marge = (v && v.marge) || 0;
    const fam = (v && v.par_famille) || {};
    const detail = Object.keys(fam).sort()
      .map(f => familleLabel(f) + ' ' + Math.round(fam[f]) + ' h').join(' · ');

    out += '<div class="sec-title">Délai annoncé dans la boutique</div>' +
      '<div class="card">' +
        '<div class="hint" style="margin-bottom:10px">Le relais additionne ce qu\'il reste ' +
          'à imprimer, le répartit sur les machines de chaque famille, et écrit le délai ' +
          'sur la boutique. Les machines tournent jour et nuit, et les deux familles ' +
          'travaillent en parallèle : c\'est la plus chargée qui donne le délai.<br><br>' +
          'Le jeton qui écrit dans la boutique reste sur le Pi : le téléphone envoie une ' +
          'décision, jamais une écriture.</div>' +
        (v === null
          ? '<div class="hint">Lecture du relais…</div>'
          : (v.jours === undefined
            ? '<div class="warn-box">Le relais n\'a pas encore publié de délai. ' +
              'Il le calcule à son premier tour, puis une fois par heure.</div>'
            : '<div class="kv"><span>Délai calculé</span><b class="mono">' +
                v.jours + (v.jours > 1 ? ' jours' : ' jour') +
                (v.marge ? ' (dont ' + v.marge + ' de marge)' : '') + '</b></div>' +
              (detail ? '<div class="kv"><span>À sortir</span><b class="mono">' +
                esc(detail) + '</b></div>' : '') +
              '<div class="kv"><span>Commandes comptées</span><b class="mono">' +
                (v.commandes || 0) + '</b></div>' +
              '<div class="kv"><span>Dernière écriture</span><b class="mono">' +
                (v.envoye_at ? fmtDayClock(v.envoye_at) : 'jamais') + '</b></div>')) +
        (v && v.boutique
          ? '<div class="warn-box">Le délai est calculé mais pas envoyé : ' +
            esc(v.boutique) + '</div>' : '') +
        (v && (v.sans_fichier || []).length
          ? '<div class="warn-box">Aucun fichier dans la bibliothèque pour ' +
            esc((v.sans_fichier || []).join(', ')) + ' : ces commandes ne comptent pas ' +
            'dans le délai.</div>' : '') +
        '<div class="sp"></div>' +
        '<label class="field"><span>Peinture</span>' +
          '<select name="paintingOpen">' +
            '<option value="1"' + (ouverte ? ' selected' : '') + '>Ouverte</option>' +
            '<option value="0"' + (ouverte ? '' : ' selected') + '>Fermée</option>' +
          '</select>' +
          '<div class="hint">Fermée, la boutique annonce que la peinture n\'est pas ' +
            'proposée en ce moment.</div>' +
        '</label>' +
        '<label class="field"><span>Délai peinture (jours)</span>' +
          '<input type="number" name="paintingDays" min="0" max="120" value="' + jours + '">' +
        '</label>' +
        '<label class="field"><span>Marge sur le délai (jours)</span>' +
          '<input type="number" name="leadMargin" min="0" max="60" value="' + marge + '">' +
          '<div class="hint">Ajoutés au délai calculé, pour ne pas promettre au plus juste.</div>' +
        '</label>' +
        '<div class="btn-row">' +
          '<button class="btn primary" onclick="envoyerVitrine()">Envoyer au relais</button>' +
          '<button class="btn" onclick="etatRelaisAuBesoin(true)">Relire</button>' +
        '</div>' +
        '<div class="hint" id="vitrine-out" style="margin-top:9px">' + VITRINE_DIT + '</div>' +
      '</div>';
  }

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

function saveRelais(silencieux) {
  const el = $('[name=relayTopic]');
  if (!el) return false;
  if (!Relais.save(el.value)) { toast('Le relais ne marche que dans l\'app Android', 'bad'); return false; }
  if (!silencieux) toast(el.value.trim() ? 'Relais enregistré' : 'Relais désactivé', 'ok');
  render();
  return true;
}

function saveBiblio(silencieux) {
  const h = $('[name=biblioHost]'), j = $('[name=biblioToken]');
  if (!h || !j) return false;
  if (!Biblio.save(h.value, j.value)) {
    toast('La bibliothèque ne marche que dans l\'app Android', 'bad');
    return false;
  }
  BIB = null;
  BIB_ERREUR = '';
  if (!silencieux) toast(h.value.trim() ? 'Bibliothèque enregistrée' : 'Bibliothèque désactivée', 'ok');
  render();
  return true;
}

function testBiblio() {
  /* comme pour le relais : on enregistre d'abord, et on ne retient la zone
     de texte qu'après le redessin */
  if (!saveBiblio(true)) return;
  if (!Biblio.regle()) {
    const vide = $('#biblio-out');
    if (vide) vide.textContent = 'Aucune adresse enregistrée.';
    return;
  }
  const out = $('#biblio-out');
  if (out) out.textContent = 'Appel du relais…';
  /* Il y a deux chemins et un jeton. L'ancien test ne regardait que le
     chemin direct, et annonçait un échec hors de l'atelier alors que tout
     marchait par le canal : on rend compte des trois séparément. */
  Biblio.test()
    .then(r => {
      const o = $('#biblio-out');
      const lignes = [];

      if (r.direct) {
        lignes.push('<span style="color:var(--ok)">Relais joignable en direct ' +
          '— affichage instantané et aperçus des plateaux.</span>');
      } else if (r.adresse) {
        lignes.push('<span style="color:var(--txt-3)">Pas de réponse directe de ' +
          esc(r.adresse) + '. Normal hors du réseau de l\'atelier, ou si le ' +
          'pare-feu sépare ton wifi du Pi.</span>');
      } else {
        lignes.push('<span style="color:var(--txt-3)">Aucune adresse : tout passe par le canal.</span>');
      }

      if (r.lecture) {
        lignes.push('<span style="color:var(--ok)">Bibliothèque lue' +
          (r.canal ? ' par le canal' : ' en direct') + ' — ' + r.fichiers + ' fichier(s).</span>');
      } else {
        lignes.push('<span style="color:var(--bad)">Bibliothèque illisible — ' +
          esc(r.error || 'sans réponse') + '</span>');
      }

      if (!r.jeton) {
        lignes.push('<span style="color:var(--bad)">Aucun jeton : tu peux voir, ' +
          'mais le relais refusera tout envoi et tout plateau coché.</span>');
        toast('Il manque le jeton', 'bad');
      } else if (r.ping) {
        lignes.push('<span style="color:var(--txt-3)" id="biblio-ping">Jeton envoyé au ' +
          'relais, réponse dans la minute…</span>');
        Biblio.suivreOrdre(r.ping).then(a => {
          const el = $('#biblio-ping');
          if (!el) return;
          if (a && a.ok) {
            el.outerHTML = '<span style="color:var(--ok)">Jeton accepté par le relais.</span>';
            toast('Tout est bon', 'ok');
          } else {
            el.outerHTML = '<span style="color:var(--bad)">Jeton refusé par le relais — ' +
              esc((a && a.dit) || 'pas de réponse') + '</span>';
            toast('Jeton refusé', 'bad');
          }
        }).catch(() => {});
        toast('Lecture bonne, je vérifie le jeton', 'ok');
      } else {
        lignes.push('<span style="color:var(--ok)">Jeton enregistré.</span>');
        toast('Tout est bon', 'ok');
      }

      if (o) o.innerHTML = lignes.join('<br>');
    })
    .catch(e => {
      toast('Échec — ' + e.message, 'bad');
      const o = $('#biblio-out');
      if (o) o.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>';
    });
}

function envoyerCompta() {
  const out = $('#compta-out');
  if (out) out.textContent = 'Envoi…';
  comptaEnvoyer()
    .then(n => {
      toast(n + ' commande' + (n > 1 ? 's' : '') + ' envoyée' + (n > 1 ? 's' : ''), 'ok');
      render();
      const o = $('#compta-out');
      if (o) o.innerHTML = '<span style="color:var(--ok)">' + n + ' commande' + (n > 1 ? 's' : '') +
        ' publiée' + (n > 1 ? 's' : '') + '. Lance le script sur le PC pour remplir le tableur.</span>';
    })
    .catch(e => {
      toast('Échec — ' + e.message, 'bad');
      if (out) out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>';
    });
}

/* Les trois gestes d'entretien du Pi. Les deux derniers coupent le relais,
   donc on prévient avant, et on attend son accusé plutôt que de dire « c'est
   fait » à un relais qui est peut-être déjà parti. */
const PI_GESTES = {
  partage: { titre: 'Relancer le partage', confirme: '',
             attente: 'Relance du partage…' },
  relais: { titre: 'Relancer le relais',
            confirme: 'Relancer le relais ? Il revient tout seul dans la demi-minute.',
            attente: 'Relais en train de repartir…' },
  pi: { titre: 'Redémarrer le Pi',
        confirme: 'Redémarrer le Pi ? Compte une minute sans relevé ni bibliothèque.',
        attente: 'Redémarrage demandé…' }
};

function piGeste(cible, quandMeme) {
  const g = PI_GESTES[cible];
  if (!g) return;
  if (g.confirme && !quandMeme && !confirm(g.confirme)) return;

  piDire(g.attente);
  Relais.service(cible, !!quandMeme)
    .then(r => {
      if (!r || !r.ok) throw new Error((r && r.error) || 'refusé');
      piDire('<span style="color:var(--txt-3)">Envoyé. Le relais répond dans la minute…</span>');
      if (!r.id) return;
      return Biblio.suivreOrdre(r.id).then(a => {
        if (a && a.ok) {
          piDire('<span style="color:var(--ok)">' + esc(a.dit || 'fait') + '</span>');
          toast('Le relais a pris en compte', 'ok');
          /* le partage relancé change l'état affiché ; les deux autres
             gestes coupent le relais, inutile de le relire tout de suite */
          if (cible === 'partage') etatRelaisAuBesoin(true);
        } else if (a && !a.ok && /transfert/.test(a.dit || '')) {
          /* refusé parce qu'un fichier est en route : on propose d'insister
             plutôt que de laisser l'utilisateur deviner */
          piDire('<span style="color:var(--bad)">' + esc(a.dit) + '</span>');
          if (confirm(a.dit + '\n\nForcer quand même ?')) piGeste(cible, true);
        } else if (a) {
          piDire('<span style="color:var(--bad)">' + esc(a.dit || 'refusé') + '</span>');
        } else {
          /* pas de réponse : pour un redémarrage c'est normal, le relais
             est parti avant de pouvoir republier quoi que ce soit */
          piDire(cible === 'partage'
            ? '<span style="color:var(--bad)">Pas de réponse du relais.</span>'
            : '<span style="color:var(--txt-3)">Pas de réponse — c\'est attendu, ' +
              'le relais est en train de repartir. Recharge dans une minute.</span>');
        }
      });
    })
    .catch(e => {
      toast('Échec — ' + e.message, 'bad');
      piDire('<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>');
    });
}

function envoyerVitrine() {
  const ouverte = ($('[name=paintingOpen]') || {}).value === '1';
  const jours = Math.max(0, num(($('[name=paintingDays]') || {}).value));
  const marge = Math.max(0, num(($('[name=leadMargin]') || {}).value));

  vitrineDire('Envoi au relais…');
  Relais.reglerVitrine(ouverte, jours, marge)
    .then(r => {
      if (!r || !r.ok) throw new Error((r && r.error) || 'refusé');
      /* l'ordre part par le canal : le relais l'applique à son tour suivant,
         et accuse. On attend cet accusé plutôt que de dire « c'est fait ». */
      vitrineDire('<span style="color:var(--txt-3)">Envoyé. Le relais ' +
        'l\'applique dans la minute…</span>');
      toast('Envoyé au relais', 'ok');
      if (!r.id) return;
      Biblio.suivreOrdre(r.id).then(a => {
        if (a && a.ok) {
          vitrineDire('<span style="color:var(--ok)">Pris en compte : ' +
            esc(a.dit || '') + '</span>');
          /* on relit ce que le relais annonce : l'écran doit montrer son
             état, pas ce qu'on vient de taper */
          etatRelaisAuBesoin(true);
          toast('Le relais a pris en compte', 'ok');
        } else {
          vitrineDire('<span style="color:var(--bad)">Pas de réponse du relais — ' +
            esc((a && a.dit) || 'réessaie') + '</span>');
        }
      }).catch(() => {});
    })
    .catch(e => {
      toast('Échec — ' + e.message, 'bad');
      vitrineDire('<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>');
    });
}

function testRelais() {
  /* enregistrer redessine l'écran : on ne retient la zone de texte qu'après,
     sinon on écrit dans un élément qui n'est plus affiché */
  if (!saveRelais(true)) return;
  const out = $('#relais-out');
  if (out) out.textContent = 'Lecture du relais…';
  Relais.test()
    .then(r => {
      if (r && r.ok) {
        toast(r.joignables + ' machine' + (r.joignables > 1 ? 's' : '') + ' au relais', 'ok');
      } else {
        toast('Relais muet — ' + ((r && r.error) || 'sans réponse'), 'bad');
      }
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
    .catch(e => {
      toast('Échec — ' + e.message, 'bad');
      if (out) out.innerHTML = '<span style="color:var(--bad)">Échec — ' + esc(e.message) + '</span>';
    });
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
