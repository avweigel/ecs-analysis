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
  reg:$('reg').value,scale:$('scale').value,
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

let gOrder='effect';

/* ── the filter bar ──────────────────────────────────────────────────────
   One line naming the slice every panel below is drawn from, kept in view as
   you scroll. Anything left at its default is quiet; anything you have
   actually chosen is marked, so you can tell at a distance whether what you
   are looking at is the whole study or a corner of it. */
function sliceSum(){
  const el=$('slicesum'); if(!el)return;
  const s=sel();
  const bits=[];
  bits.push(`<b>${label(s.met)}</b>`);
  const run=(DICT.runs[s.run]||{}).label||s.run;
  bits.push(`<span>${run}</span>`);
  const opt=(v,dflt)=>v&&v!==dflt
    ? `<span class="set">${v}</span>` : `<span>${dflt}</span>`;
  bits.push(opt(s.tis,'All tissues'));
  bits.push(opt(s.reg,'All regions'));
  if(s.vox&&s.vox!=='All')bits.push(`<span class="set">${s.vox} nm voxel</span>`);
  const box=slice(ROWS.filter(r=>r.run===s.run&&Number.isFinite(r.value)),s);
  const n=new Set(box.map(r=>r.crop)).size;
  bits.push(`<span>${n} crop${n===1?'':'s'}</span>`);
  el.innerHTML=bits.join('<span class="sep"> &middot; </span>');
}

/* The bar carries the whole control grid at the top of the page, where there
   is room for it, and folds to the summary line once you have scrolled past
   it. Folding happens once, and only if you have not already chosen for
   yourself -- an interface that keeps re-deciding is worse than one that
   never decides. */
let barTouched=false;
function setBar(open){
  const fb=$('filterbar'), bt=$('slicetoggle'); if(!fb)return;
  fb.classList.toggle('shut',!open);
  bt.setAttribute('aria-expanded',open?'true':'false');
  bt.title=open?'Hide the filters':'Show the filters';
}

function drawGlance(){
  const s=sel(), host=$('glance'); if(!host)return;
  const box=slice(ROWS.filter(r=>r.run===s.run&&Number.isFinite(r.value)),s);
  const crops=new Set(box.map(r=>r.crop));
  const nc=new Set(box.filter(r=>r.prep==='Chemical').map(r=>r.crop)).size;
  const nh=new Set(box.filter(r=>r.prep==='Rapid HPF').map(r=>r.crop)).size;
  const thin=Math.min(nc,nh)<2;
  $('glancecount').innerHTML=
    `<b>${crops.size}</b> crop${crops.size===1?'':'s'}: `+
    `<span class="tag chem">${nc} chemical</span> <span class="tag hpf">${nh} rapid HPF</span>`+
    (thin?' &middot; <span class="flag">an arm of one or none, so nothing here is a comparison</span>':'');

  const W=232,H=64,PAD=10;
  const cards=[];
  for(const [met,lab] of GLANCE){
    const d=box.filter(r=>r.metric===met);
    if(!d.length)continue;
    const C=d.filter(r=>r.prep==='Chemical'), H2=d.filter(r=>r.prep==='Rapid HPF');
    const c=C.map(r=>r.value), h=H2.map(r=>r.value);
    const all=c.concat(h);
    const lo=Math.min(...all), hi=Math.max(...all), span=(hi-lo)||1;
    const x=v=>PAD+(v-lo)/span*(W-2*PAD);
    // every dot names its crop and value: at a glance first, then on inspection
    const dot=(r,y,cl)=>`<circle cx="${x(r.value).toFixed(1)}" cy="${y}" r="3.1" class="gdot ${cl}"><title>${
      r.crop} \u00b7 ${r.prep} \u00b7 ${fmt(r.value)}${unit(met)?' '+unit(met):''}</title></circle>`;
    const tick=(vals,y,cl)=>{const m=med(vals);return Number.isFinite(m)
      ?`<line x1="${x(m).toFixed(1)}" x2="${x(m).toFixed(1)}" y1="${y-8}" y2="${y+8}" class="gmed ${cl}"/>`:''};
    const dl=cliff(c,h);
    const ok=Number.isFinite(dl)&&c.length&&h.length;
    const mag=ok?Math.abs(dl):-1;
    const strength=!ok?'not comparable':mag>=0.474?'large':mag>=0.33?'medium'
      :mag>=0.147?'small':'negligible';
    // a bar for the delta, so the size is scannable without reading the number
    const bar=ok?`<span class="dbar"><i class="${dl>0?'pos':'neg'}"
      style="width:${(mag*50).toFixed(1)}%"></i></span>`:'<span class="dbar"></span>';
    cards.push({met,mag,html:`<button type="button" class="gcard${ok&&mag>=0.33?' strong':''}"
      data-met="${met}" title="Open ${lab} in the plot below">
      <span class="gtop"><span class="glab">${lab}</span>
        <span class="gd${ok&&mag>=0.33?' on':''}">${ok?(dl>0?'+':'')+dl.toFixed(2):'&mdash;'}</span></span>
      ${bar}
      <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" aria-hidden="true">
        <line x1="${PAD}" x2="${W-PAD}" y1="${H/2}" y2="${H/2}" class="gaxis"/>
        ${C.map(r=>dot(r,H/2-12,'is-chem')).join('')}
        ${H2.map(r=>dot(r,H/2+12,'is-hpf')).join('')}
        ${tick(c,H/2-12,'is-chem')}${tick(h,H/2+12,'is-hpf')}
      </svg>
      <span class="gfoot">${strength}${ok&&dl!==0?
        (dl>0?' &middot; chemical higher':' &middot; HPF higher'):''}
        <span class="gn">${c.length}v${h.length}</span></span>
    </button>`});
  }
  if(gOrder==='effect')cards.sort((a,b)=>b.mag-a.mag);
  host.innerHTML=cards.map(c=>c.html).join('')||
    '<p class="muted">No headline metric has values in this slice.</p>';

  // the headline: the largest separation in this slice, said in words
  const top=cards.slice().sort((a,b)=>b.mag-a.mag)[0];
  const lab=top?(GLANCE.find(g=>g[0]===top.met)||[])[1]:'';
  $('headline').innerHTML=(!top||top.mag<0||thin)
    ? 'Not enough crops on both sides here to compare.'
    : (top.mag<0.147
        ? `Nothing separates strongly in this slice &mdash; the largest, <b>${lab}</b>, is negligible.`
        : `The largest separation here is <b>${lab}</b>.`);
}

