const { chromium } = require('playwright');
const path = require('path');

const WEB = 'file://' + path.resolve(__dirname, '../web/index.html');
const OUT = path.resolve(__dirname, '../test/shots');

const errors = [];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 412, height: 915 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true
  });
  const page = await ctx.newPage();

  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));

  /* le parc pré-rempli est testé à part : ici on part d'une base neutre
     pour que les comptages portent sur ce que le test crée lui-même */
  await page.addInitScript(() => {
    try {
      /* uniquement au tout premier chargement : ce script est rejoué
         à chaque navigation, et il ne doit pas effacer les données
         que le test vient d'écrire quand il recharge la page */
      if (!localStorage.getItem('nmt_atelier_v1')) {
        localStorage.setItem('nmt_atelier_v1', JSON.stringify({
          machines: [], spools: [], profiles: [], orders: [], weights: {},
          settings: { parcSeeded: 1 }
        }));
      }
    } catch (e) {}
  });

  await page.goto(WEB);
  await page.waitForTimeout(300);

  const step = async (name, fn) => {
    try { await fn(); console.log('  ok   ' + name); }
    catch (e) { console.log('  FAIL ' + name + ' → ' + e.message); errors.push('STEP ' + name + ': ' + e.message); }
  };

  console.log('\n— navigation —');
  for (const t of ['stock', 'biblio', 'orders', 'profiles', 'settings', 'machines']) {
    await step('onglet ' + t, async () => {
      await page.click(`#tabbar .tab[data-tab=${t}]`);
      await page.waitForTimeout(120);
      if (!(await page.$('#view'))) throw new Error('vue vide');
    });
  }

  console.log('\n— création machine —');
  await step('ouvrir la feuille machine', async () => {
    await page.click('#tb-actions .tb-btn.accent');
    await page.waitForSelector('.sheet');
  });
  await step('remplir et enregistrer', async () => {
    await page.fill('.sheet [name=name]', 'K2 Plus');
    await page.fill('.sheet [name=model]', 'Creality K2 Plus');
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(200);
    const txt = await page.textContent('#view');
    if (!txt.includes('K2 Plus')) throw new Error('machine absente de la liste');
  });

  console.log('\n— stock —');
  await step('achat en gros : 10 bobines d\'un coup', async () => {
    await page.click('#tabbar .tab[data-tab=stock]');
    await page.click('#tb-actions .tb-btn.accent');
    await page.waitForSelector('.sheet');
    await page.click('.sheet [data-chips=brand] .chip[data-v=Sunlu]');
    await page.click('.sheet [data-chips=material] .chip[data-v=PLA]');
    await page.click('.sheet [data-chips=color] .chip[data-v=Noir]');
    await page.fill('.sheet [name=sealed]', '9');
    await page.fill('.sheet [name=open]', '640');
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(250);
    const txt = await page.textContent('#view');
    if (!txt.includes('Sunlu')) throw new Error('référence absente');
    if (!txt.includes('9,64 kg')) throw new Error('total faux : ' + txt.slice(0, 160));
    if (!txt.includes('×10')) throw new Error('nombre de bobines absent');
  });
  await step('deuxième référence, presque épuisée', async () => {
    await page.click('#tb-actions .tb-btn.accent');
    await page.waitForSelector('.sheet');
    await page.click('.sheet [data-chips=brand] .chip[data-v=Creality]');
    await page.click('.sheet [data-chips=material] .chip[data-v=PETG]');
    await page.click('.sheet [data-chips=color] .chip[data-v=Rouge]');
    await page.fill('.sheet [name=sealed]', '0');
    await page.fill('.sheet [name=open]', '120');
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(250);
    const txt = await page.textContent('#view');
    if (!txt.includes('Bientôt vide')) throw new Error('niveau bas non signalé');
    if (!txt.includes('À racheter')) throw new Error('alerte rachat absente');
  });
  await step('ajouter 5 bobines depuis Ajuster', async () => {
    await page.click('#view .card:has-text("Rouge") .btn:has-text("Ajuster")');
    await page.waitForSelector('.sheet');
    await page.click('.sheet .chip[data-sealed="5"]');
    await page.waitForTimeout(150);
    await page.click('.sheet [data-x=no]');
    await page.waitForTimeout(250);
    const t = await page.evaluate(() => DB.spools.find(s => s.color === 'Rouge').sealed);
    if (t !== 5) throw new Error('réserve non incrémentée : ' + t);
  });

  console.log('\n— commande manuelle —');
  await step('créer une commande', async () => {
    await page.click('#tabbar .tab[data-tab=orders]');
    await page.click('#tb-actions .tb-btn:not(.accent)');
    await page.waitForSelector('.sheet');
    await page.fill('.sheet [name=name]', 'Commission Rémi');
    await page.fill('.sheet [name=customer]', 'Rémi Morand');
    await page.fill('.sheet [name=title]', 'Casque Mando');
    await page.fill('.sheet [name=grams]', '480');
    await page.click('.sheet [data-chips=color] .chip[data-v=Noir]');
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(200);
    const txt = await page.textContent('#view');
    if (!txt.includes('Commission Rémi')) throw new Error('commande absente');
  });
  await step('ouvrir le détail', async () => {
    await page.click('#view .card.click');
    await page.waitForSelector('.sheet');
    const txt = await page.textContent('.sheet');
    if (!txt.includes('Casque Mando')) throw new Error('ligne absente');
    await page.click('.sheet .btn.ghost:has-text("Fermer")');
    await page.waitForTimeout(150);
  });

  console.log('\n— besoins stock —');
  await step('la commande apparaît dans le stock', async () => {
    await page.click('#tabbar .tab[data-tab=stock]');
    await page.waitForTimeout(150);
    const txt = await page.textContent('#view');
    if (!txt.includes('Ce qu\'il faut pour les commandes')) throw new Error('bloc besoins absent');
    if (!txt.includes('480 g')) throw new Error('besoin non calculé');
  });

  console.log('\n— profil —');
  await step('créer un profil', async () => {
    await page.click('#tabbar .tab[data-tab=profiles]');
    await page.click('#tb-actions .tb-btn.accent');
    await page.waitForSelector('.sheet');
    await page.fill('.sheet [name=name]', 'Casque PLA Matte fuzzy');
    await page.fill('.sheet [name=layer]', '0.2');
    await page.fill('.sheet [name=nozzle]', '0.4');
    await page.fill('.sheet [name=infill]', '12');
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(200);
    if (!(await page.textContent('#view')).includes('Casque PLA Matte fuzzy')) throw new Error('profil absent');
  });

  console.log('\n— timer —');
  await step('charger un filament sur la machine', async () => {
    await page.click('#tabbar .tab[data-tab=machines]');
    await page.waitForTimeout(100);
    await page.click('#view .btn:has-text("Changer")');
    await page.waitForSelector('.sheet [name=filamentId]');
    await page.selectOption('.sheet [name=filamentId]', { index: 1 });
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(200);
    if (!(await page.textContent('#view')).includes('Sunlu')) throw new Error('filament non affiché sur la machine');
  });
  await step('lancer un timer', async () => {
    await page.click('#view .btn:has-text("Lancer une impression")');
    await page.waitForSelector('.sheet');
    await page.click('.sheet .chip[data-v="120"]');
    await page.fill('.sheet [name=label]', 'Coque casque');
    const sel = await page.$('.sheet [name=lineRef]');
    if (sel) await page.selectOption('.sheet [name=lineRef]', { index: 1 });
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(400);
    const txt = await page.textContent('#view');
    if (!/[12]:\d\d:\d\d/.test(txt)) throw new Error('compte à rebours absent : ' + txt.slice(0, 200));
  });
  await step('le compteur descend', async () => {
    const a = await page.textContent('#clk-' + (await page.evaluate(() => DB.machines[0].id)));
    await page.waitForTimeout(2300);
    const b = await page.textContent('#clk-' + (await page.evaluate(() => DB.machines[0].id)));
    if (a === b) throw new Error('horloge figée (a=' + a + ' b=' + b + ')');
  });
  await step('ajouter 15 min', async () => {
    await page.click('#view .btn:has-text("+15 min")');
    await page.waitForTimeout(200);
    if (!/2:14:\d\d/.test(await page.textContent('#view'))) throw new Error('+15 min sans effet');
  });

  console.log('\n— fin d\'impression —');
  await step('terminer et déduire le filament', async () => {
    const before = await page.evaluate(() => spoolTotal(DB.spools[0]));
    await page.click('#view .btn:has-text("Terminer")');
    await page.waitForSelector('.sheet');
    const val = await page.inputValue('.sheet [name=grams]');
    if (val !== '480') throw new Error('poids non pré-rempli (reçu "' + val + '")');
    await page.click('.sheet [data-x=ok]');
    await page.waitForTimeout(250);
    const left = await page.evaluate(() => spoolTotal(DB.spools[0]));
    if (left !== before - 480) throw new Error('déduction incorrecte : ' + before + ' → ' + left);
    const done = await page.evaluate(() => DB.orders[0].lines[0].done);
    if (!done) throw new Error('ligne de commande non soldée');
    const st = await page.evaluate(() => DB.orders[0].status);
    if (st !== 'done') throw new Error('commande non clôturée : ' + st);
  });

  console.log('\n— persistance —');
  await step('rechargement de la page', async () => {
    /* save() est synchrone mais l'action qui le declenche ne l'est pas
       toujours : on attend que le stockage porte bien l'etat courant,
       sinon le rechargement part trop tot et le test ment */
    await page.waitForFunction(() => {
      try {
        const brut = localStorage.getItem('nmt_atelier_v1');
        if (!brut) return false;
        const d = JSON.parse(brut);
        return (d.machines || []).length === 1 && (d.spools || []).length === 2
            && (d.orders || []).length === 1;
      } catch (e) { return false; }
    }, null, { timeout: 5000 });
    await page.reload();
    await page.waitForTimeout(300);
    const n = await page.evaluate(() => DB.machines.length + '/' + DB.spools.length + '/' + DB.orders.length);
    if (n !== '1/2/1') throw new Error('données perdues : ' + n);
    const kg = await page.evaluate(() => spoolTotal(DB.spools[0]));
    if (kg !== 9160) throw new Error('stock mal relu : ' + kg);
  });

  console.log('\n— captures —');
  await page.evaluate(() => {
    DB.machines[0].status = 'running';
    DB.machines[0].filamentId = DB.spools[1].id;
    DB.machines[0].job = { label: 'Casque Bo-Katan — coque', grams: 420 };
    DB.machines[0].timer = { startedAt: Date.now(), endAt: Date.now() + 7400000, dur: 7400000 };
    DB.machines.push({ id: 'm2', name: 'P1S', model: 'Bambu Lab P1S', filamentId: DB.spools[0].id,
      profileId: '', status: 'done', timer: { endAt: Date.now() - 600000 }, job: { label: 'Pauldrons ×2' } });
    DB.machines.push({ id: 'm3', name: 'Ender 3', model: 'Creality Ender 3 V3', filamentId: '',
      profileId: '', status: 'idle', timer: null, job: null });
    DB.orders[0].status = 'todo'; DB.orders[0].lines[0].done = false;
    save(); render();
  });
  await page.waitForTimeout(300);

  /* La bibliotheque vit sur le Pi : en navigateur on bouchonne le pont
     Android pour que l'ecran se dessine quand meme, avec une commande qui
     s'etale sur les deux familles et un 3mf a trois plateaux. */
  console.log('\n— bibliothèque —');
  await page.evaluate(() => {
    const plat = (idx, min, g, objets, faits, etat) => ({
      idx: idx, minutes: min, grammes: g, objets: objets, vignette: 'Metadata/plate_' + idx + '.png',
      exemplaires: 1, faits: faits, reste: faits ? 0 : 1,
      dernier: faits ? Date.now() - 7200000 : 0, machines: faits ? ['P1S 1'] : [],
      refaire: etat === 'refaire', etat: etat || (faits ? 'fait' : 'attente'),
      machine_en_cours: etat === 'encours' ? 'P1S 2' : ''
    });
    const casque = {
      chemin: 'p1s/1045 Mando/casque_jetpack.gcode.3mf', famille: 'p1s',
      nom: 'casque_jetpack.gcode.3mf', dossier: '1045 Mando', commande: '1045 Mando',
      taille: 48234567, modifie: Date.now() - 86400000, multi: true,
      plateaux: [plat(1, 307, 186, ['casque_coque', 'casque_visiere'], 1, 'fait'),
                 plat(2, 121, 74, ['jetpack_gauche'], 0, 'attente'),
                 plat(3, 121, 74, ['jetpack_droit'], 0, 'encours')],
      encours: true,
      exemplaires: 3, faits: 1, reste: 2, dernier: Date.now() - 7200000,
      machines: ['P1S 1'], minutes: 549
    };
    const socle = {
      chemin: 'k2/1045 Mando/socle.gcode', famille: 'k2', nom: 'socle.gcode',
      dossier: '1045 Mando', commande: '1045 Mando', taille: 2411000,
      modifie: Date.now() - 3600000, multi: false,
      plateaux: [{ idx: 0, minutes: 0, grammes: 0, objets: [], vignette: '',
                   exemplaires: 1, faits: 0, reste: 1, dernier: 0, machines: [],
                   refaire: true, etat: 'refaire', machine_en_cours: '' }],
      refaire: true,
      exemplaires: 1, faits: 0, reste: 1, dernier: 0, machines: [], minutes: 0
    };
    const blaster = {
      chemin: 'p1s/blaster.gcode.3mf', famille: 'p1s', nom: 'blaster.gcode.3mf',
      dossier: '', commande: '', taille: 9123000, modifie: Date.now() - 172800000,
      multi: false,
      plateaux: [{ idx: 1, minutes: 190, grammes: 95, objets: ['blaster'], vignette: '',
                   exemplaires: 1, faits: 2, reste: 0, dernier: Date.now() - 90000000,
                   machines: ['P1S 1', 'P1S 2'], refaire: false, etat: 'fait',
                   manuel: 0, machine_en_cours: '' }],
      exemplaires: 1, faits: 2, reste: 0, dernier: Date.now() - 90000000,
      machines: ['P1S 1', 'P1S 2'], minutes: 190
    };
    const index = {
      ok: true, racine: '/opt/relais-atelier/gcodes', familles: ['k2', 'p1s'],
      fichiers: [socle, casque, blaster],
      commandes: [{ nom: '1045 Mando', fichiers: 2, familles: ['k2', 'p1s'],
                    plateaux: 4, faits: 1, reste: 3, minutes: 549,
                    dernier: Date.now() - 7200000, chemins: [socle.chemin, casque.chemin],
                    encours: 1, refaire: 1, termine: false }]
    };
    const historique = { ok: true, lignes: [
      { machine: 'P1S 1', fichier: 'casque_jetpack.gcode.3mf', etat: 'fini',
        fin: Date.now() - 7200000, minutes: 307 },
      { machine: 'P1S 2', fichier: 'blaster.gcode.3mf', etat: 'échec',
        fin: Date.now() - 86400000, minutes: 41 }
    ] };
    window.NMT = Object.assign(window.NMT || {}, {
      biblioHost: () => '10.1.2.60',
      biblioToken: () => 'secret',
      setBiblio: () => {},
      biblioIndex: id => setTimeout(() => window.NMTcb(id, JSON.stringify(index)), 10),
      biblioHistory: (n, id) => setTimeout(() => window.NMTcb(id, JSON.stringify(historique)), 10),
      biblioCopies: (c, n, id) => setTimeout(() => window.NMTcb(id, '{"ok":true}'), 10),
      biblioPlateCopies: (c, p, n, id) => setTimeout(() => window.NMTcb(id, '{"ok":true}'), 10),
      biblioMark: (c, p, f, m, id) => setTimeout(() => window.NMTcb(id, '{"ok":true}'), 10),
      biblioOrder: (c, n, id) => setTimeout(() => window.NMTcb(id, '{"ok":true}'), 10),
      biblioThumb: (c, p, id) => setTimeout(() => window.NMTcb(id, '{"ok":false}'), 10),
      biblioPush: (c, m, h, l, p, id) => { window.__push = [c, m, h, l, p];
        setTimeout(() => window.NMTcb(id, '{"ok":true,"lance":true}'), 10); },
      biblioRedo: (c, p, r, id) => { window.__redo = [c, p, r];
        setTimeout(() => window.NMTcb(id, '{"ok":true}'), 10); },
      biblioStart: (c, m, h, p, id) => { window.__demarre = [c, m, h, p];
        setTimeout(() => window.NMTcb(id,
          '{"ok":true,"dit":"P1S 1 a démarré casque_jetpack.gcode.3mf"}'), 10); },
      biblioCancel: (cible, id) => { window.__annule = cible;
        setTimeout(() => window.NMTcb(id, '{"ok":true,"dit":"arrêt demandé"}'), 10); },
      biblioTransfers: (id) => { window.__sondes = (window.__sondes || 0) + 1;
        setTimeout(() => window.NMTcb(id,
        JSON.stringify({ ok: true, direct: !!window.__direct,
                         envois: window.__envois || [],
                         at: Date.now() + (window.__derive || 0), ici: Date.now() })), 10); },
      biblioAck: (ident, id) => setTimeout(() => window.NMTcb(id,
        JSON.stringify({ id: ident, ok: true, dit: 'casque lancé sur P1S 1' })), 10),
      testBiblio: id => setTimeout(() => window.NMTcb(id, '{"ok":true,"fichiers":3}'), 10)
    });
    /* des machines branchees : sans elles, aucune n'est proposee comme
       destination et les boutons d'envoi n'ont rien a afficher */
    DB.machines.push({ id: 'mk2', name: 'K2 Plus 1', model: 'Creality K2 Plus',
      filamentId: '', profileId: '', status: 'idle', timer: null, job: null,
      printer: { kind: 'moonraker', host: '10.1.2.57' } });
    DB.machines.push({ id: 'mp1s', name: 'P1S 1', model: 'Bambu Lab P1S',
      filamentId: '', profileId: '', status: 'idle', timer: null, job: null,
      printer: { kind: 'bambu', host: '10.1.3.10', serial: 'X', code: '' } });
    save();
    BIB = null; BIB_ERREUR = '';
  });

  await step('la bibliothèque se remplit', async () => {
    await page.click('#tabbar .tab[data-tab=biblio]');
    await page.waitForTimeout(400);
    const n = await page.$$eval('#view [data-bib]', e => e.length);
    if (n !== 3) throw new Error('3 fichiers attendus, ' + n + ' affichés');
  });

  await step('la commande regroupe les deux familles', async () => {
    const tete = await page.textContent('#view .cmd-head');
    if (!/1045 Mando/.test(tete)) throw new Error('commande absente : ' + tete);
    if (!/1 plateau sur 4/.test(tete)) throw new Error('avancement faux : ' + tete);
    if (!/K2 \+ P1S/.test(tete)) throw new Error('familles absentes : ' + tete);
  });

  await step('ce qui n\'a pas de commande est à part', async () => {
    const titres = await page.$$eval('#view .sec-title', e => e.map(x => x.textContent));
    if (!titres.some(t => /Hors commande/.test(t))) throw new Error('section manquante');
  });

  await step('la recherche filtre sans perdre le curseur', async () => {
    await page.fill('#bib-q', 'blaster');
    await page.waitForTimeout(150);
    const vus = await page.$$eval('#view [data-bib]', e => e.filter(x => x.style.display !== 'none').length);
    if (vus !== 1) throw new Error('1 résultat attendu, ' + vus);
    const actif = await page.evaluate(() => document.activeElement && document.activeElement.id);
    if (actif !== 'bib-q') throw new Error('le champ a perdu le curseur');
    await page.fill('#bib-q', '');
    await page.waitForTimeout(120);
  });

  await step('chercher par commande marche aussi', async () => {
    await page.fill('#bib-q', '1045');
    await page.waitForTimeout(150);
    const vus = await page.$$eval('#view [data-bib]', e => e.filter(x => x.style.display !== 'none').length);
    if (vus !== 2) throw new Error('2 fichiers attendus pour 1045, ' + vus);
    await page.fill('#bib-q', '');
    await page.waitForTimeout(120);
  });

  await step('le filtre « à sortir » écarte ce qui est fait', async () => {
    await page.click('#view .chip:nth-child(2)');
    await page.waitForTimeout(200);
    const n = await page.$$eval('#view [data-bib]', e => e.length);
    if (n !== 2) throw new Error('2 fichiers attendus, ' + n);
    await page.click('#view .chip:nth-child(1)');
    await page.waitForTimeout(200);
  });

  await step('les plateaux d\'un 3mf sont listés un par un', async () => {
    await page.click('#view [data-bib*="casque_jetpack"]');
    await page.waitForTimeout(300);
    const n = await page.$$eval('.sheet .plateau', e => e.length);
    if (n !== 3) throw new Error('3 plateaux attendus, ' + n);
    const fini = await page.$$eval('.sheet .plateau.fini', e => e.length);
    if (fini !== 1) throw new Error('1 plateau déjà sorti attendu, ' + fini);
    const t = await page.textContent('.sheet .plateau .s');
    if (!/casque_coque/.test(t)) throw new Error('objets du plateau absents : ' + t);
    await page.screenshot({ path: OUT + '/biblio-plateaux.png' });
  });

  await step('cocher un plateau le signale au relais', async () => {
    let vu = null;
    await page.evaluate(() => { window.__mark = null; });
    await page.evaluate(() => {
      const vrai = window.NMT.biblioMark;
      window.NMT.biblioMark = (c, p, f, m, id) => { window.__mark = [c, p, f]; vrai(c, p, f, m, id); };
    });
    await page.click('.sheet .plateau:nth-of-type(2) .btn.primary');
    await page.waitForTimeout(400);
    vu = await page.evaluate(() => window.__mark);
    if (!vu) throw new Error('rien envoyé au relais');
    if (vu[1] !== 2 || vu[2] !== true) throw new Error('mauvais plateau : ' + JSON.stringify(vu));
    await page.evaluate(() => closeSheet());
    await page.waitForTimeout(150);
  });

  await step('à distance, l\'envoi passe par le relais', async () => {
    await page.evaluate(() => { BIB.canal = true; render(); });
    await page.waitForTimeout(200);
    const note = await page.textContent('#view .note');
    if (!/relais/.test(note)) throw new Error('bandeau absent : ' + note);
    await page.click('#view [data-bib*="casque_jetpack"]');
    await page.waitForTimeout(300);
    const txt = await page.textContent('.sheet');
    if (!/Déposer/.test(txt)) throw new Error('le bouton Déposer doit rester là');
    if (!/c'est le relais qui enverra/i.test(txt)) throw new Error('explication absente');
    await page.evaluate(() => { closeSheet(); BIB.canal = false; render(); });
    await page.waitForTimeout(150);
  });

  await step('chaque plateau montre où il en est', async () => {
    await page.click('#view [data-bib*="casque_jetpack"]');
    await page.waitForTimeout(300);
    const lignes = await page.$$eval('.sheet .plateau', e => e.map(x => x.textContent));
    if (!/Sorti/.test(lignes[0])) throw new Error('plateau 1 pas sorti : ' + lignes[0]);
    if (!/À faire/.test(lignes[1])) throw new Error('plateau 2 pas à faire : ' + lignes[1]);
    if (!/En cours/.test(lignes[2])) throw new Error('plateau 3 pas en cours : ' + lignes[2]);
    if (!/P1S 2/.test(lignes[2])) throw new Error('machine absente : ' + lignes[2]);
    const boutons = await page.$$eval('.sheet .plateau .btn', e => e.length);
    if (boutons !== 2) throw new Error('le plateau en cours ne doit pas avoir de bouton, vu ' + boutons);
    await page.screenshot({ path: OUT + '/biblio-plateaux.png' });
    await page.evaluate(() => closeSheet());
    await page.waitForTimeout(150);
  });

  await step('la commande signale ce qui est à refaire', async () => {
    const tete = await page.textContent('#view .cmd-head');
    if (!/À refaire/.test(tete)) throw new Error('en-tête : ' + tete);
  });

  await step('un fichier a un seul plateau se coche aussi', async () => {
    await page.click('#view [data-bib*="socle"]');
    await page.waitForTimeout(300);
    const feuille = await page.textContent('.sheet');
    if (!/Exemplaires voulus/.test(feuille)) throw new Error('fiche inattendue : ' + feuille);
    const boutons = await page.$$eval('.sheet .btn', e => e.map(x => x.textContent));
    if (!boutons.includes('Fait'))
      throw new Error('rien pour le cocher à la main : ' + boutons.join(','));
    await page.evaluate(() => { window.__marks = [];
      const v = window.NMT.biblioMark;
      window.NMT.biblioMark = (c, p, f, m, id) => { window.__marks.push([c, p, f]); v(c, p, f, m, id); }; });
    await page.evaluate(() => biblioMarquer('k2/1045 Mando/socle.gcode', 0, true));
    await page.waitForTimeout(300);
    const vu = await page.evaluate(() => window.__marks);
    if (!vu.length || vu[0][2] !== true)
      throw new Error('le relais n\'a rien reçu : ' + JSON.stringify(vu));
  });

  await step('un plateau raté se signale à refaire', async () => {
    await page.click('#view [data-bib*="socle"]');
    await page.waitForTimeout(300);
    const boutons = await page.$$eval('.sheet .btn', e => e.map(x => x.textContent));
    if (!boutons.some(b => /refaire/i.test(b)))
      throw new Error('rien pour le signaler raté : ' + boutons.join(','));
    await page.evaluate(() => biblioRefaire('k2/1045 Mando/socle.gcode', 0, false));
    await page.waitForTimeout(300);
    const vu = await page.evaluate(() => window.__redo);
    if (!vu || vu[2] !== false) throw new Error('mauvais ordre : ' + JSON.stringify(vu));
  });

  await step('ce qui est sorti tout seul ne propose pas d\'annuler', async () => {
    await page.click('#view [data-bib*="blaster"]');
    await page.waitForTimeout(300);
    const boutons = await page.$$eval('.sheet .btn', e => e.map(x => x.textContent));
    if (boutons.includes('Annuler'))
      throw new Error('bouton sans effet proposé : ' + boutons.join(','));
    await page.evaluate(() => closeSheet());
    await page.waitForTimeout(150);
  });

  await step('un fichier déjà déposé se démarre sans le renvoyer', async () => {
    await page.evaluate(() => { window.__demarre = null; window.__push = null; });
    await page.click('#view [data-bib*="casque_jetpack"]');
    await page.waitForTimeout(300);
    const feuille = await page.textContent('.sheet');
    if (!/Démarrer sans renvoyer/.test(feuille))
      throw new Error('pas de geste pour démarrer seul : ' + feuille.slice(0, 200));
    await page.evaluate(() => biblioLancerSeul('p1s/1045 Mando/casque_jetpack.gcode.3mf', 'P1S 1'));
    await page.waitForTimeout(250);
    /* multi-plateaux : il doit demander lequel avant de lancer quoi que ce soit */
    const titre = await page.textContent('.sheet h2');
    if (!/Quel plateau/.test(titre)) throw new Error('pas de choix de plateau : ' + titre);
    await page.click('.sheet .card.click:nth-of-type(2)');
    await page.waitForTimeout(400);
    const vu = await page.evaluate(() => window.__demarre);
    if (!vu) throw new Error('rien demandé au relais');
    if (vu[3] !== 2) throw new Error('mauvais plateau : ' + JSON.stringify(vu));
    if (!/^\d+\.\d+\.\d+\.\d+$/.test(vu[2] || ''))
      throw new Error('adresse absente : ' + JSON.stringify(vu));
    /* et surtout : aucun fichier n'est reparti */
    const renvoye = await page.evaluate(() => window.__push);
    if (renvoye) throw new Error('le fichier a été renvoyé pour rien');
    await page.evaluate(() => closeSheet());
    await page.waitForTimeout(150);
  });

  await step('lancer un multi-plateaux demande lequel', async () => {
    await page.click('#view [data-bib*="casque_jetpack"]');
    await page.waitForTimeout(300);
    const boutons = await page.$$eval('.sheet .btn.primary', e => e.map(x => x.textContent));
    if (!boutons.includes('Lancer')) throw new Error('pas de bouton Lancer : ' + boutons.join(','));
    await page.evaluate(() => biblioPousser('p1s/1045 Mando/casque_jetpack.gcode.3mf', 'P1S 1', true));
    await page.waitForTimeout(300);
    const titre = await page.textContent('.sheet h2');
    if (!/Quel plateau/.test(titre)) throw new Error('pas de choix de plateau : ' + titre);
    const choix = await page.$$eval('.sheet .card.click', e => e.length);
    if (choix !== 3) throw new Error('3 plateaux attendus, ' + choix);

    await page.click('.sheet .card.click:nth-of-type(2)');
    await page.waitForTimeout(250);
    const conf = await page.textContent('.sheet');
    if (!/plateau 2/.test(conf)) throw new Error('le plateau choisi n\'est pas repris : ' + conf);
    await page.click('.sheet .btn.primary');
    await page.waitForTimeout(400);
    const vu = await page.evaluate(() => window.__push);
    if (!vu) throw new Error('rien envoyé');
    if (vu[3] !== true || vu[4] !== 2) throw new Error('mauvais envoi : ' + JSON.stringify(vu));
    /* l'adresse accompagne le nom : c'est elle qui fait le lien côté relais
       quand la machine a été renommée sur le téléphone */
    if (!/^\d+\.\d+\.\d+\.\d+$/.test(vu[2] || ''))
      throw new Error('adresse de la machine absente : ' + JSON.stringify(vu));
    await page.evaluate(() => closeSheet());
    await page.waitForTimeout(150);
  });

  await step('sans jeton, l\'écran prévient au lieu de laisser faire', async () => {
    await page.evaluate(() => {
      window.NMT.biblioToken = () => '';
      BIB.canal = true; render();
    });
    await page.waitForTimeout(200);
    const vu = await page.textContent('#view');
    if (!/Jeton manquant/.test(vu)) throw new Error('aucun avertissement');
    if (!/refusera/.test(vu)) throw new Error('conséquence pas dite');
    await page.evaluate(() => {
      window.NMT.biblioToken = () => 'secret';
      BIB.canal = false; render();
    });
    await page.waitForTimeout(150);
  });

  await step('un ordre différé rend compte de son sort', async () => {
    await page.evaluate(() => {
      const vrai = window.NMT.biblioPush;
      window.NMT.biblioPush = (c, m, h, l, p, id) => setTimeout(() => window.NMTcb(id,
        JSON.stringify({ ok: true, differe: true, id: 'ord-1' })), 10);
      window.__toasts = [];
      const vraiToast = window.toast;
      window.toast = (m, k) => { window.__toasts.push(m); vraiToast(m, k); };
    });
    await page.evaluate(() => biblioPousser('p1s/blaster.gcode.3mf', 'P1S 1', false));
    await page.waitForTimeout(300);
    const premier = await page.evaluate(() => window.__toasts.join(' | '));
    if (!/Demandé au relais/.test(premier)) throw new Error('pas d\'accusé immédiat : ' + premier);
    /* l'accusé arrive après le premier essai, à 20 s : on force le temps */
    await page.waitForFunction(() => window.__toasts.some(t => /lancé sur P1S 1/.test(t)),
                               null, { timeout: 40000 });
  });

  await step('un envoi long dit qu\'il est en cours avant de conclure', async () => {
    await page.evaluate(() => {
      /* le relais accuse deux fois : « reçu, en cours », puis le résultat */
      let appels = 0;
      window.NMT.biblioAck = (ident, id) => { appels++;
        const a = appels < 2
          ? { id: ident, ok: true, fini: false, dit: 'reçu — blaster part vers P1S 1' }
          : { id: ident, ok: true, fini: true, dit: 'blaster déposé sur P1S 1' };
        setTimeout(() => window.NMTcb(id, JSON.stringify(a)), 10); };
      window.NMT.biblioPush = (c, m, h, l, p, id) => setTimeout(() => window.NMTcb(id,
        JSON.stringify({ ok: true, differe: true, id: 'ord-2' })), 10);
      Biblio.cadence = { premier: 300, ensuite: 300, duree: 20000 };
      window.__toasts = [];
    });
    await page.evaluate(() => biblioPousser('p1s/blaster.gcode.3mf', 'P1S 1', false));
    await page.waitForFunction(() => window.__toasts.some(t => /part vers P1S 1/.test(t)),
                               null, { timeout: 8000 });
    await page.waitForFunction(() => window.__toasts.some(t => /déposé sur P1S 1/.test(t)),
                               null, { timeout: 8000 });
    const tout = await page.evaluate(() => window.__toasts.join(' | '));
    if (/Aucune réponse/.test(tout))
      throw new Error('conclut au silence alors que le relais répond : ' + tout);
  });

  await step('un envoi qui ne revient jamais le dit sans mentir', async () => {
    await page.evaluate(() => {
      window.NMT.biblioAck = (ident, id) => setTimeout(() => window.NMTcb(id,
        JSON.stringify({ id: ident, ok: true, fini: false, dit: 'reçu — en cours' })), 10);
      Biblio.cadence = { premier: 200, ensuite: 200, duree: 1200 };
      window.__toasts = [];
    });
    await page.evaluate(() => biblioPousser('p1s/blaster.gcode.3mf', 'P1S 1', false));
    await page.waitForFunction(() => window.__toasts.some(t => /pas dit comment/.test(t)),
                               null, { timeout: 8000 });
    const tout = await page.evaluate(() => window.__toasts.join(' | '));
    if (/Aucune réponse du relais/.test(tout))
      throw new Error('dit le relais muet alors qu\'il avait répondu : ' + tout);
    await page.evaluate(() => { Biblio.cadence = { premier: 20000, ensuite: 60000, duree: 900000 }; });
  });

  await step('un envoi montre où il en est', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e1', fichier: 'casque_jetpack.gcode.3mf', machine: 'P1S 1',
                           octets: 30000000, total: 91000000,
                           debut: Date.now() - 20000, ecoule: 20000,
                           fin: 0, etat: 'en cours' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /%/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (!/Envoi en cours/.test(vu)) throw new Error('pas de titre : ' + vu.slice(0, 120));
    if (!/33%/.test(vu)) throw new Error('pourcentage faux : ' + vu.slice(0, 200));
    if (!/P1S 1/.test(vu)) throw new Error('machine absente');
    const large = await page.$eval('#bib-envois .jauge > i', e => e.style.width);
    if (large !== '33%') throw new Error('jauge à ' + large);
    /* à distance la barre ne bouge qu'à chaque relevé : il faut le dire */
    if (!/paliers/.test(vu)) throw new Error('la latence n\'est pas annoncée');
  });

  await step('un envoi fini se voit jusqu\'au bout, puis s\'arrête', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e1', fichier: 'casque_jetpack.gcode.3mf', machine: 'P1S 1',
                           octets: 91000000, total: 91000000,
                           debut: Date.now() - 90000, fin: Date.now(), etat: 'fait',
                           dit: 'déposé' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /100%/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (!/Dernier envoi/.test(vu)) throw new Error('encore annoncé en cours : ' + vu.slice(0, 120));
    if (!/envoi fait/.test(vu) && !/class="card tight envoi fait"/.test(vu))
      throw new Error('pas marqué fini : ' + vu.slice(0, 200));
    /* plus rien en cours : le suivi doit finir par s'arrêter de lui-même.
       Les envois lancés aux étapes précédentes ont chacun programmé une
       relecture de politesse ; elles s'éteignent après leur tour. */
    await page.waitForFunction(() => BIB_ENVOIS_T === null, null, { timeout: 30000 });
  });

  await step('le débit ne dépend pas de l\'horloge du téléphone', async () => {
    /* le relais dit « 20 s pour 30 Mo » : 1,5 Mo/s, quelle que soit l'heure
       que croit le Pi. C'est le mélange des deux horloges qui affichait des
       débits inventés. */
    await page.evaluate(() => {
      window.__derive = 0;
      window.__envois = [{ id: 'e3', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 31457280, total: 94371840, ecoule: 20000,
                           debut: Date.now() - 999999999, fin: 0, etat: 'en cours' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /Mo\/s/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (!/1,5 Mo\/s/.test(vu)) throw new Error('débit faux : ' + vu.slice(0, 260));
  });

  await step('une horloge de relais à la dérive se signale', async () => {
    await page.evaluate(() => {
      /* sur place seulement : par le canal, « at » est l'heure de publication
         du relevé et l'écart mesuré serait son âge, pas une dérive */
      window.__direct = true;
      window.__derive = -20 * 60 * 1000;      // le Pi retarde de 20 minutes
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /écart/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (!/en retard/.test(vu)) throw new Error('sens de la dérive faux : ' + vu.slice(0, 200));
    if (!/set-ntp/.test(vu)) throw new Error('aucune marche à suivre');
    /* un petit écart ne doit alarmer personne */
    await page.evaluate(() => { window.__derive = 30000; biblioSuivreEnvois(false); });
    await page.waitForTimeout(600);
    const calme = await page.$eval('#bib-envois', e => e.innerHTML);
    if (/écart/.test(calme)) throw new Error('alarme pour 30 secondes d\'écart');
    /* et à distance on ne mesure rien du tout : l'âge du relevé n'est pas
       une dérive d'horloge, et l'annoncer comme telle était un faux procès */
    await page.evaluate(() => {
      window.__direct = false; window.__derive = -20 * 60 * 1000;
      biblioSuivreEnvois(false);
    });
    await page.waitForTimeout(600);
    const loin = await page.$eval('#bib-envois', e => e.innerHTML);
    if (/écart/.test(loin)) throw new Error('accuse l\'horloge sur un relevé vieux');
    await page.evaluate(() => { window.__derive = 0; window.__direct = false; });
  });

  await step('un envoi en cours peut être arrêté', async () => {
    await page.evaluate(() => {
      window.__annule = null;
      window.__envois = [{ id: 'e9', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 20000000, total: 94371840, ecoule: 15000,
                           fin: 0, etat: 'en cours' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /Arrêter/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    await page.click('#bib-envois .btn.ghost');
    await page.waitForTimeout(250);
    const feuille = await page.textContent('.sheet');
    if (!/Arrêter l'envoi/.test(feuille)) throw new Error('pas de confirmation : ' + feuille);
    if (!/incomplet/.test(feuille)) throw new Error('la conséquence n\'est pas dite');
    await page.click('.sheet .btn.danger');
    await page.waitForFunction(() => window.__annule === 'e9', null, { timeout: 5000 });
  });

  await step('un envoi fini ne propose plus de l\'arrêter', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e9', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 94371840, total: 94371840, ecoule: 60000,
                           fin: Date.now(), etat: 'fait', dit: 'déposé' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /100%/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (/Arrêter/.test(vu)) throw new Error('bouton sans objet : ' + vu.slice(0, 200));
  });

  await step('un envoi arrêté ne se fait pas passer pour une panne', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e9', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 20000000, total: 94371840, ecoule: 15000,
                           fin: Date.now(), etat: 'annule',
                           dit: 'arrêté en cours d\'envoi' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /arrêté/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (!/n'en garde rien/.test(vu)) throw new Error('le sort du fichier n\'est pas dit');
    if (/Arrêter/.test(vu)) throw new Error('encore un bouton d\'arrêt');
  });

  await step('un envoi raté le dit en rouge', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e2', fichier: 'socle.gcode', machine: 'K2 Plus 1',
                           octets: 0, total: 2411000, debut: Date.now() - 5000,
                           fin: Date.now(), etat: 'echoue',
                           dit: 'K2 Plus 1 ne répond pas sur 10.1.2.57' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /ne répond pas/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (!/envoi echoue/.test(vu)) throw new Error('pas marqué raté : ' + vu.slice(0, 200));
    await page.evaluate(() => { window.__envois = []; biblioSuivreEnvois(false); });
    await page.waitForTimeout(300);
  });

  await step('quitter l\'écran coupe le suivi des envois', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e7', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 1000, total: 10000, ecoule: 5000,
                           fin: 0, etat: 'en cours' }];
      Biblio.cadence = { premier: 200, ensuite: 200, duree: 20000 };
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => BIB_ENVOIS_T !== null, null, { timeout: 5000 });
    await page.evaluate(() => { go('machines'); });
    await page.waitForTimeout(200);
    const coupe = await page.evaluate(() => BIB_ENVOIS_T === null);
    if (!coupe) throw new Error('le suivi tourne encore hors de l\'écran');
    /* et il ne doit pas repartir tout seul */
    await page.evaluate(() => { window.__sondes = 0; });
    await page.waitForTimeout(1200);
    const n = await page.evaluate(() => window.__sondes);
    if (n > 0) throw new Error(n + ' interrogations du relais écran quitté');
    await page.evaluate(() => { go('biblio'); });
    await page.waitForTimeout(300);
  });

  await step('une seule interrogation à la fois', async () => {
    /* lancer un envoi, en arrêter un et revenir sur l'écran programmaient
       chacun leur suivi : les chaînes se superposaient jusqu'à huit
       interrogations simultanées du relais */
    await page.evaluate(() => {
      window.__sondes = 0;
      window.__envois = [{ id: 'e8', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 1000, total: 10000, ecoule: 5000,
                           fin: 0, etat: 'en cours' }];
      for (let i = 0; i < 8; i++) biblioSuivreEnvois(false);
    });
    await page.waitForTimeout(150);
    const n = await page.evaluate(() => window.__sondes);
    if (n > 1) throw new Error(n + ' interrogations lancées d\'un coup');
    await page.evaluate(() => {
      window.__envois = []; biblioArreterSuivi();
      Biblio.cadence = { premier: 20000, ensuite: 60000, duree: 900000 };
    });
    await page.waitForTimeout(200);
  });

  await step('un état d\'envoi inconnu n\'est pas pris pour un succès', async () => {
    await page.evaluate(() => {
      window.__envois = [{ id: 'e6', fichier: 'casque.3mf', machine: 'P1S 1',
                           octets: 12000000, total: 60000000, ecoule: 9000,
                           fin: 0, etat: 'bizarre' }];
      biblioSuivreEnvois(false);
    });
    await page.waitForFunction(() => /casque/.test(
      (document.getElementById('bib-envois') || {}).innerHTML || ''), null, { timeout: 5000 });
    const vu = await page.$eval('#bib-envois', e => e.innerHTML);
    if (/déposé sur la machine/.test(vu))
      throw new Error('annonce un dépôt qui n\'a pas eu lieu : ' + vu.slice(0, 200));
    if (!/Arrêter/.test(vu)) throw new Error('plus moyen de l\'arrêter');
    await page.evaluate(() => { window.__envois = []; biblioArreterSuivi(); });
  });

  await step('l\'historique de la farm s\'affiche', async () => {
    await page.click('#tb-actions .tb-btn');
    await page.waitForTimeout(400);
    const n = await page.$$eval('.sheet .rowitem', e => e.length);
    if (n < 2) throw new Error('historique vide');
    await page.evaluate(() => closeSheet());
  });

  for (const t of ['machines', 'stock', 'biblio', 'orders', 'profiles']) {
    await page.click(`#tabbar .tab[data-tab=${t}]`);
    await page.waitForTimeout(250);
    await page.screenshot({ path: OUT + '/' + t + '.png' });
  }

  await browser.close();

  console.log('\n══════════════════════════════');
  if (errors.length) {
    console.log(errors.length + ' problème(s) :');
    errors.forEach(e => console.log('  · ' + e));
    process.exit(1);
  }
  console.log('Tout est passé.');
})();
