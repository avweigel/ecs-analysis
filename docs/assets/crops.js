/* Crop hub: facets, ranges, column picker, table, and the linked viewer. */
(function () {
  const $ = id => document.getElementById(id);
  const PREP = { Chemical: 'chem', 'Rapid HPF': 'hpf' };
  const rows = DATA.rows, COLS = DATA.cols, MANI = DATA.mani;
  const base = 'membranes/';
  let shown = new Set(DATA.defaults.filter(c => COLS[c]));
  const facet = { tissue: new Set(), region: new Set(), prep: new Set() };
  const ranges = {};                       // col -> [lo, hi] currently applied
  let selected = { A: null, B: null }, active = 'A', compare = false, linked = true;

  const fmt = v => {
    if (v === null || v === undefined || Number.isNaN(v)) return null;
    const a = Math.abs(v);
    if (a === 0) return '0';
    if (a < 0.001 || a >= 1e6) return v.toExponential(2);
    if (a < 1) return v.toPrecision(3);
    if (a < 100) return v.toFixed(2);
    return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  };
  const uniq = k => [...new Set(rows.map(r => r[k]).filter(Boolean))].sort();

  /* ---------- filtering ---------- */
  function passes(r) {
    const q = $('q').value.toLowerCase().trim();
    if (q) {
      const hay = [r.crop, r.tissue, r.region, r.anatomy, r.prep].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    for (const k of ['tissue', 'region', 'prep']) {
      if (facet[k].size && !facet[k].has(r[k] || '')) return false;
    }
    for (const [c, [lo, hi]] of Object.entries(ranges)) {
      const v = r.m[c];
      if (v === null || v === undefined) return false;
      if (v < lo || v > hi) return false;
    }
    return true;
  }

  /* ---------- facets ---------- */
  function buildFacets() {
    const box = $('facets'); box.innerHTML = '';
    for (const [key, label] of [['tissue', 'Tissue'], ['region', 'Region'], ['prep', 'Preparation']]) {
      const g = document.createElement('div'); g.className = 'fgroup';
      g.innerHTML = `<span class="flabel">${label}</span>`;
      for (const v of uniq(key)) {
        const n = rows.filter(r => (r[key] || '') === v).length;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'chip' + (facet[key].has(v) ? ' on' : '');
        b.innerHTML = `${v}<span class="c">${n}</span>`;
        b.onclick = () => { facet[key].has(v) ? facet[key].delete(v) : facet[key].add(v);
          buildFacets(); render(); };
        g.appendChild(b);
      }
      box.appendChild(g);
    }
  }

  /* ---------- numeric ranges ---------- */
  function buildRanges() {
    const box = $('ranges'); box.innerHTML = '';
    for (const c of DATA.defaults) {
      const vals = rows.map(r => r.m[c]).filter(v => v !== null && v !== undefined);
      if (!vals.length) continue;
      const lo = Math.min(...vals), hi = Math.max(...vals);
      const d = document.createElement('div'); d.className = 'rrow';
      const cur = ranges[c] || [lo, hi];
      d.innerHTML = `<label>${COLS[c].label}${COLS[c].unit ? ' · ' + COLS[c].unit : ''}</label>
        <div class="pair">
          <input type="range" min="${lo}" max="${hi}" step="${(hi - lo) / 200 || 0.001}" value="${cur[0]}">
          <input type="range" min="${lo}" max="${hi}" step="${(hi - lo) / 200 || 0.001}" value="${cur[1]}">
          <span class="val">${fmt(cur[0])} – ${fmt(cur[1])}</span></div>`;
      const [a, b] = d.querySelectorAll('input'), lab = d.querySelector('.val');
      const upd = () => {
        let x = +a.value, y = +b.value; if (x > y) [x, y] = [y, x];
        lab.textContent = `${fmt(x)} – ${fmt(y)}`;
        if (x <= lo && y >= hi) delete ranges[c]; else ranges[c] = [x, y];
        render();
      };
      a.oninput = upd; b.oninput = upd;
      box.appendChild(d);
    }
  }

  /* ---------- column picker ---------- */
  function buildCols() {
    const box = $('colpick'); box.innerHTML = '';
    for (const c of Object.keys(COLS)) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'chip' + (shown.has(c) ? ' on' : '');
      b.textContent = COLS[c].label;
      b.title = COLS[c].blurb || '';
      b.onclick = () => { shown.has(c) ? shown.delete(c) : shown.add(c); buildCols(); render(); };
      box.appendChild(b);
    }
  }

  /* ---------- table ---------- */
  let sortCol = 'crop', sortDir = 1;
  function render() {
    const list = rows.filter(passes);
    const cols = [...shown];
    const th = $('t').querySelector('thead'), tb = $('t').querySelector('tbody');
    const head = ['crop', 'tissue', 'region', 'anatomy', 'prep', 'voxel'];
    th.innerHTML = '<tr>' +
      head.map(h => `<th class="sortable${h === 'voxel' ? ' num' : ''}" data-k="${h}">${
        h === 'voxel' ? 'Voxel<span class="u">nm</span>' : h[0].toUpperCase() + h.slice(1)}</th>`).join('') +
      cols.map(c => `<th class="num sortable" data-k="${c}" title="${(COLS[c].blurb || '').replace(/"/g, '&quot;')}">${
        COLS[c].label}<span class="u">${COLS[c].unit || '&nbsp;'}</span></th>`).join('') + '</tr>';

    const key = r => (head.includes(sortCol) ? r[sortCol] : r.m[sortCol]);
    list.sort((x, y) => {
      const a = key(x), b = key(y);
      if (a === null || a === undefined) return 1;
      if (b === null || b === undefined) return -1;
      return (typeof a === 'number' ? a - b : String(a).localeCompare(String(b))) * sortDir;
    });

    tb.innerHTML = list.map(r => {
      const sel = (selected.A === r.crop ? ' sel' : '') || (selected.B === r.crop ? ' sel' : '');
      return `<tr class="${sel}" data-crop="${r.crop}">
        <td class="thumbcell"><span style="display:flex;align-items:center;gap:9px">
          <img class="thumb" src="assets/art/thumbs/${r.crop}.png" alt="" loading="lazy" width="34" height="34">
          ${r.crop}<span class="cmp" data-slot="B">compare →</span></span></td>
        <td>${r.tissue}</td><td>${r.region || ''}</td><td class="wrap">${r.anatomy || ''}</td>
        <td><span class="tag ${PREP[r.prep]}">${r.prep}</span></td>
        <td class="num">${r.voxel || ''}</td>` +
        cols.map(c => { const v = fmt(r.m[c]);
          return `<td class="num${v === null ? ' muted' : ''}">${v === null ? '—' : v}</td>`; }).join('') +
        '</tr>';
    }).join('');
    $('count').textContent = `${list.length} of ${rows.length} crops`;
  }

  $('t').addEventListener('click', e => {
    const cmp = e.target.closest('.cmp');
    const tr = e.target.closest('tr[data-crop]'); if (!tr) return;
    const crop = tr.dataset.crop;
    if (cmp) { if (!compare) toggleCompare(); load('B', crop); }
    else load(active, crop);
  });
  $('t').querySelector('thead').addEventListener('click', e => {
    const th = e.target.closest('th[data-k]'); if (!th) return;
    const k = th.dataset.k;
    sortDir = (sortCol === k) ? -sortDir : 1; sortCol = k; render();
  });

  /* ---------- viewer ---------- */
  const V = window.ECSViewer;
  const panels = {};
  function initPanels() {
    for (const s of ['A', 'B']) {
      const host = $('p' + s).querySelector('.stage');
      panels[s] = new V.Panel(host, base);
      panels[s].onMove = p => {
        if (!linked || !compare) return;
        const other = s === 'A' ? panels.B : panels.A;
        if (other && other.entry) other.syncFrom(p);
      };
      const sel = $('p' + s).querySelector('.pick');
      sel.innerHTML = Object.keys(MANI).sort()
        .map(c => {const r=rows.find(x=>x.crop===c);
          return `<option value="${c}">${c} · ${MANI[c].tissue} · ${MANI[c].prep}${
            r&&r.voxel?' · '+r.voxel+' nm':''}</option>`;}).join('');
      sel.onchange = () => load(s, sel.value);
      $('p' + s).onclick = () => setActive(s);
    }
  }
  function setActive(s) {
    active = s;
    for (const k of ['A', 'B']) $('p' + k).classList.toggle('active', k === active);
  }
  function currentRange() { return [parseFloat($('vlo').value), parseFloat($('vhi').value)]; }
  function autoRange() {
    const sc = $('vscalar').value;
    const es = [selected.A, selected.B].filter(Boolean).map(c => MANI[c]).filter(Boolean);
    if (!es.length) return;
    const d = es.map(e => e.ranges[sc].default);
    const lo = Math.min(...d.map(x => x[0])), hi = Math.max(...d.map(x => x[1]));
    $('vlo').value = +lo.toPrecision(4); $('vhi').value = +hi.toPrecision(4);
  }
  function paintBar() {
    const sc = $('vscalar').value, [lo, hi] = currentRange();
    V.drawBar($('vbar'), sc, lo, hi);
    $('vlolab').textContent = fmt(lo) + ' ' + V.SCALARS[sc].unit;
    $('vhilab').textContent = fmt(hi) + ' ' + V.SCALARS[sc].unit;
  }
  async function load(slot, crop) {
    const e = MANI[crop]; if (!e) return;
    selected[slot] = crop;
    $('p' + slot).querySelector('.pick').value = crop;
    if (!Number.isFinite(parseFloat($('vlo').value))) autoRange();
    const sc = $('vscalar').value, [lo, hi] = currentRange();
    await panels[slot].show(e, sc, lo, hi);
    // the manifest's voxel_nm is the scale the mesh patch was built at (16 nm for
    // every crop), not the crop's acquisition voxel — take that from the table row
    const row = rows.find(r => r.crop === crop);
    const vox = row && row.voxel ? row.voxel + ' nm' : '';
    $('p' + slot).querySelector('.vfoot').textContent =
      [e.tissue, e.region_group || e.anatomy, e.prep, vox].filter(Boolean).join(' · ');
    if (linked && compare) {
      const other = slot === 'A' ? panels.B : panels.A;
      if (other && other.entry) panels[slot].syncFrom(other);
    }
    paintBar(); render();
  }
  function recolorAll() {
    const sc = $('vscalar').value, [lo, hi] = currentRange();
    for (const s of ['A', 'B']) if (panels[s] && panels[s].entry) panels[s].recolor(sc, lo, hi);
    paintBar();
  }
  function toggleCompare() {
    compare = !compare;
    $('pB').hidden = !compare;
    $('vwrap').classList.toggle('solo', !compare);
    $('vlink').hidden = !compare;
    $('vcompare').textContent = compare ? 'Single view' : 'Compare two';
    $('vcompare').classList.toggle('on', compare);
    if (compare && !selected.B) {
      const list = rows.filter(passes).map(r => r.crop).filter(c => c !== selected.A);
      load('B', list[0] || Object.keys(MANI)[0]);
    }
    setTimeout(() => { for (const s of ['A', 'B']) panels[s] && panels[s].resize(); }, 60);
  }

  $('vscalar').onchange = () => { autoRange(); recolorAll(); };
  $('vlo').oninput = recolorAll; $('vhi').oninput = recolorAll;
  $('vauto').onclick = () => { autoRange(); recolorAll(); };
  $('vcompare').onclick = toggleCompare;
  $('vlink').onclick = () => {
    linked = !linked;
    $('vlink').classList.toggle('on', linked);
    $('vlink').textContent = linked ? 'Cameras linked' : 'Cameras free';
    if (linked && panels.B.entry) panels.B.syncFrom(panels.A);
  };
  $('q').oninput = render;
  $('reset').onclick = () => {
    $('q').value = '';
    for (const k of Object.keys(facet)) facet[k].clear();
    for (const k of Object.keys(ranges)) delete ranges[k];
    shown = new Set(DATA.defaults.filter(c => COLS[c]));
    buildFacets(); buildRanges(); buildCols(); render();
  };

  buildFacets(); buildRanges(); buildCols(); render();
  initPanels();
  load('A', Object.keys(MANI).sort()[0]);
})();