/* The region vignettes are 4.4:1 strips of six panels each. Six of them stacked
   is a page of texture nobody reads; one at full width, named, is a figure. The
   picker follows the Region filter when one is set, so choosing a region above
   brings its vignette with it. */
let vigPick=null;
function syncPanels(){
  const s=sel();
  const reg=(s.reg&&s.reg!=='All regions')?s.reg:null;
  const figs=[...document.querySelectorAll('.fig[data-region]')];
  const sec=document.getElementById('vigsection');
  if(!figs.length){ if(sec)sec.hidden=true; return; }
  if(sec)sec.hidden=false;
  const names=figs.map(f=>f.dataset.region);
  // the region filter wins; otherwise whatever was last picked, else the first
  let want=(reg&&names.includes(reg))?reg
         :(vigPick&&names.includes(vigPick))?vigPick:names[0];
  vigPick=want;
  figs.forEach(f=>{f.hidden=f.dataset.region!==want});
  const pick=document.getElementById('regpick');
  if(pick)pick.innerHTML=names.map(n=>
    `<button type="button" class="btn${n===want?' on':''}" data-vig="${n}">${n}</button>`).join('');
  const note=document.getElementById('vignote');
  if(note)note.innerHTML=(reg&&names.includes(reg))
    ? `Following the <b>${reg}</b> region filter above.`
    : `Six regions have crops in both preparations. Showing <b>${want}</b>.`;
}

