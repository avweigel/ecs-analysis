#!/usr/bin/env python3
"""Build docs/explore.html — the metric explorer, on the shared site shell.
Reads data/all_metrics_long.csv and data/metrics.json at runtime."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

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

function draw(){
  const s=sel();
  let d=ROWS.filter(r=>r.run===s.run&&r.metric_family===s.fam&&r.metric===s.met
        &&Number.isFinite(r.value));
  if(s.tis&&s.tis!=='All tissues')d=d.filter(r=>r.tissue===s.tis);
  if(s.vox&&s.vox!=='All')d=d.filter(r=>String(r.analysis_voxel_nm)===s.vox);
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

  const thd=$('tbl').querySelector('thead'), tb=$('tbl').querySelector('tbody');
  thd.innerHTML='<tr><th>Crop</th><th>Tissue</th><th>Region</th><th class="wrap">Anatomy</th>'
    +'<th>Prep</th><th class="num">Voxel nm</th><th class="num">'+label(s.met)
    +(unit(s.met)?' <span style="font-weight:400;text-transform:none">('+unit(s.met)+')</span>':'')
    +'</th></tr>';
  tb.innerHTML=d.slice().sort((a,b)=>a.crop.localeCompare(b.crop)).map(r=>
    `<tr><td><a href="crops.html?crop=${r.crop}" title="Open ${r.crop} in the viewer">${r.crop}</a></td><td>${r.tissue}</td><td>${r.region_group||''}</td>
     <td class="wrap">${r.anatomy||''}</td>
     <td><span class="tag ${PREP[r.prep]}">${r.prep}</span></td>
     <td class="num">${r.analysis_voxel_nm||''}</td><td class="num">${fmt(r.value)}</td></tr>`).join('');
}

document.addEventListener('mouseover',e=>{
  const c=e.target.closest('circle[data-c]'); if(!c)return;
  ECS.tip(`<b>${c.dataset.c}</b><div>${c.dataset.p}</div>`
    +`<div>${label($('met').value)}: ${fmt(parseFloat(c.dataset.v))} ${unit($('met').value)}</div>`
    +(c.dataset.a?`<div>${c.dataset.a}</div>`:'')
    +(c.dataset.x?`<div class="muted">${c.dataset.x} nm voxel</div>`:''), e);
});
document.addEventListener('mouseout',e=>{if(e.target.closest('circle[data-c]'))ECS.tip(null)});
['run','fam'].forEach(i=>$(i).addEventListener('change',()=>{refreshOptions();draw()}));
['met','grp','tis','vox'].forEach(i=>$(i).addEventListener('change',draw));
let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(draw,150)});
document.addEventListener('ecs:theme',()=>draw());

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
  draw();
  const keep=()=>{const s=sel();const u=new URLSearchParams(
      {run:s.run,fam:s.fam,metric:s.met,grp:s.grp});
    history.replaceState(null,'',location.pathname+'?'+u.toString())};
  ['run','fam','met','grp'].forEach(i=>$(i).addEventListener('change',keep));
  keep();
}).catch(e=>{$('plot').innerHTML='<p class="muted">Could not load the data &mdash; '+e+'</p>'});
</script>"""


def main():
    html = sh.head("Metric explorer — ECS preservation", 0, EXTRA)
    html += sh.nav("explore.html", 0)
    html += sh.pagehead_art("Metric explorer",
        "Every per-crop measurement the pipeline has produced. Each dot is one crop, chemical "
        "above the line and HPF below, with groups sharing one scale so they can be read against "
        'each other. <a href="reference.html#reading">How to read this.</a>')
    html += f"""<main class="after-head">

<div class="controls">
  <div class="ctl"><label for="run">Run</label><select id="run"></select></div>
  <div class="ctl"><label for="fam">Metric family</label><select id="fam"></select></div>
  <div class="ctl"><label for="met">Metric</label><select id="met" style="min-width:280px"></select></div>
  <div class="ctl"><label for="grp">Group by</label><select id="grp">
    <option value="region_group">Region</option><option value="tissue">Tissue</option>
    <option value="anatomy">Anatomy</option></select></div>
  <div class="ctl"><label for="tis">Tissue</label><select id="tis"></select></div>
  <div class="ctl"><label for="vox">Analysis voxel</label><select id="vox"></select></div>
</div>

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

<h2>Table view</h2>
<div class="card scroll"><table id="tbl"><thead></thead><tbody></tbody></table></div>
"""
    html += sh.footer(0) + "</main><div id=\"tip\"></div>" + JS + "</body></html>"
    (ROOT / "docs" / "explore.html").write_text(html)
    print("built docs/explore.html")


if __name__ == "__main__":
    main()
