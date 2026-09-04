/* Crop hub: facets, ranges, column picker, table, and the linked viewer. */
(function () {
  const $ = id => document.getElementById(id);
  const PREP = { Chemical: 'chem', 'Rapid HPF': 'hpf' };
  const rows = DATA.rows, COLS = DATA.cols;
  // one manifest per surface; the view says which one a panel is reading
  const SURF = { membrane: DATA.mani || {}, ecs: DATA.ecs || {} };
  const V = window.ECSViewer;
  const curView = () => V.VIEW[$('vview').value] || V.VIEW['mem-gap'];
  const MANIfor = surf => SURF[surf] || {};
  const MANI = () => MANIfor(curView().surface);
  const base = 'membranes/';
  let shown = new Set(DATA.defaults.filter(c => COLS[c]));
  const facet = { tissue: new Set(), region: new Set(), prep: new Set() };
  const ranges = {};                       // col -> [lo, hi] currently applied
  let selected = { A: null, B: null }, active = 'A', compare = true, linked = true;

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
    // two families measure the same things by different routes, so their labels
    // collide; disambiguate only the ones that actually clash
    const seen = {};
    for (const c of Object.keys(COLS)) seen[COLS[c].label] = (seen[COLS[c].label] || 0) + 1;
    for (const c of Object.keys(COLS)) {
      const fam = c.split('.')[0].replace(/_/g, ' ');
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'chip' + (shown.has(c) ? ' on' : '');
      b.textContent = seen[COLS[c].label] > 1
        ? `${COLS[c].label} · ${fam === 'membrane topology' ? 'mesh' : 'pooled'}`
        : COLS[c].label;
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
      '<th title="Open in Neuroglancer">View</th>' +
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
        <td class="ngcell"><a class="nglink" data-crop="${r.crop}" target="_blank"
          rel="noopener" title="Open this dataset in Neuroglancer, centred here">NG</a></td>
        <td>${r.tissue}</td><td>${r.region || ''}</td><td class="wrap">${r.anatomy || ''}</td>
        <td><span class="tag ${PREP[r.prep]}">${r.prep}</span></td>
        <td class="num">${r.voxel || ''}</td>` +
        cols.map(c => { const v = fmt(r.m[c]);
          return `<td class="num${v === null ? ' muted' : ''}">${v === null ? '—' : v}</td>`; }).join('') +
        '</tr>';
    }).join('');
    $('count').textContent = `${list.length} of ${rows.length} crops`;
    const nf = ['tissue', 'region', 'prep'].reduce((a, k) => a + facet[k].size, 0)
             + Object.keys(ranges).length;
    const nfe = $('nfilt');
    if (nfe) { nfe.textContent = nf ? '· ' + nf : ''; }
    if (window.refreshNgLinks) window.refreshNgLinks();
  }

  $('t').addEventListener('click', e => {
    if (e.target.closest('a.nglink')) return;      // let the link do its job
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
      sel.onchange = () => load(s, sel.value);
      $('p' + s).onclick = () => setActive(s);
      const fit = $('p' + s).querySelector('.fit');
      if (fit) fit.onclick = ev => {
        ev.stopPropagation();
        panels[s].frame();
        if (linked && compare) {
          const other = s === 'A' ? panels.B : panels.A;
          if (other && other.entry) other.syncFrom(panels[s]);
        }
      };
      $('p' + s).querySelector('.stage')
        .addEventListener('dblclick', () => panels[s].frame());
    }
  }
  function fillPicks() {
    const M = MANI();
    for (const s of ['A', 'B']) {
      const sel = $('p' + s).querySelector('.pick');
      sel.innerHTML = Object.keys(M).sort()
        .map(c => {const r = rows.find(x => x.crop === c);
          return `<option value="${c}">${c} · ${M[c].tissue} · ${M[c].prep}${
            r && r.voxel ? ' · ' + r.voxel + ' nm' : ''}</option>`;}).join('');
      if (selected[s] && M[selected[s]]) sel.value = selected[s];
    }
  }
  function setActive(s) {
    active = s;
    for (const k of ['A', 'B']) $('p' + k).classList.toggle('active', k === active);
  }
  function currentRange() { return [parseFloat($('vlo').value), parseFloat($('vhi').value)]; }
  /* which surface, coloured by what. `scalar` is null for the bare mesh, and
     the colour-range controls have nothing to say then, so they go away. */
  function curScalar() { return curView().scalar || null; }
  function autoRange() {
    const sc = curScalar(); if (!sc) return;
    const M = MANI();
    const es = [selected.A, selected.B].filter(Boolean).map(c => M[c]).filter(Boolean);
    if (!es.length) return;
    const d = es.map(e => e.ranges[sc] && e.ranges[sc].default).filter(Boolean);
    if (!d.length) return;
    const lo = Math.min(...d.map(x => x[0])), hi = Math.max(...d.map(x => x[1]));
    $('vlo').value = +lo.toPrecision(4); $('vhi').value = +hi.toPrecision(4);
  }
  function paintBar() {
    const sc = curScalar();
    $('vrange').hidden = !sc;
    if (!sc) return;
    const [lo, hi] = currentRange();
    V.drawBar($('vbar'), sc, lo, hi);
    $('vlolab').textContent = fmt(lo) + ' ' + V.SCALARS[sc].unit;
    $('vhilab').textContent = fmt(hi) + ' ' + V.SCALARS[sc].unit;
  }
  async function load(slot, crop) {
    const view = curView(), M = MANI();
    const e = M[crop]; if (!e) return;
    selected[slot] = crop;
    $('p' + slot).querySelector('.pick').value = crop;
    if (!Number.isFinite(parseFloat($('vlo').value))) autoRange();
    const sc = curScalar(), [lo, hi] = currentRange();
    await panels[slot].show(e, sc, lo, hi, view.surface);
    panels[slot].setCaps(capsOn);
    // the manifest's voxel_nm is the scale the mesh patch was built at (16 nm for
    // every crop), not the crop's acquisition voxel — take that from the table row
    const row = rows.find(r => r.crop === crop);
    const vox = row && row.voxel ? row.voxel + ' nm' : '';
    const box = view.surface === 'ecs' && e.cube_nm
      ? `${Math.round(e.cube_nm)} nm box at ${e.voxel_nm} nm` : '';
    $('p' + slot).querySelector('.vfoot').textContent =
      [e.tissue, e.region_group || e.anatomy, e.prep, vox, box]
        .filter(Boolean).join(' · ');
    if (linked && compare) {
      const other = slot === 'A' ? panels.B : panels.A;
      if (other && other.entry) panels[slot].syncFrom(other);
    }
    paintBar(); render();
  }
  function recolorAll() {
    const sc = curScalar(), [lo, hi] = currentRange();
    for (const s of ['A', 'B']) if (panels[s] && panels[s].entry) panels[s].recolor(sc, lo, hi);
    paintBar();
  }
  function toggleCompare() {
    compare = !compare;
    $('pB').hidden = !compare;
    $('hub').classList.toggle('solo', !compare);
    $('vlink').hidden = !compare;
    $('vswap').hidden = !compare;
    $('vcompare').textContent = compare ? 'Single view' : 'Compare two';
    if (compare && !selected.B) {
      const M = MANI();
      const list = rows.filter(passes).map(r => r.crop)
        .filter(c => c !== selected.A && M[c]);
      load('B', list[0] || Object.keys(M)[0]);
    }
    resizeSoon();
  }
  function resizeSoon() {
    setTimeout(() => { for (const s of ['A', 'B']) panels[s] && panels[s].resize(); }, 60);
  }

  /* ---------- draggable table width ---------- */
  const TW = 'ecs-tablew';
  function setTableWidth(px) {
    const min = 280, max = Math.max(min, innerWidth - 520);
    px = Math.max(min, Math.min(max, px));
    $('hub').style.setProperty('--tablew', px + 'px');
    try { localStorage.setItem(TW, px); } catch (e) {}
    resizeSoon();
  }
  (function initGutter() {
    try { const v = +localStorage.getItem(TW); if (v) setTableWidth(v); } catch (e) {}
    const g = $('gutter'); if (!g) return;
    let dragging = false;
    // listeners live on the document: pointer capture on a 6px strip is easy to
    // lose, and losing it mid-drag leaves the divider stuck to the cursor
    const move = e => {
      if (!dragging) return;
      e.preventDefault();
      setTableWidth(e.clientX - $('hub').getBoundingClientRect().left);
    };
    const stop = () => {
      if (!dragging) return;
      dragging = false; g.classList.remove('drag');
      document.body.style.userSelect = '';
    };
    g.addEventListener('pointerdown', e => {
      dragging = true; g.classList.add('drag');
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', stop);
    document.addEventListener('pointercancel', stop);
    // keyboard: the divider is focusable so it can be nudged without a mouse
    g.tabIndex = 0;
    g.setAttribute('role', 'separator');
    g.setAttribute('aria-label', 'Resize the table');
    g.addEventListener('keydown', e => {
      const cur = parseInt(getComputedStyle($('hub')).getPropertyValue('--tablew')) || 460;
      if (e.key === 'ArrowLeft') { setTableWidth(cur - 24); e.preventDefault(); }
      if (e.key === 'ArrowRight') { setTableWidth(cur + 24); e.preventDefault(); }
    });
    g.addEventListener('dblclick', () => setTableWidth(460));
  })();

  let surfaceShown = 'membrane';
  const haveSurface = sf => Object.keys(MANIfor(sf)).length > 0;
  V.mountSurfaceToggle($('vsurface'), surfaceShown, haveSurface);
  V.mountScalarSelect($('vview'), surfaceShown, 'mem-gap');

  async function switchSurface(sf) {
    if (sf === surfaceShown || !haveSurface(sf)) return;
    surfaceShown = sf;
    V.mountSurfaceToggle($('vsurface'), sf, haveSurface);
    // keep the same kind of colouring across the switch where it exists:
    // curvature stays curvature, and gap and width are both "how far apart"
    const same = { curvature: 'curvature', deviation: 'deviation',
                   gap: 'thickness', thickness: 'gap', width: 'gap', '': '' };
    const want = same[curScalar() || ''] || '';
    const match = V.VIEWS.find(v => v.surface === sf && v.ready &&
                                    (v.scalar || '') === want);
    V.mountScalarSelect($('vview'), sf, match ? match.id : undefined);
    $('vlo').value = ''; $('vhi').value = '';
    const M = MANI(), keys = Object.keys(M).sort();
    fillPicks();
    const pick = (w, fb) => (w && M[w]) ? w : fb;
    const a = pick(selected.A, keys[0]);
    const b = pick(selected.B, keys[1] || keys[0]);
    selected.A = selected.B = null;
    await load('A', a);
    if (compare) await load('B', b);
    for (const s of ['A', 'B']) panels[s] && panels[s].frame();
    syncCaps();
    autoRange(); recolorAll();
  }
  $('vsurface').onclick = e => {
    const b = e.target.closest('[data-surface]');
    if (b && !b.disabled) switchSurface(b.dataset.surface);
  };
  let capsOn = true;
  function syncCaps() {
    const has = !!(V.SURFACES && V.SURFACES[surfaceShown] || {}).caps;
    $('vcaps').hidden = !has;
    $('vcaps').classList.toggle('on', capsOn);
    $('vcaps').textContent = capsOn ? 'Cut faces solid' : 'Cut faces open';
    for (const s of ['A', 'B']) if (panels[s]) panels[s].setCaps(capsOn);
  }
  $('vcaps').onclick = () => { capsOn = !capsOn; syncCaps(); };

  $('vview').onchange = () => {
    $('vlo').value = ''; $('vhi').value = '';   // each view has its own range
    autoRange(); recolorAll();
  };
  $('vlo').oninput = recolorAll; $('vhi').oninput = recolorAll;
  $('vauto').onclick = () => { autoRange(); recolorAll(); };
  $('vcompare').onclick = toggleCompare;
  $('vswap').onclick = () => {
    const a = selected.A, b = selected.B;
    if (!a || !b) return;
    load('A', b); load('B', a);
  };
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

  document.querySelectorAll('details.tools').forEach(d => {
    const target = $(d.dataset.panel);
    if (!target) return;
    d.addEventListener('toggle', () => {
      target.hidden = !d.open;
      // opening a drawer pushes the hub down; it has to be re-measured
      fitHub();
    });
  });

  /* ---------- the hub fills whatever is left of the window ----------
     Hard-coding `calc(100vh - Npx)` was always wrong for somebody: the chrome
     above wraps to a different height at every width. Measure it instead. */
  function fitHub() {
    const hub = $('hub');
    // the narrow tier sets height:auto !important, so this is a no-op there
    const top = hub.getBoundingClientRect().top + window.scrollY;
    const h = Math.max(420, window.innerHeight - top - 22);
    if (Math.abs(parseFloat(hub.style.height) - h) < 1) return;
    hub.style.height = h + 'px';
    resizeSoon();
  }
  addEventListener('resize', fitHub);
  // the chrome above the hub changes height on its own -- the Neuroglancer note
  // arrives after first paint, the toolbar rewraps, a drawer opens -- so watch
  // it rather than measuring once and hoping
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => fitHub());
    for (const el of [document.querySelector('.toolbar'), $('facets'), $('ranges'), $('colpick')])
      if (el) ro.observe(el);
  }

  buildFacets(); buildRanges(); buildCols(); render();
  initPanels(); fillPicks();
  fitHub();
  addEventListener('resize', resizeSoon);
  (async () => {
    const first = Object.keys(MANI()).sort();
    await load('A', first[0]);
    await load('B', first[1] || first[0]);
    syncCaps();
  })();
})();

/* ---------- Neuroglancer links ----------------------------------------
   A crop's link opens its whole dataset: the EM image plus every annotated
   crop in that dataset as its own layer, centred on the crop you clicked. */
(function () {
  const $ = id => document.getElementById(id);
  // 'auto' takes the public copy wherever it is genuinely servable and falls
  // back to Janelia for the rest, so a link is public whenever it can be
  let NG = null;
  const baseFor = d => NG.sources[d.s3_ready ? 's3' : 'nrs'].base;

  function state(crop) {
    const dsName = NG.crop_dataset[crop]; if (!dsName) return null;
    const d = NG.datasets[dsName]; if (!d) return null;
    const base = `zarr://${baseFor(d)}/${dsName}/${dsName}.zarr/recon-1`;
    const em = { type: 'image', source: `${base}/em/${d.em}`, name: 'em' };
    if (d.shader) { em.shaderControls = d.shader; em.tab = 'rendering'; }
    const layers = [em];
    for (const c of d.crops) {
      layers.push({ type: 'segmentation',
        source: `${base}/labels/groundtruth/${c}/all`,
        name: c, visible: true, ...(c === crop ? { tab: 'segments' } : {}) });
    }
    const s = { layers, selectedLayer: { layer: crop }, layout: '4panel' };
    const c = NG.centre_nm[crop];
    if (c) {
      const v = d.voxel_nm || 8;
      s.dimensions = { x: [v * 1e-9, 'm'], y: [v * 1e-9, 'm'], z: [v * 1e-9, 'm'] };
      s.position = c.map(x => +(x / v).toFixed(1));   // nm -> dataset voxels
    }
    return s;
  }

  window.ngURL = crop => {
    if (!NG) return null;
    const s = state(crop); if (!s) return null;
    return 'https://neuroglancer-demo.appspot.com/#!' +
      encodeURIComponent(JSON.stringify(s));
  };
  window.ngReady = () => !!NG;

  function note() {
    const n = document.getElementById('ngnote'); if (!n) return;
    const per = Object.entries(NG.datasets);
    const pub = per.filter(([, d]) => d.s3_ready).map(([k]) => k);
    n.innerHTML = pub.length
      ? `Public copy for <code>${pub.join('</code>, <code>')}</code>; the other ` +
        `${per.length - pub.length} still need the Janelia VPN. ` +
        `<a href="reference.html#datasets">Per-dataset status.</a>`
      : 'None of these datasets are on the public bucket yet, so every link needs the Janelia VPN.';
  }

  fetch('data/neuroglancer.json').then(r => r.json()).then(j => {
    NG = j; note();
    if (window.refreshNgLinks) window.refreshNgLinks();
  }).catch(() => {});
})();

window.refreshNgLinks = function () {
  if (!window.ngReady || !window.ngReady()) return;
  document.querySelectorAll('a.nglink').forEach(a => {
    const u = window.ngURL(a.dataset.crop);
    if (u) { a.href = u; a.removeAttribute('aria-disabled'); }
    else { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); }
  });
};