function draw(){
  const s=sel();
  sliceSum();
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
  /* A log axis needs positive values, and several of these metrics are
     fractions that legitimately reach zero; offering log where it cannot be
     drawn would be a lie, so the control says so and falls back. */
  const canLog=dmin>0;
  const logOn=s.scale==='log'&&canLog;
  $('scale').title=canLog?'':'This metric reaches zero, so a log axis is not available';
  $('scale').classList.toggle('muted',!canLog);
  let lo=dmin,hi=dmax;
  if(lo===hi){const e=Math.abs(lo||1)*.05;lo-=e;hi+=e;}
  if(logOn){ lo=dmin/1.15; hi=dmax*1.15; }
  else{
    const pad=(hi-lo)*.06; lo-=pad; hi+=pad;
    if(dmin>=0&&lo<0)lo=0;
    if(dmax<=0&&hi>0)hi=0;
  }
  // an explicit range wins over anything computed
  const ulo=parseFloat($('axlo').value), uhi=parseFloat($('axhi').value);
  if(Number.isFinite(ulo))lo=ulo;
  if(Number.isFinite(uhi))hi=uhi;
  if(logOn&&lo<=0)lo=dmin/1.15;
  const T=v=>logOn?Math.log10(Math.max(v,1e-12)):v;
  const M=11, X=v=>M+((T(v)-T(lo))/((T(hi)-T(lo))||1))*(W-2*M), H=36, R=5.5;

  let html='';
  const ticks=logOn
    ? [lo,Math.sqrt(lo*hi),hi]
    : [lo,(lo+hi)/2,hi];
  html+=`<div class="row" style="border-bottom:1px solid var(--rule);padding-bottom:6px">
    <div></div><div><svg width="${W}" height="15" viewBox="0 0 ${W} 15" class="axis">
    ${ticks.map((t,i)=>{const a=i===0?'start':(i===2?'end':'middle');
      return `<text x="${X(t).toFixed(1)}" y="11" text-anchor="${a}">${fmt(t)}</text>`}).join('')}
    </svg><div style="font-size:11px;color:var(--ink-3);text-align:center;margin-top:-2px">
    ${(unit($('met').value)||'')+(logOn?' &middot; log scale':'')}</div></div>
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
  clipTable(n);
}

/* Fifty-five rows is a wall in the middle of a page people are scrolling
   through for something else. The table opens at a readable height with the
   count on the button, so nothing is hidden -- it is just not in the way. */
let tblOpen=false;
function clipTable(n){
  const box=document.getElementById('tblbox'),
        btn=document.getElementById('tblmore');
  if(!box||!btn)return;
  const many=n>14;
  box.classList.toggle('clip',many&&!tblOpen);
  btn.hidden=!many;
  btn.textContent=tblOpen?'Show fewer':`Show all ${n} rows`;
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
['met','grp','vox','reg','scale'].forEach(i=>$(i).addEventListener('change',
  ()=>{draw();drawGlance();syncPanels()}));
['axlo','axhi'].forEach(i=>$(i).addEventListener('input',draw));
$('axauto').addEventListener('click',()=>{$('axlo').value='';$('axhi').value='';draw()});
// a new metric has a new range: an old one held over would be meaningless
$('met').addEventListener('change',()=>{$('axlo').value='';$('axhi').value=''});

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
  const ob=e.target.closest('#gorder [data-order]');
  if(ob){ gOrder=ob.dataset.order;
    document.querySelectorAll('#gorder .seg').forEach(b=>
      b.classList.toggle('on',b===ob));
    drawGlance(); return; }
  const vb=e.target.closest('#regpick [data-vig]');
  if(vb){ vigPick=vb.dataset.vig;
    // a picked vignette should not fight a region filter that says otherwise
    if($('reg').value!=='All regions'&&$('reg').value!==vigPick){
      $('reg').value='All regions'; draw(); drawGlance(); }
    syncPanels(); return; }
  const sb=e.target.closest('#slicetoggle');
  if(sb){ barTouched=true;
    setBar($('filterbar').classList.contains('shut')); return; }
  if(e.target.id==='tblmore'){ tblOpen=!tblOpen; drawTable();
    if(!tblOpen)document.getElementById('tblbox')
      .scrollIntoView({behavior:'smooth',block:'start'}); return; }
});

/* A sticky element's offsetTop is its stuck position, not its resting one, so
   asking the bar where it lives always returns "right here". A sentinel above
   it does not move, and leaving the viewport is exactly the moment the bar
   becomes a floating strip rather than part of the page. */
(function(){
  const sn=$('fbtop'), fb=$('filterbar');
  if(!sn||!fb||!('IntersectionObserver' in window))return;
  new IntersectionObserver(([e])=>{
    const stuck=!e.isIntersecting;
    fb.classList.toggle('stuck',stuck);
    if(stuck&&!barTouched&&!fb.classList.contains('shut'))setBar(false);
  },{rootMargin:'-56px 0px 0px 0px',threshold:0}).observe(sn);
})();
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
  draw(); drawGlance(); syncFamPanels(); syncPanels(); sliceSum();
  const keep=()=>{const s=sel();const u=new URLSearchParams(
      {run:s.run,fam:s.fam,metric:s.met,grp:s.grp});
    history.replaceState(null,'',location.pathname+'?'+u.toString())};
  ['run','fam','met','grp'].forEach(i=>$(i).addEventListener('change',keep));
  keep();
}).catch(e=>{$('plot').innerHTML='<p class="muted">Could not load the data &mdash; '+e+'</p>'});
</script>"""


def main():
    html = sh.head("Analysis — ECS preservation", 0,
                   '<script type="module" src="assets/model-viewer.min.js"></script>'
                   + EXTRA + FIG_STYLE)
    html += sh.nav("explore.html", 0)
    html += sh.pagehead_model("Analysis",
        "Every per-crop measurement the pipeline has produced, live at the top and as standing "
        "panels below. Each dot is one crop, chemical above the line and HPF below, with groups "
        'sharing one scale so they can be read against each other. '
        '<a href="reference.html#reading">How to read this.</a>')
    family_html, _ = family_block()
    standing, n_panels = sections_html()
    html += f"""<main class="after-head">

<div id="fbtop" aria-hidden="true"></div>
<div class="filterbar" id="filterbar">
  <div class="fbline">
    <button class="btn slicebtn" id="slicetoggle" type="button" aria-expanded="true">
      <span id="slicesum">Loading&hellip;</span><i>&#9662;</i></button>
    <nav class="onpage" aria-label="On this page">
      <a href="#glancesec">Glance</a>
      <a href="#live">One metric</a>
      <a href="#table">Table</a>
      <a href="#matrix">All metrics</a>
      <a href="#vignettes">Regions</a>
      <a href="#renders">Geometry</a>
    </nav>
  </div>
  <div class="controls" id="controls">
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
</div>

<section class="lead" id="glancesec">
  <div class="leadtop">
    <h2 class="sec-first">At a glance</h2>
    <div class="leadctl">
      <span class="seglabel">Order</span>
      <span class="seggroup" id="gorder">
        <button type="button" class="btn seg on" data-order="effect">Biggest difference</button>
        <button type="button" class="btn seg" data-order="listed">As listed</button>
      </span>
    </div>
  </div>
  <p class="headline" id="headline"></p>
  <p class="note" id="glancecount"></p>
  <p class="secintro">One card per headline metric: each dot a crop,
  <span class="tag chem">chemical</span> above and <span class="tag hpf">rapid HPF</span> below,
  medians ticked. The bar is Cliff's &delta;, drawn from the centre &mdash; longer means the two
  preparations separate further. Click a card to open that metric in full.
  <a href="reference.html#delta">What &delta; means.</a></p>
  <div class="glance" id="glance"></div>
</section>

<h2 id="live">One metric at a time</h2>
<p class="secintro">Pick any of the 60-odd measurements above. Each dot is one crop &mdash;
chemical on the upper line, rapid HPF on the lower &mdash; and the thick tick is that arm's
median. Groups share one scale so they can be read against each other.</p>
<div id="about"></div>
<div class="readout" id="readout"></div>

<div class="legend">
  <span class="item"><i class="sw" style="background:var(--chem)"></i>Chemical, one crop</span>
  <span class="item"><i class="sw" style="background:var(--hpf)"></i>Rapid HPF, one crop</span>
  <span class="item"><i class="sw line" style="background:var(--ink-3)"></i>group median</span>
  <span class="item"><b class="flag">n</b>&nbsp;arm with one crop or none</span>
</div>

<div class="plotbar">
  <span class="ctl inline"><label for="scale">Scale</label><select id="scale">
    <option value="linear">Linear</option><option value="log">Logarithmic</option>
    </select></span>
  <span class="ctl inline"><label for="axlo">Axis range</label>
    <span class="rng"><input type="number" id="axlo" step="any" placeholder="auto">
    <span class="to">to</span>
    <input type="number" id="axhi" step="any" placeholder="auto">
    <button class="btn" id="axauto" type="button">Auto</button></span></span>
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

<h2 id="table">The same crops, as numbers</h2>
<p class="secintro">Every crop behind the plot above, for the metric you have selected. Click a
heading to sort; the &#9662; on a column filters it; a crop name opens that crop in the 3D
viewer. <span id="tblcount"></span></p>
<div class="tblbox" id="tblbox">
  <div class="card scroll"><table id="tbl"><thead></thead><tbody></tbody></table></div>
</div>
<button class="btn tblmore" id="tblmore" type="button" hidden>Show all rows</button>
<p class="note"><a href="data/all_metrics_long.csv">Download every metric for every crop</a>
&mdash; one CSV, the same file this page reads.</p>
"""
    html += standing
    html += """
<section class="whereto">
  <h2>Where to next</h2>
  <ul class="jump">
    <li><a href="crops.html"><span class="t">The 55 crops</span>
      <span class="d">Every crop with its tissue, region and preparation &mdash; and a viewer
      that turns the extracellular space and the membrane in 3D.</span></a></li>
    <li><a href="reference.html"><span class="t">How this was measured</span>
      <span class="d">What each metric is, where the resolution floors sit, and why the
      comparison is region-matched.</span></a></li>
    <li><a href="data/all_metrics_long.csv"><span class="t">The data</span>
      <span class="d">One CSV, every metric for every crop, at both resolutions.</span></a></li>
  </ul>
</section>
"""
    html += sh.footer(0) + "</main><div id=\"tip\"></div>" + JS + "</body></html>"
    (ROOT / "docs" / "explore.html").write_text(html)
    print("built docs/explore.html")


if __name__ == "__main__":
    main()
