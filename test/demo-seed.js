/* Données d'exemple — uniquement dans l'aperçu web, jamais dans l'APK.
   Noms de clients inventés. */
(function () {
  const H = 3600000;
  const now = Date.now();

  const spools = [
    { id: 's1', brand: 'Sunlu',    material: 'PLA',  color: 'Noir',   spoolSize: 1000, sealed: 9, open: 720, note: 'Matte' },
    { id: 's2', brand: 'Creality', material: 'PETG', color: 'Rouge',  spoolSize: 1000, sealed: 2, open: 410, note: '' },
    { id: 's3', brand: 'Sunlu',    material: 'PLA',  color: 'Blanc',  spoolSize: 1000, sealed: 0, open: 95,  note: '' },
    { id: 's4', brand: 'Sunlu',    material: 'PETG', color: 'Noir',   spoolSize: 1000, sealed: 5, open: 0,   note: '' },
    { id: 's5', brand: 'Creality', material: 'ABS',  color: 'Gris',   spoolSize: 1000, sealed: 1, open: 560, note: '' },
    { id: 's6', brand: 'Sunlu',    material: 'PLA',  color: 'Argent', spoolSize: 1000, sealed: 0, open: 260, note: 'Silk' }
  ].map(s => Object.assign(s, { colorHex: colorHexOf(s.color), archived: false, createdAt: now }));

  const profiles = [
    { id: 'p1', name: 'Casque — PLA Matte fuzzy', material: 'PLA', layer: '0.2', nozzle: '0.4',
      infill: '12', speed: '220', tempNozzle: '215', tempBed: '60',
      note: 'Fuzzy skin 0.3 mm, bruit Voronoï. Supports arbre côté mentonnière.' },
    { id: 'p2', name: 'Armure — PETG solide', material: 'PETG', layer: '0.24', nozzle: '0.6',
      infill: '20', speed: '160', tempNozzle: '245', tempBed: '80',
      note: '4 périmètres sur les pièces qui prennent des coups.' },
    { id: 'p3', name: 'Blaster — pièces fines', material: 'PLA', layer: '0.12', nozzle: '0.4',
      infill: '25', speed: '120', tempNozzle: '210', tempBed: '60', note: '' }
  ];

  const machines = [
    { id: 'm1', name: 'K2 Plus', model: 'Creality K2 Plus', filamentId: 's2', profileId: 'p2',
      status: 'running', timer: { startedAt: now - 5.2 * H, endAt: now + 2.6 * H, dur: 7.8 * H },
      job: { label: 'Death Watch — plastron', orderId: 'o1', lineId: 'l1', grams: 620 } },
    { id: 'm2', name: 'P1S', model: 'Bambu Lab P1S', filamentId: 's1', profileId: 'p1',
      status: 'done', timer: { startedAt: now - 9 * H, endAt: now - 0.4 * H, dur: 8.6 * H },
      job: { label: 'Casque Bo-Katan — coque', orderId: 'o2', lineId: 'l3', grams: 480 } },
    { id: 'm3', name: 'Ender 3', model: 'Creality Ender 3 V3', filamentId: 's6', profileId: 'p3',
      status: 'idle', timer: null, job: null }
  ];

  const orders = [
    { id: 'o1', shopifyId: '', name: '#1041', customer: 'Lucas Berger', country: 'Belgium',
      createdAt: now - 5 * 86400000, source: 'shopify', status: 'printing', lines: [
        { id: 'l1', title: 'Death Watch Armor', variant: 'None / PETG', qty: 1, grams: 620,
          material: 'PETG', color: 'Rouge', done: false },
        { id: 'l2', title: 'Blaster Westar 35', variant: 'PETG / Yes', qty: 1, grams: 240,
          material: 'PETG', color: 'Rouge', done: true }
      ] },
    { id: 'o2', shopifyId: '', name: '#1042', customer: 'Marta Oliveira', country: 'Portugal',
      createdAt: now - 3 * 86400000, source: 'shopify', status: 'printing', lines: [
        { id: 'l3', title: 'Bo Katan Helmet', variant: 'With Visor Kit / PLA', qty: 1, grams: 480,
          material: 'PLA', color: 'Noir', done: false }
      ] },
    { id: 'o3', shopifyId: '', name: '#1043', customer: 'Tom Vandenberg', country: 'France',
      createdAt: now - 1 * 86400000, source: 'shopify', status: 'todo', lines: [
        { id: 'l4', title: 'Mandalorian Helmet', variant: 'Tesso / Without Visor / PLA', qty: 2,
          grams: 430, material: 'PLA', color: 'Blanc', done: false },
        { id: 'l5', title: 'Blaster DC-17', variant: 'PLA / No', qty: 1, grams: 180,
          material: 'PLA', color: 'Blanc', done: false }
      ] },
    { id: 'o4', shopifyId: '', name: 'Commission atelier', customer: 'Rémi', country: '',
      createdAt: now - 9 * 86400000, source: 'manual', status: 'shipped', lines: [
        { id: 'l6', title: 'Pauldrons sur mesure', variant: '', qty: 2, grams: 310,
          material: 'ABS', color: 'Gris', done: true }
      ] }
  ];

  const seed = function () {
    if (DB.machines.length || DB.spools.length || DB.orders.length) return;
    DB.spools = spools;
    DB.profiles = profiles;
    DB.machines = machines;
    DB.orders = orders;
    DB.settings.lastSync = now - 2 * H;
    save();
  };

  const originalBoot = window.boot;
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(function () {
      seed();
      if (typeof render === 'function') render();
    }, 0);
  });
})();
