/* Membrane patch viewer, reusable so two of them can sit side by side and be
   driven together. Reads the same .bin layout the inspector uses:
     positions f32[nv*3] · indices u32[nf*3] · curvature f32[nv]
     · deviation f32[nv] · gap f32[nv]
   NaN marks boundary-uncertain vertices and renders neutral grey. */
(function () {
  const SCALARS = {
    gap:       { label: 'Gap to nearest cell', cmap: 'viridis', unit: 'nm' },
    curvature: { label: 'Signed curvature',    cmap: 'RdBu_r',  unit: '1/nm' },
    deviation: { label: 'Protrusion / indentation', cmap: 'RdBu_r', unit: 'nm' },
  };
  const NAN_GREY = [0.30, 0.31, 0.35];
  const PLAIN = 0xb9b2a3;          // unpainted surface: warm bone, reads in both themes

  /* What you can put in a panel. `surface` is which mesh, `scalar` is what
     colours it (null = the bare mesh). `ready:false` entries are listed but
     disabled: the ECS surfaces are coming and the menu should say so rather
     than pretend the analysis is membrane-only. Turning one on is a one-line
     change here once its data ships. */
  const VIEWS = [
    { id: 'mem',      group: 'Membrane surface', label: 'Mesh only',
      surface: 'membrane', scalar: null, ready: true },
    { id: 'mem-curv', group: 'Membrane surface', label: 'Curvature — morphology',
      surface: 'membrane', scalar: 'curvature', ready: true },
    { id: 'mem-dev',  group: 'Membrane surface', label: 'Protrusion / indentation — morphology',
      surface: 'membrane', scalar: 'deviation', ready: true },
    { id: 'mem-gap',  group: 'Membrane surface', label: 'Gap to nearest cell — distance',
      surface: 'membrane', scalar: 'gap', ready: true },
    { id: 'ecs',      group: 'ECS surface (not built yet)', label: 'Mesh only',
      surface: 'ecs', scalar: null, ready: false },
    { id: 'ecs-curv', group: 'ECS surface (not built yet)', label: 'Curvature — morphology',
      surface: 'ecs', scalar: 'curvature', ready: false },
    { id: 'ecs-wid',  group: 'ECS surface (not built yet)', label: 'Local width — thickness',
      surface: 'ecs', scalar: 'width', ready: false },
  ];
  const VIEW = Object.fromEntries(VIEWS.map(v => [v.id, v]));

  function mountViewSelect(sel, current) {
    let g = null, html = '';
    for (const v of VIEWS) {
      if (v.group !== g) { if (g) html += '</optgroup>'; g = v.group;
        html += `<optgroup label="${g}">`; }
      html += `<option value="${v.id}"${v.ready ? '' : ' disabled'}${
        v.id === current ? ' selected' : ''}>${v.label}</option>`;
    }
    sel.innerHTML = html + '</optgroup>';
  }
  const cache = new Map();

  async function loadBin(base, entry) {
    const key = entry.crop;
    if (cache.has(key)) return cache.get(key);
    const buf = await (await fetch(base + 'inspect/' + entry.bin)).arrayBuffer();
    const nv = entry.nverts, nf = entry.nfaces;
    let o = 0;
    const pos = new Float32Array(buf, o, nv * 3);           o += nv * 12;
    const idx = new Uint32Array(buf, o, nf * 3);            o += nf * 12;
    const cur = new Float32Array(buf, o, nv);               o += nv * 4;
    const dev = new Float32Array(buf, o, nv);               o += nv * 4;
    const gap = new Float32Array(buf, o, nv);
    const data = { pos, idx, scal: { curvature: cur, deviation: dev, gap } };
    cache.set(key, data);
    return data;
  }

  class Panel {
    constructor(host, base) {
      this.host = host; this.base = base; this.entry = null;
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 1e6);
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
      host.appendChild(this.renderer.domElement);
      this.scene.add(new THREE.AmbientLight(0xffffff, 0.62));
      const d1 = new THREE.DirectionalLight(0xffffff, 0.72); d1.position.set(1, 1, 2);
      const d2 = new THREE.DirectionalLight(0xffffff, 0.38); d2.position.set(-1, -1, -1);
      this.scene.add(d1, d2);
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.mesh = null;
      this.onMove = null;
      this.controls.addEventListener('change', () => { if (this.onMove) this.onMove(this); });
      const loop = () => { this.controls.update(); this.renderer.render(this.scene, this.camera);
        requestAnimationFrame(loop); };
      loop();
      this.resize();
      // the canvas is sized by CSS (100% of the stage) and setSize's third
      // argument leaves that alone, so this only matches the drawing buffer to
      // the box. A ResizeObserver catches the divider drag and the layout-tier
      // switch, which a window resize listener alone misses.
      if (window.ResizeObserver) new ResizeObserver(() => this.resize()).observe(host);
      else addEventListener('resize', () => this.resize());
    }
    resize() {
      const w = this.host.clientWidth, h = this.host.clientHeight;
      if (!w || !h) return;
      this.renderer.setSize(w, h, false);
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    }
    async show(entry, scalar, lo, hi) {
      this.entry = entry;
      const d = await loadBin(this.base, entry);
      if (this.mesh) { this.scene.remove(this.mesh); this.mesh.geometry.dispose(); }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(d.pos, 3));
      g.setIndex(new THREE.BufferAttribute(d.idx, 1));
      g.computeVertexNormals();
      this.geom = g; this.data = d;
      this.mesh = new THREE.Mesh(g, new THREE.MeshPhongMaterial({
        vertexColors: true, side: THREE.DoubleSide, flatShading: false, shininess: 12 }));
      this.scene.add(this.mesh);
      this.recolor(scalar, lo, hi);
      this.frame();
    }
    frame() {
      if (!this.geom) return;
      this.geom.computeBoundingSphere();
      const s = this.geom.boundingSphere;
      this.controls.target.copy(s.center);
      const d = s.radius / Math.sin((this.camera.fov * Math.PI / 180) / 2) * 0.92;
      this.camera.position.set(s.center.x, s.center.y, s.center.z + d);
      this.camera.near = d / 100; this.camera.far = d * 12;
      this.camera.updateProjectionMatrix();
      this.controls.update();
    }
    recolor(scalar, lo, hi) {
      if (!this.geom) return;
      // the bare mesh: one material colour, so shape is all you read
      if (!scalar) {
        this.mesh.material.vertexColors = false;
        this.mesh.material.color.setHex(PLAIN);
        this.mesh.material.needsUpdate = true;
        return;
      }
      if (!this.mesh.material.vertexColors) {
        this.mesh.material.vertexColors = true;
        this.mesh.material.color.setHex(0xffffff);
        this.mesh.material.needsUpdate = true;
      }
      const vals = this.data.scal[scalar];
      if (!vals) return;
      const lut = window.CMAPS[SCALARS[scalar].cmap], n = lut.length - 1;
      const N = vals.length, col = new Float32Array(N * 3), span = (hi - lo) || 1e-9;
      for (let i = 0; i < N; i++) {
        const v = vals[i];
        if (v !== v) { col[i*3] = NAN_GREY[0]; col[i*3+1] = NAN_GREY[1]; col[i*3+2] = NAN_GREY[2]; continue; }
        let t = (v - lo) / span; t = t < 0 ? 0 : t > 1 ? 1 : t;
        const c = lut[Math.round(t * n)];
        col[i*3] = c[0]; col[i*3+1] = c[1]; col[i*3+2] = c[2];
      }
      this.geom.setAttribute('color', new THREE.BufferAttribute(col, 3));
    }
    syncFrom(other) {
      this.camera.position.copy(other.camera.position);
      this.camera.quaternion.copy(other.camera.quaternion);
      this.controls.target.copy(other.controls.target);
      this.camera.updateProjectionMatrix();
    }
  }

  window.ECSViewer = { Panel, SCALARS, VIEWS, VIEW, mountViewSelect, drawBar };

  function drawBar(canvas, scalar, lo, hi) {
    const w = canvas.clientWidth || 220;
    canvas.width = w; canvas.height = 12;
    const ctx = canvas.getContext('2d');
    const lut = window.CMAPS[SCALARS[scalar].cmap], n = lut.length - 1;
    for (let x = 0; x < w; x++) {
      const c = lut[Math.round(x / (w - 1) * n)];
      ctx.fillStyle = `rgb(${c[0]*255|0},${c[1]*255|0},${c[2]*255|0})`;
      ctx.fillRect(x, 0, 1, 12);
    }
  }
})();
