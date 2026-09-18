/* ============================================================
   profiles.js — profils d'impression réutilisables
   ============================================================ */

function renderProfiles() {
  setTop('Profils',
    DB.profiles.length ? DB.profiles.length + ' profil' + (DB.profiles.length > 1 ? 's' : '') + ' enregistré' + (DB.profiles.length > 1 ? 's' : '') : 'Aucun profil',
    '<button class="tb-btn accent" onclick="editProfile()">' + iconPlus() + 'Profil</button>'
  );

  if (!DB.profiles.length) {
    return emptyState(
      'Aucun profil',
      'Un profil regroupe tes réglages habituels : matière, buse, hauteur de couche, températures. Tu peux ensuite l\'affecter à une machine.',
      'Créer un profil', 'editProfile()'
    );
  }

  return '<div class="stack">' + DB.profiles.map(profileCard).join('') + '</div>';
}

function profileCard(p) {
  const used = DB.machines.filter(m => m.profileId === p.id).map(m => m.name);
  const specs = [
    p.layer ? p.layer + ' mm' : '',
    p.nozzle ? 'buse ' + p.nozzle : '',
    p.infill ? p.infill + ' %' : '',
    p.speed ? p.speed + ' mm/s' : ''
  ].filter(Boolean).join(' · ');

  return '<div class="card tight click" onclick="editProfile(\'' + p.id + '\')">' +
    '<div class="card-head">' +
      '<div class="grow">' +
        '<div class="card-name" style="font-size:15px">' + esc(p.name) + '</div>' +
        '<div class="card-meta">' + esc(specs || 'Aucun réglage détaillé') + '</div>' +
      '</div>' +
      badge('', p.material || '—') +
    '</div>' +
    (p.tempNozzle || p.tempBed
      ? '<div class="card-meta" style="margin-top:8px">' +
        (p.tempNozzle ? 'Buse ' + esc(p.tempNozzle) + ' °C' : '') +
        (p.tempNozzle && p.tempBed ? ' · ' : '') +
        (p.tempBed ? 'Plateau ' + esc(p.tempBed) + ' °C' : '') + '</div>'
      : '') +
    (p.note ? '<div class="card-meta" style="margin-top:6px">' + esc(p.note) + '</div>' : '') +
    (used.length ? '<div class="fil-line"><span class="grow small">Utilisé sur ' + esc(used.join(', ')) + '</span></div>' : '') +
  '</div>';
}

function editProfile(id) {
  const p = id ? profileById(id) : null;
  sheet(
    '<h2>' + (p ? 'Modifier le profil' : 'Nouveau profil') + '</h2>' +
    '<label class="field"><span>Nom</span><input type="text" name="name" placeholder="Casque — PLA Matte fuzzy" value="' + esc(p ? p.name : '') + '"></label>' +
    '<label class="field"><span>Matière</span>' + materialChips('material', p ? p.material : 'PLA') + '</label>' +
    '<div class="field-2">' +
      '<label class="field"><span>Hauteur de couche (mm)</span><input type="text" name="layer" inputmode="decimal" placeholder="0.2" value="' + esc(p ? p.layer : '') + '"></label>' +
      '<label class="field"><span>Buse (mm)</span><input type="text" name="nozzle" inputmode="decimal" placeholder="0.4" value="' + esc(p ? p.nozzle : '') + '"></label>' +
    '</div>' +
    '<div class="field-2">' +
      '<label class="field"><span>Remplissage (%)</span><input type="number" name="infill" inputmode="numeric" placeholder="15" value="' + esc(p ? p.infill : '') + '"></label>' +
      '<label class="field"><span>Vitesse (mm/s)</span><input type="number" name="speed" inputmode="numeric" placeholder="200" value="' + esc(p ? p.speed : '') + '"></label>' +
    '</div>' +
    '<div class="field-2">' +
      '<label class="field"><span>Temp. buse (°C)</span><input type="number" name="tempNozzle" inputmode="numeric" placeholder="220" value="' + esc(p ? p.tempNozzle : '') + '"></label>' +
      '<label class="field"><span>Temp. plateau (°C)</span><input type="number" name="tempBed" inputmode="numeric" placeholder="60" value="' + esc(p ? p.tempBed : '') + '"></label>' +
    '</div>' +
    '<label class="field"><span>Notes</span><textarea name="note" placeholder="Fuzzy skin 0.3 / Voronoï, supports arbre, séchage 6 h…">' + esc(p ? p.note : '') + '</textarea></label>' +
    '<div class="sheet-actions">' +
      (p ? '<button class="btn danger" data-x="del">Supprimer</button>' : '') +
      '<button class="btn ghost" data-x="no">Annuler</button>' +
      '<button class="btn primary" data-x="ok">Enregistrer</button>' +
    '</div>',
    root => {
      const chips = bindChips(root);
      $('[data-x=no]', root).onclick = closeSheet;
      const del = $('[data-x=del]', root);
      if (del) del.onclick = () => {
        closeSheet();
        confirmSheet('Supprimer ce profil ?', p.name, 'Supprimer', () => {
          DB.profiles = DB.profiles.filter(x => x.id !== p.id);
          DB.machines.forEach(m => { if (m.profileId === p.id) m.profileId = ''; });
          save(); render(); toast('Profil supprimé');
        }, true);
      };
      $('[data-x=ok]', root).onclick = () => {
        const v = formValues(root), c = chips();
        if (!v.name.trim()) { toast('Il faut un nom', 'bad'); return; }
        const data = {
          name: v.name.trim(), material: c.material || 'PLA',
          layer: v.layer.trim(), nozzle: v.nozzle.trim(), infill: v.infill,
          speed: v.speed, tempNozzle: v.tempNozzle, tempBed: v.tempBed, note: v.note.trim()
        };
        if (p) Object.assign(p, data);
        else DB.profiles.push(Object.assign({ id: uid() }, data));
        save(); closeSheet(); render(); toast('Enregistré', 'ok');
      };
    }
  );
}
