#!/usr/bin/env python3
"""
Build the membrane-patch INSPECTOR: a three.js viewer that loads raw scalar
values per crop and colormaps them client-side, with a scalar selector,
real-time min/max sliders, and a live colorbar legend.

Per crop it writes figures/membranes/inspect/<crop>.bin (geometry + raw
curvature/deviation/gap), manifest_inspect.json, colormaps.js (LUTs generated
from matplotlib so colors match the PNG/GLB galleries), and inspector.html.

Usage:
    python scripts/make_inspector.py                 # bile-canaliculus proof set
    python scripts/make_inspector.py --all
    python scripts/make_inspector.py --crops crop1039 crop1072
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

from ecs import config as cfg
from scripts.render_membrane_patch import bin_from_patch, build_patch

OUT_DIR = Path(__file__).resolve().parents[1] / "figures" / "membranes"
INSPECT_DIR = OUT_DIR / "inspect"
PROOF = ["crop1039", "crop1040", "crop1042", "crop1072", "crop1073", "crop1074", "crop1075"]


def write_colormaps() -> None:
    def lut(name, n=256):
        cm = matplotlib.colormaps[name]
        return [[round(float(v), 4) for v in cm(i / (n - 1))[:3]] for i in range(n)]
    js = "window.CMAPS=" + json.dumps({"viridis": lut("viridis"),
                                       "RdBu_r": lut("RdBu_r")}) + ";"
    (OUT_DIR / "colormaps.js").write_text(js)


INSPECTOR_HTML = r"""<!doctype html><html><head><meta charset=utf-8>
<title>ECS membrane inspector</title>
<style>
 html,body{margin:0;height:100%;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1a1d21}
 #app{display:flex;height:100vh}
 #side{width:300px;overflow:auto;border-right:1px solid #e3e6ea;padding:12px;box-sizing:border-box;background:#fafbfc}
 #side h1{font-size:16px;margin:0 0 4px} #side p{font-size:12px;color:#666;margin:4px 0 12px}
 #side a{color:#1971c2}
 .grp{font-size:12px;font-weight:600;color:#1565c0;margin:12px 0 4px}
 .crop{display:block;width:100%;text-align:left;border:1px solid #cdd3da;background:#fff;border-radius:5px;
   padding:5px 8px;margin:3px 0;cursor:pointer;font-size:12px}
 .crop:hover{background:#eef4fc} .crop.active{background:#1565c0;color:#fff;border-color:#1565c0}
 .chem{color:#d9480f} .hpf{color:#1971c2} .crop.active .chem,.crop.active .hpf{color:#fff}
 #main{flex:1;position:relative;background:#fff} #view{width:100%;height:100%;display:block}
 #ctrl{position:absolute;top:12px;right:12px;background:rgba(255,255,255,.94);border:1px solid #e3e6ea;
   border-radius:8px;padding:12px;width:280px;box-shadow:0 2px 8px rgba(0,0,0,.08);font-size:13px}
 #ctrl select{width:100%;padding:4px;margin:4px 0 10px} #ctrl label{font-size:12px;color:#555}
 .row{display:flex;align-items:center;gap:6px;margin:3px 0} .row input[type=range]{flex:1}
 .row input[type=number]{width:74px;font-size:12px;padding:2px}
 #bar{width:100%;height:16px;border:1px solid #ccc;border-radius:3px;margin-top:8px}
 #barlab{display:flex;justify-content:space-between;font-size:11px;color:#555}
 #title{position:absolute;top:12px;left:12px;background:rgba(255,255,255,.9);padding:6px 10px;
   border-radius:6px;font-size:13px;border:1px solid #e3e6ea}
 #hint{position:absolute;bottom:10px;left:12px;font-size:11px;color:#888}
</style></head><body>
<div id=app>
 <div id=side>
   <h1>ECS membrane inspector</h1>
   <p>Pick a crop, choose a scalar, drag the min/max sliders to rescale the
   colormap live. <a href="../home.html">project home</a> ·
   <a href="membranes_3d.html">3D gallery</a> ·
   <a href="index.html">maps</a></p>
   <div id=list></div>
 </div>
 <div id=main>
   <canvas id=view></canvas>
   <div id=title>—</div>
   <div id=ctrl>
     <label>Scalar</label>
     <select id=scalar></select>
     <div class=row><label style="width:30px">min</label>
       <input type=range id=lo><input type=number id=lon step=any></div>
     <div class=row><label style="width:30px">max</label>
       <input type=range id=hi><input type=number id=hin step=any></div>
     <canvas id=bar></canvas>
     <div id=barlab><span id=blo></span><span id=bhi></span></div>
   </div>
   <div id=hint>drag = rotate · scroll = zoom · right-drag = pan</div>
 </div>
</div>
<script src="three.min.js"></script>
<script src="OrbitControls.js"></script>
<script src="colormaps.js"></script>
<script>
const SCALARS={
  curvature:{label:'Signed curvature (1/nm)',cmap:'RdBu_r',unit:'1/nm'},
  deviation:{label:'Protrusion / indentation (nm)',cmap:'RdBu_r',unit:'nm'},
  gap:{label:'Gap to nearest cell (nm)',cmap:'viridis',unit:'nm'},
};
let MAN=[], cur=null, scalarsData={}, geom=null, mesh=null;
let scene,camera,renderer,controls;

function initGL(){
  const cv=document.getElementById('view');
  renderer=new THREE.WebGLRenderer({canvas:cv,antialias:true});
  renderer.setPixelRatio(window.devicePixelRatio);
  scene=new THREE.Scene(); scene.background=new THREE.Color(0xffffff);
  camera=new THREE.PerspectiveCamera(45,1,1,1e6);
  controls=new THREE.OrbitControls(camera,renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff,0.6));
  const d1=new THREE.DirectionalLight(0xffffff,0.7); d1.position.set(1,1,2); scene.add(d1);
  const d2=new THREE.DirectionalLight(0xffffff,0.4); d2.position.set(-1,-1,-1); scene.add(d2);
  resize(); window.addEventListener('resize',resize);
  (function loop(){requestAnimationFrame(loop);controls.update();renderer.render(scene,camera);})();
}
function resize(){const m=document.getElementById('main');
  renderer.setSize(m.clientWidth,m.clientHeight,false);
  camera.aspect=m.clientWidth/m.clientHeight;camera.updateProjectionMatrix();}

function buildList(){
  const order=['Liver','Heart','Kidney','Cortex']; const byT={};
  MAN.forEach(r=>{(byT[r.tissue]=byT[r.tissue]||[]).push(r);});
  const list=document.getElementById('list');
  order.filter(t=>byT[t]).forEach(t=>{
    const h=document.createElement('div');h.className='grp';h.textContent=t;list.appendChild(h);
    byT[t].sort((a,b)=>(a.region_group||'~').localeCompare(b.region_group||'~')||a.prep.localeCompare(b.prep));
    byT[t].forEach(r=>{
      const b=document.createElement('button');b.className='crop';b.id='c-'+r.crop;
      const pc=r.prep==='Chemical'?'chem':'hpf';
      b.innerHTML=`<b class=${pc}>${r.prep[0]}</b> ${r.crop} · ${r.region_group||'—'} `+
        `<span style="color:#888">${r.nfaces.toLocaleString()} f</span>`;
      b.onclick=()=>loadCrop(r);list.appendChild(b);
    });
  });
}

function loadCrop(r){
  document.querySelectorAll('.crop').forEach(b=>b.classList.remove('active'));
  document.getElementById('c-'+r.crop).classList.add('active');
  cur=r;
  fetch('inspect/'+r.bin).then(x=>x.arrayBuffer()).then(buf=>{
    const nv=r.nverts, nf=r.nfaces;
    let o=0;
    const pos=new Float32Array(buf,o,nv*3); o+=nv*3*4;
    const idx=new Uint32Array(buf,o,nf*3); o+=nf*3*4;
    scalarsData.curvature=new Float32Array(buf,o,nv); o+=nv*4;
    scalarsData.deviation=new Float32Array(buf,o,nv); o+=nv*4;
    scalarsData.gap=new Float32Array(buf,o,nv);
    if(mesh){scene.remove(mesh);geom.dispose();mesh.material.dispose();}
    geom=new THREE.BufferGeometry();
    geom.setAttribute('position',new THREE.BufferAttribute(pos,3));
    geom.setIndex(new THREE.BufferAttribute(idx,1));
    geom.computeVertexNormals();
    const mat=new THREE.MeshStandardMaterial({vertexColors:true,roughness:0.85,
      metalness:0.0,side:THREE.DoubleSide});
    mesh=new THREE.Mesh(geom,mat); scene.add(mesh);
    frame(geom);
    document.getElementById('title').textContent=
      `${r.tissue} ${r.region_group||''} — ${r.prep} (${r.crop}, cell ${r.cell})`;
    setScalar(document.getElementById('scalar').value||'gap');
  });
}
function frame(g){
  g.computeBoundingBox();const bb=g.boundingBox;
  const c=new THREE.Vector3();bb.getCenter(c);
  const sz=new THREE.Vector3();bb.getSize(sz);const r=Math.max(sz.x,sz.y,sz.z);
  controls.target.copy(c);
  camera.position.set(c.x+r*0.8,c.y+r*0.6,c.z+r*1.6);
  camera.near=r/100;camera.far=r*100;camera.updateProjectionMatrix();controls.update();
}

function setScalar(s){
  const sc=SCALARS[s], rng=cur.ranges[s];
  const [bmin,bmax]=rng.bounds, [dlo,dhi]=rng.default;
  for(const [el,val] of [['lo',dlo],['hi',dhi]]){
    const sl=document.getElementById(el);
    sl.min=bmin; sl.max=bmax; sl.step=(bmax-bmin)/400||1e-6; sl.value=val;
    document.getElementById(el+'n').value=Number(val.toFixed(4));
  }
  applyColors();
}
function syncFromNumber(which){
  const n=document.getElementById(which+'n');
  document.getElementById(which).value=n.value; applyColors();
}
function applyColors(){
  if(!geom||!cur) return;
  const s=document.getElementById('scalar').value;
  let lo=parseFloat(document.getElementById('lo').value);
  let hi=parseFloat(document.getElementById('hi').value);
  document.getElementById('lon').value=Number(lo.toFixed(4));
  document.getElementById('hin').value=Number(hi.toFixed(4));
  const lut=window.CMAPS[SCALARS[s].cmap], n=lut.length-1;
  const vals=scalarsData[s], N=vals.length, col=new Float32Array(N*3);
  const span=(hi-lo)||1e-9;
  for(let i=0;i<N;i++){
    const v=vals[i];
    // NaN gap values mark boundary-uncertain vertices — render neutral grey
    // so the rim doesn't get painted with the in-volume EDT's overestimate.
    if(v!==v){ col[i*3]=0.87; col[i*3+1]=0.87; col[i*3+2]=0.87; continue; }
    let t=(v-lo)/span; t=t<0?0:t>1?1:t;
    const c=lut[Math.round(t*n)];
    col[i*3]=c[0];col[i*3+1]=c[1];col[i*3+2]=c[2];
  }
  geom.setAttribute('color',new THREE.BufferAttribute(col,3));
  drawBar(s,lo,hi);
}
function drawBar(s,lo,hi){
  const cvs=document.getElementById('bar');const w=cvs.clientWidth||256;cvs.width=w;cvs.height=16;
  const ctx=cvs.getContext('2d');const lut=window.CMAPS[SCALARS[s].cmap],n=lut.length-1;
  for(let x=0;x<w;x++){const c=lut[Math.round(x/(w-1)*n)];
    ctx.fillStyle=`rgb(${c[0]*255|0},${c[1]*255|0},${c[2]*255|0})`;ctx.fillRect(x,0,1,16);}
  document.getElementById('blo').textContent=lo.toFixed(3)+' '+SCALARS[s].unit;
  document.getElementById('bhi').textContent=hi.toFixed(3)+' '+SCALARS[s].unit;
}

fetch('manifest_inspect.json').then(x=>x.json()).then(m=>{
  MAN=m.filter(r=>r.bin); initGL(); buildList();
  const sel=document.getElementById('scalar');
  Object.keys(SCALARS).forEach(k=>{const o=document.createElement('option');
    o.value=k;o.textContent=SCALARS[k].label;sel.appendChild(o);});
  sel.value='gap'; sel.onchange=()=>setScalar(sel.value);
  ['lo','hi'].forEach(e=>document.getElementById(e).oninput=applyColors);
  ['lon','hin'].forEach(e=>document.getElementById(e).onchange=()=>syncFromNumber(e.slice(0,2)));
  if(MAN.length) loadCrop(MAN[0]);
});
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--voxel", type=float, default=16.0)
    args = ap.parse_args()

    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    write_colormaps()
    (OUT_DIR / "inspector.html").write_text(INSPECTOR_HTML)

    crops = list(cfg.active_crops())
    if not args.all:
        wanted = set(args.crops) if args.crops else set(PROOF)
        crops = [c for c in crops if c.crop in wanted]

    records: list[dict] = []
    for i, crop in enumerate(crops, 1):
        try:
            p = build_patch(crop, voxel=args.voxel)
            meta = bin_from_patch(p, INSPECT_DIR / f"{crop.crop}.bin")
            records.append(meta)
            print(f"[{i}/{len(crops)}] {crop.crop} OK "
                  f"({meta['nverts']:,} verts)", flush=True)
        except Exception as e:  # noqa: BLE001
            records.append({"crop": crop.crop, "tissue": crop.tissue,
                            "prep": crop.prep, "region_group": crop.region_group,
                            "error": f"{type(e).__name__}: {e}"})
            print(f"[{i}/{len(crops)}] {crop.crop} FAILED: {e}", flush=True)
            traceback.print_exc()
        (OUT_DIR / "manifest_inspect.json").write_text(json.dumps(records, indent=1))

    print(f"\nDone. Inspector: {OUT_DIR / 'inspector.html'}")


if __name__ == "__main__":
    main()
