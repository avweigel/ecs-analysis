#!/usr/bin/env python3
"""Build docs/explore.html — the metric explorer, on the shared site shell.
Reads data/all_metrics_long.csv and data/metrics.json at runtime."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh
from build_figures_page import FIG_STYLE, family_block, sections_html

ROOT = Path(__file__).resolve().parent.parent

EXTRA = """<style>
 .strip{padding:0}
 .row{display:grid;grid-template-columns:200px 1fr 96px;gap:var(--s4);align-items:center;
      padding:9px 0;border-bottom:1px solid var(--rule)}
 .row:hover{background:var(--sunk)}
 .row:last-child{border-bottom:0}
 .row .gname{font-size:var(--t4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .row .gname small{color:var(--ink-3);display:block;font-size:var(--t5)}
 .row .ns{font-size:var(--t5);color:var(--ink-3);text-align:right;font-variant-numeric:tabular-nums}
 @media(max-width:760px){.row{grid-template-columns:1fr;gap:4px}.row .ns{text-align:left}}
 svg{display:block}
 .axis text{font-size:10.5px;fill:var(--ink-3)}
 .gl{stroke:var(--rule)}
 #about{margin:2px 0 14px}
 #about h2{margin:0 0 3px;font-size:var(--t2)}
 #about .u{color:var(--ink-3);font-size:var(--t4);margin-bottom:var(--s2)}
 #about p{margin:0;color:var(--ink-2);font-size:var(--t3);max-width:72ch}
 details.cav{margin-top:9px}
 details.cav summary{cursor:pointer;font-size:var(--t4);color:var(--accent);
   list-style:none;display:inline-flex;align-items:center;gap:6px;padding:3px 0}
 details.cav summary::-webkit-details-marker{display:none}
 details.cav summary::before{content:"▸";display:inline-block;transition:transform .15s}
 details.cav[open] summary::before{transform:rotate(90deg)}
 .cavbody{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}
 .cavbody .callout{margin:0}
 @media(max-width:900px){.cavbody{grid-template-columns:1fr}}
 circle[data-c]{cursor:crosshair}
</style>"""

JS = r"""
<script>
const $=id=>document.getElementById(id);
const PREP={Chemical:'chem','Rapid HPF':'hpf'};
let ROWS=[], DICT={metrics:{},families:{},runs:{}};

function parseCSV(t){
  const L=t.split(/\r?\n/).filter(Boolean), h=L[0].split(',');
  return L.slice(1).map(l=>{const p=l.split(','),o={};
    h.forEach((k,i)=>o[k]=p[i]);
    o.value=parseFloat(o.value); o.analysis_voxel_nm=parseFloat(o.analysis_voxel_nm);
    return o;});
}
const uniq=a=>[...new Set(a)].filter(v=>v!==undefined&&v!=='');
const med=a=>{if(!a.length)return NaN;const s=[...a].sort((x,y)=>x-y),m=s.length>>1;
  return s.length%2?s[m]:(s[m-1]+s[m])/2};
const fmt=v=>{const a=Math.abs(v);
  if(a===0)return '0';
  if(a<0.001||a>=1e6)return v.toExponential(2);
  if(a<1)return v.toPrecision(3);
  if(a<100)return v.toFixed(2);
  return v.toLocaleString(undefined,{maximumFractionDigits:0})};
const label=c=>(DICT.metrics[c]||{}).label||c;
const unit=c=>(DICT.metrics[c]||{}).unit||'';

function fill(sel,vals,cur,labeller){
  sel.innerHTML=vals.map(v=>{
    const txt=labeller?labeller(v):v;
    return `<option value="${String(v).replace(/"/g,'&quot;')}"${v===cur?' selected':''}>${txt}</option>`;
  }).join('');
  if(cur!==undefined&&vals.includes(cur))sel.value=cur;
}
function sel(){return {run:$('run').value,fam:$('fam').value,met:$('met').value,
  reg:$('reg').value,
  grp:$('grp').value,tis:$('tis').value,vox:$('vox').value};}

function refreshOptions(pre){
  const s=pre||sel();
  fill($('run'),uniq(ROWS.map(r=>r.run)).sort(),s.run,v=>(DICT.runs[v]||{}).label||v);
  const inRun=ROWS.filter(r=>r.run===$('run').value);
  fill($('fam'),uniq(inRun.map(r=>r.metric_family)).sort(),s.fam,
       v=>(DICT.families[v]||{}).label||v.replace(/_/g,' '));
  const inFam=inRun.filter(r=>r.metric_family===$('fam').value);
  fill($('met'),uniq(inFam.map(r=>r.metric)).sort((a,b)=>label(a).localeCompare(label(b))),
       s.met,label);
  fill($('tis'),['All tissues',...uniq(ROWS.map(r=>r.tissue)).sort()],s.tis);
  // regions follow the tissue, so the two filters cannot contradict each other
  const inTis=(s.tis&&s.tis!=='All tissues')?ROWS.filter(r=>r.tissue===s.tis):ROWS;
  fill($('reg'),['All regions',...uniq(inTis.map(r=>r.region_group)).filter(Boolean).sort()],
       s.reg);
  fill($('vox'),['All',...uniq(inFam.map(r=>r.analysis_voxel_nm)).sort((a,b)=>a-b).map(String)],s.vox);
}

function describe(){
  const m=DICT.metrics[$('met').value]||{}, f=DICT.families[$('fam').value]||{},
        r=DICT.runs[$('run').value]||{};
  const cav=(f.caveat?`<div class="callout warn"><b>This metric.</b> ${f.caveat}</div>`:'')
           +(r.caveat?`<div class="callout"><b>This run.</b> ${r.caveat}</div>`:'');
  $('about').innerHTML=
    `<h2>${m.label||$('met').value}</h2>`+
    `<div class="u">${m.unit?m.unit+' · ':''}${f.label||''} · ${r.label||''}</div>`+
    `<p>${m.blurb||''}</p>`+
    (cav?`<details class="cav"><summary>Two things to know before reading this</summary>
          <div class="cavbody">${cav}</div></details>`:'');
}

/* One slice, applied everywhere: the live plot, the at-a-glance grid, the
   table and the standing panels all answer to these. */
function slice(rows,s){
  let d=rows;
  if(s.tis&&s.tis!=='All tissues')d=d.filter(r=>r.tissue===s.tis);
  if(s.reg&&s.reg!=='All regions')d=d.filter(r=>(r.region_group||'')===s.reg);
  if(s.vox&&s.vox!=='All')d=d.filter(r=>String(r.analysis_voxel_nm)===s.vox);
  return d;
}

/* Cliff's delta: the chance a chemical crop reads higher than an HPF one,
   minus the chance it reads lower. Non-parametric, and it survives the tiny
   group sizes here better than a difference of means would. */
function cliff(a,b){
  if(!a.length||!b.length)return NaN;
  let gt=0,lt=0;
  for(const x of a)for(const y of b){ if(x>y)gt++; else if(x<y)lt++; }
  return (gt-lt)/(a.length*b.length);
}

/* The eleven metrics the effect matrix uses, so the live summary and the
   published panel are answering with the same numbers. */
const GLANCE=[['ecs_fraction','ECS fraction'],
  ['narrow_percentiles_nm_p50','ECS width p50'],
  ['percentiles_nm_p50','Cell-to-cell gap p50'],
  ['contact_fractions_p40','Contact under 40 nm'],
  ['sa_v_ecs_per_nm','SA:V (ECS)'],
  ['cell_density_per_um3','Cell density'],
  ['roughness_rms_nm_p60','Roughness 60 nm'],
  ['curvature_std_per_nm','Curvature spread'],
  ['fraction_concave','Fraction concave'],
  ['protrusion_density_per_um2','Protrusion density'],
  ['indentation_density_per_um2','Indentation density']];

function drawGlance(){
  const s=sel(), host=$('glance'); if(!host)return;
  const box=slice(ROWS.filter(r=>r.run===s.run&&Number.isFinite(r.value)),s);
  const crops=new Set(box.map(r=>r.crop));
  const nc=new Set(box.filter(r=>r.prep==='Chemical').map(r=>r.crop)).size;
  const nh=new Set(box.filter(r=>r.prep==='Rapid HPF').map(r=>r.crop)).size;
  $('glancecount').innerHTML=
    `<b>${crops.size}</b> crop${crops.size===1?'':'s'} in this slice &mdash; `+
    `<span class="tag chem">${nc} chemical</span> <span class="tag hpf">${nh} rapid HPF</span>`+
    (Math.min(nc,nh)<2?' <span class="flag">an arm of one or none: no comparison</span>':'');
  const W=232,H=74,PAD=10;
  host.innerHTML=GLANCE.map(([met,lab])=>{
    const d=box.filter(r=>r.metric===met);
    if(!d.length)return '';
    const C=d.filter(r=>r.prep==='Chemical'), H2=d.filter(r=>r.prep==='Rapid HPF');
    const c=C.map(r=>r.value), h=H2.map(r=>r.value);
    const all=c.concat(h);
    const lo=Math.min(...all), hi=Math.max(...all), span=(hi-lo)||1;
    const x=v=>PAD+(v-lo)/span*(W-2*PAD);
    // every dot names its crop and value: at a glance first, then on inspection
    const dot=(r,y,cl)=>`<circle cx="${x(r.value).toFixed(1)}" cy="${y}" r="3.1" class="gdot ${cl}"><title>${
      r.crop} · ${r.prep} · ${fmt(r.value)}${unit(met)?' '+unit(met):''}</title></circle>`;
    const tick=(vals,y,cl)=>{const m=med(vals);return Number.isFinite(m)
      ?`<line x1="${x(m).toFixed(1)}" x2="${x(m).toFixed(1)}" y1="${y-8}" y2="${y+8}" class="gmed ${cl}"/>`:''};
    const dl=cliff(c,h);
    const dtxt=Number.isFinite(dl)?(dl>0?'+':'')+dl.toFixed(2):'&mdash;';
    const strength=Math.abs(dl)>=0.474?'large':Math.abs(dl)>=0.33?'medium'
      :Math.abs(dl)>=0.147?'small':'negligible';
    return `<button type="button" class="gcard" data-met="${met}"
      title="Open ${lab} in the plot below">
      <span class="gtop"><span class="glab">${lab}</span>
        <span class="gd ${Math.abs(dl)>=0.33?'on':''}">&delta; ${dtxt}</span></span>
      <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" aria-hidden="true">
        <line x1="${PAD}" x2="${W-PAD}" y1="${H/2}" y2="${H/2}" class="gaxis"/>
        ${C.map(r=>dot(r,H/2-13,'is-chem')).join('')}
        ${H2.map(r=>dot(r,H/2+13,'is-hpf')).join('')}
        ${tick(c,H/2-13,'is-chem')}${tick(h,H/2+13,'is-hpf')}
      </svg>
      <span class="gfoot">${strength}${Number.isFinite(dl)&&dl!==0?
        (dl>0?' &middot; chemical higher':' &middot; HPF higher'):''}</span>
    </button>`;
  }).join('')||'<p class="muted">No headline metric has values in this slice.</p>';
}

/* Standing panels answer to the slice too: with a region chosen, only that
   region's vignette is worth looking at. */
function syncPanels(){
  const s=sel();
  const reg=(s.reg&&s.reg!=='All regions')?s.reg:null;
  let shown=0, total=0;
  document.querySelectorAll('.fig[data-region]').forEach(f=>{
    total++;
    const hit=!reg||f.dataset.region===reg;
    f.hidden=!hit; if(hit)shown++;
  });
  const note=document.getElementById('vignote');
  if(note)note.innerHTML=reg
    ? `Showing <b>${shown}</b> of ${total}, for ${reg}. `+
      '<button type="button" class="btnlink" id="allregions">Show every region</button>'
    : `All ${total} regions with an arm on both sides.`;
  const sec=document.getElementById('vigsection');
  if(sec)sec.hidden=shown===0;
}

function draw(){
  const s=sel();
  let d=ROWS.filter(r=>r.run===s.run&&r.metric_family===s.fam&&r.metric===s.met
        &&Number.isFinite(r.value));
  d=slice(d,s);
  describe();
  // the headline comparison: both medians and the gap between them
  const RO=$('readout');
  const cm=med(d.filter(r=>r.prep==='Chemical').map(r=>r.value));
  const hm=med(d.filter(r=>r.prep==='Rapid HPF').map(r=>r.value));
  const u=unit(s.met);
  if(Number.isFinite(cm)&&Number.isFinite(hm)){
    const diff=cm-hm, pct=hm!==0?(diff/Math.abs(hm))*100:NaN;
    const dir=diff>0?'higher':'lower';
    RO.innerHTML=
      `<div class="side"><span class="lbl"><i class="sw" style="background:var(--chem)"></i>Chemical</span>
        <span class="big chem">${fmt(cm)}</span><span class="sub">${u||'median'}</span></div>`+
      `<div class="side"><span class="lbl"><i class="sw" style="background:var(--hpf)"></i>Rapid HPF</span>
        <span class="big hpf">${fmt(hm)}</span><span class="sub">${u||'median'}</span></div>`+
      `<div class="side delta"><span class="lbl">Difference</span>
        <span class="big">${diff>0?'+':''}${fmt(diff)}</span>
        <span class="sub">${Number.isFinite(pct)?Math.abs(pct).toFixed(0)+'% '+dir+' under chemical fixation':'&nbsp;'}</span></div>`;
  } else { RO.innerHTML=''; }

  const plot=$('plot');
  if(!d.length){plot.innerHTML='<p class="muted" style="padding:22px 0">No data for this combination.</p>';
    $('tbl').querySelector('thead').innerHTML='';$('tbl').querySelector('tbody').innerHTML='';
    $('note').textContent='';return;}

  plot.innerHTML='<div class="row"><div></div><div id="probe"></div><div class="ns"></div></div>';
  const W=Math.max(240,Math.round($('probe').getBoundingClientRect().width));
  const key=r=>(r[s.grp]||'(unassigned)');
  const groups=uniq(d.map(key)).sort();
  const vals=d.map(r=>r.value);
  const dmin=Math.min(...vals), dmax=Math.max(...vals);
  let lo=dmin,hi=dmax;
  if(lo===hi){const e=Math.abs(lo||1)*.05;lo-=e;hi+=e;}
  const pad=(hi-lo)*.06; lo-=pad; hi+=pad;
  if(dmin>=0&&lo<0)lo=0;
  if(dmax<=0&&hi>0)hi=0;
  const M=11, X=v=>M+((v-lo)/(hi-lo))*(W-2*M), H=36, R=5.5;

  let html='';
  const ticks=[lo,(lo+hi)/2,hi];
  html+=`<div class="row" style="border-bottom:1px solid var(--rule);padding-bottom:6px">
    <div></div><div><svg width="${W}" height="15" viewBox="0 0 ${W} 15" class="axis">
    ${ticks.map((t,i)=>{const a=i===0?'start':(i===2?'end':'middle');
      return `<text x="${X(t).toFixed(1)}" y="11" text-anchor="${a}">${fmt(t)}</text>`}).join('')}
    </svg><div style="font-size:11px;color:var(--ink-3);text-align:center;margin-top:-2px">
    ${unit($('met').value)||''}</div></div>
    <div class="ns">n chem / hpf</div></div>`;

  for(const g of groups){
    const gd=d.filter(r=>key(r)===g);
    const by={Chemical:gd.filter(r=>r.prep==='Chemical'),'Rapid HPF':gd.filter(r=>r.prep==='Rapid HPF')};
    let marks='';
    for(const prep of ['Chemical','Rapid HPF']){
      const arr=by[prep]; if(!arr.length)continue;
      const col=`var(--${PREP[prep]})`, y=prep==='Chemical'?H*.33:H*.67;
      arr.forEach(r=>{marks+=`<circle cx="${X(r.value).toFixed(2)}" cy="${y.toFixed(1)}" r="${R}"
        fill="${col}" fill-opacity=".8" stroke="var(--bg)" stroke-width="1.8"
        data-c="${r.crop}" data-p="${prep}" data-v="${r.value}" data-a="${r.anatomy||''}"
        data-x="${r.analysis_voxel_nm||''}"></circle>`;});
      if(arr.length<2)continue;
      const m=med(arr.map(r=>r.value));
      marks+=`<line x1="${X(m).toFixed(2)}" x2="${X(m).toFixed(2)}" y1="${(y-10).toFixed(1)}"
        y2="${(y+10).toFixed(1)}" stroke="${col}" stroke-width="2.5" stroke-linecap="round"></line>`;
    }
    const nc=by.Chemical.length, nh=by['Rapid HPF'].length;
    const th=n=>n<=1?`<span class="flag">${n}</span>`:n;
    html+=`<div class="row"><div class="gname">${g}${s.grp==='tissue'?'':
      `<small>${uniq(gd.map(r=>r.tissue)).join(', ')}</small>`}</div>
      <div><svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      <line class="gl" x1="${M}" x2="${W-M}" y1="${H/2}" y2="${H/2}"></line>${marks}</svg></div>
      <div class="ns">${th(nc)} / ${th(nh)}</div></div>`;
  }
  plot.innerHTML=html;

  const thin=groups.filter(g=>{const gd=d.filter(r=>key(r)===g);
    return gd.filter(r=>r.prep==='Chemical').length<=1||gd.filter(r=>r.prep==='Rapid HPF').length<=1;});
  $('note').innerHTML=`${d.length} crops in ${groups.length} groups.`+
    (thin.length?` <span class="flag">${thin.length} group${thin.length>1?'s':''}</span>
      (${thin.join(', ')}) ${thin.length>1?'have':'has'} an arm at n&nbsp;&le;&nbsp;1 and cannot
      support a comparison.`:'');

  TROWS=d.slice();
  drawTable();
}

/* ---- the table: same sorting and column filters as the crop page ---- */
let TROWS=[], tsort={k:'crop',dir:1};
const TCOLS=[['crop','Crop',0],['tissue','Tissue',1],['region_group','Region',1],
             ['anatomy','Anatomy',1],['prep','Prep',1],
             ['analysis_voxel_nm','Voxel nm',0],['value',null,0]];
const TFILT={tissue:new Set(),region_group:new Set(),anatomy:new Set(),prep:new Set()};
const TLABEL={tissue:'Tissue',region_group:'Region',anatomy:'Anatomy',prep:'Preparation'};
const tvals=k=>[...new Set(TROWS.map(r=>r[k]||''))].filter(Boolean).sort()
  .map(v=>({value:v,n:TROWS.filter(r=>(r[k]||'')===v).length}));
const tmenu=ECS.filterMenu({label:k=>TLABEL[k],values:tvals,state:k=>TFILT[k],
                            onchange:()=>drawTable()});

function drawTable(){
  const met=$('met').value;
  const keep=TROWS.filter(r=>Object.keys(TFILT).every(k=>
    !TFILT[k].size||TFILT[k].has(r[k]||'')));
  keep.sort((a,b)=>{const x=a[tsort.k],y=b[tsort.k];
    if(x===''||x==null)return 1; if(y===''||y==null)return -1;
    return (typeof x==='number'&&typeof y==='number'?x-y:
            (isFinite(x)&&isFinite(y)?parseFloat(x)-parseFloat(y):
             String(x).localeCompare(String(y))))*tsort.dir});
  const arrow=k=>tsort.k===k?`<i class="srt">${tsort.dir>0?'▲':'▼'}</i>`:'';
  const thd=$('tbl').querySelector('thead'), tb=$('tbl').querySelector('tbody');
  thd.innerHTML='<tr>'+TCOLS.map(([k,lab,cat])=>{
    const head=lab!==null?lab:label(met)+(unit(met)
      ?' <span style="font-weight:400;text-transform:none">('+unit(met)+')</span>':'');
    const num=(k==='analysis_voxel_nm'||k==='value')?' num':'';
    const wrap=k==='anatomy'?' wrap':'';
    const filt=cat?`<button class="fbtn${TFILT[k].size?' on':''}" data-f="${k}"
        title="Filter by ${TLABEL[k].toLowerCase()}">▾</button>`:'';
    return `<th class="sortable${num}${wrap}" data-k="${k}" title="Sort">${head}${arrow(k)}${filt}</th>`;
  }).join('')+'</tr>';
  tb.innerHTML=keep.map(r=>
    `<tr><td><a href="crops.html?crop=${r.crop}" title="Open ${r.crop} in the viewer">${r.crop}</a></td>
     <td>${r.tissue}</td><td>${r.region_group||''}</td>
     <td class="wrap">${r.anatomy||''}</td>
     <td><span class="tag ${PREP[r.prep]}">${r.prep}</span></td>
     <td class="num">${r.analysis_voxel_nm||''}</td><td class="num">${fmt(r.value)}</td></tr>`).join('');
  const n=keep.length, all=TROWS.length;
  const cap=document.getElementById('tblcount');
  if(cap)cap.textContent=n===all?`${all} crops`:`${n} of ${all} crops`;
}

document.addEventListener('click',e=>{
  const fb=e.target.closest('#tbl .fbtn');
  if(fb){e.stopPropagation();tmenu.open(fb.dataset.f,fb);return}
  const th=e.target.closest('#tbl thead th[data-k]');
  if(!th)return;
  const k=th.dataset.k;
  tsort.dir=(tsort.k===k)?-tsort.dir:1; tsort.k=k; drawTable();
});

document.addEventListener('mouseover',e=>{
  const c=e.target.closest('circle[data-c]'); if(!c)return;
  ECS.tip(`<b>${c.dataset.c}</b><div>${c.dataset.p}</div>`
    +`<div>${label($('met').value)}: ${fmt(parseFloat(c.dataset.v))} ${unit($('met').value)}</div>`
    +(c.dataset.a?`<div>${c.dataset.a}</div>`:'')
    +(c.dataset.x?`<div class="muted">${c.dataset.x} nm voxel</div>`:''), e);
});
document.addEventListener('mouseout',e=>{if(e.target.closest('circle[data-c]'))ECS.tip(null)});
function syncFamPanels(){
  const f=$('fam').value;
  document.querySelectorAll('#fampanels .fam').forEach(el=>{
    el.hidden = el.dataset.fam !== f;
  });
  // families the pipeline draws no standing panel for (the mesh-based topology
  // and the bm sensitivity) simply have nothing here
  const box=document.getElementById('fampanels');
  if(box) box.hidden = !box.querySelector('.fam:not([hidden])');
}
['run','fam','tis'].forEach(i=>$(i).addEventListener('change',
  ()=>{refreshOptions();draw();drawGlance();syncFamPanels();syncPanels()}));
['met','grp','vox','reg'].forEach(i=>$(i).addEventListener('change',
  ()=>{draw();drawGlance();syncPanels()}));

// a glance card promotes its metric into the plot below
document.addEventListener('click',e=>{
  const g=e.target.closest('.gcard'); if(g){
    const met=g.dataset.met;
    const row=ROWS.find(r=>r.metric===met);
    if(row){ $('fam').value=row.metric_family; refreshOptions();
             $('met').value=met; draw(); syncFamPanels();
             document.getElementById('live').scrollIntoView({behavior:'smooth',block:'start'}); }
    return;
  }
  if(e.target.id==='allregions'){ $('reg').value='All regions';
    draw(); drawGlance(); syncPanels(); }
});
let rt; addEventListener('resize',()=>{clearTimeout(rt);
  rt=setTimeout(()=>{draw();drawGlance()},150)});
document.addEventListener('ecs:theme',()=>{draw();drawGlance()});

Promise.all([
  fetch('data/all_metrics_long.csv').then(r=>r.text()),
  fetch('data/metrics.json').then(r=>r.json())
]).then(([csv,dict])=>{
  ROWS=parseCSV(csv); DICT=dict;
  /* the quantification panels link here by family and run, so a static panel
     and its live version are one click apart rather than two pages that look
     like they show the same thing twice */
  const q=new URLSearchParams(location.search);
  refreshOptions({run:q.get('run')||'native',
                  fam:q.get('fam')||'volume_fraction',
                  met:q.get('metric')||'ecs_fraction',
                  grp:q.get('grp')||'region_group',
                  tis:'All tissues',vox:'All'});
  draw(); drawGlance(); syncFamPanels(); syncPanels();
  const keep=()=>{const s=sel();const u=new URLSearchParams(
      {run:s.run,fam:s.fam,metric:s.met,grp:s.grp});
    history.replaceState(null,'',location.pathname+'?'+u.toString())};
  ['run','fam','met','grp'].forEach(i=>$(i).addEventListener('change',keep));
  keep();
}).catch(e=>{$('plot').innerHTML='<p class="muted">Could not load the data &mdash; '+e+'</p>'});
</script>"""


def main():
    html = sh.head("Analysis — ECS preservation", 0, EXTRA + FIG_STYLE)
    html += sh.nav("explore.html", 0)
    html += sh.pagehead_art("Analysis",
        "Every per-crop measurement the pipeline has produced, live at the top and as standing "
        "panels below. Each dot is one crop, chemical above the line and HPF below, with groups "
        'sharing one scale so they can be read against each other. '
        '<a href="reference.html#reading">How to read this.</a>')
    family_html, _ = family_block()
    standing, n_panels = sections_html()
    html += f"""<main class="after-head">

<nav class="onpage" aria-label="On this page">
  <span>On this page</span>
  <a href="#glancesec">At a glance</a>
  <a href="#live">One metric, live</a>
  <a href="#matrix">Every metric at once</a>
  <a href="#vignettes">One region, every metric</a>
  <a href="#renders">Pictures of the geometry</a>
</nav>

<div class="controls">
  <div class="ctl"><label for="run">Run</label><select id="run"></select></div>
  <div class="ctl"><label for="fam">Metric family</label><select id="fam"></select></div>
  <div class="ctl"><label for="met">Metric</label><select id="met" style="min-width:280px"></select></div>
  <div class="ctl"><label for="grp">Group by</label><select id="grp">
    <option value="region_group">Region</option><option value="tissue">Tissue</option>
    <option value="anatomy">Anatomy</option></select></div>
  <div class="ctl"><label for="tis">Tissue</label><select id="tis"></select></div>
  <div class="ctl"><label for="reg">Region</label><select id="reg"></select></div>
  <div class="ctl"><label for="vox">Analysis voxel</label><select id="vox"></select></div>
</div>

<h2 id="glancesec" class="sec-first">At a glance</h2>
<p class="lede" id="glancecount"></p>
<p class="note">Eleven headline metrics for the crops the filters above leave in, chemical over
rapid HPF, with Cliff's &delta; for each &mdash; the chance a chemical crop reads higher than an
HPF one, minus the chance it reads lower. Click any card to open that metric in the plot below.
Every number here is computed in the page from the same CSV the table reads.</p>
<div class="glance" id="glance"></div>

<h2 id="live">One metric, live</h2>
<div id="about"></div>
<div class="readout" id="readout"></div>

<div class="legend">
  <span class="item"><i class="sw" style="background:var(--chem)"></i>Chemical, one crop</span>
  <span class="item"><i class="sw" style="background:var(--hpf)"></i>Rapid HPF, one crop</span>
  <span class="item"><i class="sw line" style="background:var(--ink-3)"></i>group median</span>
  <span class="item"><b class="flag">n</b>&nbsp;arm with one crop or none</span>
</div>

<div class="strip" id="plot"><p class="muted" style="padding:22px 0">Loading&hellip;</p></div>
<p class="note" id="note"></p>

<div class="fampanels" id="fampanels">
  <h3>The standing panels for this family</h3>
  <p class="note">Pre-rendered by the pipeline, one for each resolution. The matched panel exists
  to be read against the native one: a difference that survives downsampling to 8&nbsp;nm is not
  explained by voxel size. These change with the family above.</p>
  {family_html}
</div>

<h2>Table view</h2>
<p class="note" style="margin-top:calc(var(--s3) * -1)">The same crops as the plot above, for the
metric you have selected. Click a heading to sort; the &#9662; on a column filters it;
a crop name opens it in the viewer. <span id="tblcount"></span></p>
<div class="card scroll"><table id="tbl"><thead></thead><tbody></tbody></table></div>
"""
    html += standing
    html += sh.footer(0) + "</main><div id=\"tip\"></div>" + JS + "</body></html>"
    (ROOT / "docs" / "explore.html").write_text(html)
    print("built docs/explore.html")


if __name__ == "__main__":
    main()
