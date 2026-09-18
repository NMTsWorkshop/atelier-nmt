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
  for (const t of ['stock', 'orders', 'profiles', 'settings', 'machines']) {
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
    await page.fill('.sheet [name=brand]', 'Sunlu');
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
    await page.fill('.sheet [name=brand]', 'Creality');
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

  for (const t of ['machines', 'stock', 'orders', 'profiles']) {
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
