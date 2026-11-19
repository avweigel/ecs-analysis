#!/usr/bin/env python3
"""Build docs/ng-lines.html: paste a Neuroglancer link, get its line
annotations as a spreadsheet.

It is scripts/ng_lines_to_csv.py in the browser. Both read the same fields
and write the same columns, so the CSV from either is the same file. Nothing
leaves the page: the link is decoded in JavaScript and the CSV is built
there.

    python3 scripts/build_ng_lines_page.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_shell as sh

ROOT = Path(__file__).resolve().parent.parent

EXTRA = """<style>
 .exporter label{display:block;font-weight:600;margin:0 0 var(--s2)}
 .exporter textarea{width:100%;box-sizing:border-box;min-height:7.5em;resize:vertical;
   background:var(--raise);color:var(--ink);border:1px solid var(--rule-strong);
   border-radius:6px;padding:9px 11px;font:12.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
   word-break:break-all}
 .exporter textarea:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
 .exporter .actions{display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap;
   margin-top:var(--s3)}
 .btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
 .btn.primary:hover{color:#fff;filter:brightness(1.08)}
 .btn:disabled,.btn:disabled:hover{opacity:.45;cursor:default;filter:none;
   border-color:var(--rule-strong)}
 #status{font-size:var(--t4);color:var(--ink-2)}
 #status.err{color:var(--flag)}
 #preview{margin-top:var(--s5)}
 #preview[hidden]{display:none}
</style>"""

BODY = """<main class="after-head">

<div class="card exporter">
  <label for="ngin">Neuroglancer link</label>
  <textarea id="ngin" spellcheck="false" autocomplete="off"
    placeholder="https://neuroglancer-demo.appspot.com/#!%7B%22dimensions%22…   or the JSON from Neuroglancer’s { } button"></textarea>
  <div class="actions">
    <button class="btn primary" id="dl" type="button" disabled>Download CSV</button>
    <button class="btn" id="copy" type="button" disabled>Copy for a spreadsheet</button>
    <span id="status" role="status" aria-live="polite"></span>
  </div>
</div>

<div id="preview" hidden>
  <div class="scroll"><table id="out"><thead></thead><tbody></tbody></table></div>
</div>

<p class="note">The CSV has, for each line: where it starts and ends (z, y, x in
nanometres), its length in nanometres, the segments Neuroglancer linked to it (several
are joined with <code>;</code>), the annotation id and layer, and the full link. The
column names are the ones
<a href="https://github.com/davidackerman/annotation-processing-utils">annotation-processing-utils</a>
reads. <em>Copy for a spreadsheet</em> puts the same table on the clipboard, ready to
paste into Google Sheets or Excel.</p>
<p class="note">Only annotations stored in the link itself (local annotation layers) are
read; points and other shapes are skipped and counted. The same export runs from the
command line with <code>scripts/ng_lines_to_csv.py</code> in the
<a href="https://github.com/avweigel/ecs-analysis">repository</a>.</p>
"""

# Kept line for line with extract() in scripts/ng_lines_to_csv.py: same fields,
# same column order, same number formatting, same CSV quoting and line ends.
JS = r"""<script>
(function () {
  const AXES = ['z', 'y', 'x'];
  const UNIT_TO_NM = { m: 1e9, mm: 1e6, um: 1e3, 'µm': 1e3, nm: 1 };
  class InputError extends Error {}

  // Python's unquote: decode %XX as UTF-8 and leave anything malformed alone,
  // where decodeURIComponent would throw on the whole string
  function unquote(s) {
    return s.replace(/(%[0-9A-Fa-f]{2})+/g, m => {
      try { return decodeURIComponent(m); } catch (e) { return m; }
    });
  }

  function loadState(text) {
    text = text.trim();
    if (text.startsWith('{')) return { state: parseJSON(text), link: '' };
    const i = text.indexOf('#!');
    if (i < 0) throw new InputError("No '#!' state in that link. Copy the full address from Neuroglancer.");
    const frag = unquote(text.slice(i + 2));
    if (/^(https?|gs|s3):\/\//.test(frag))
      throw new InputError('This link points at a saved state (' + frag.slice(0, 80) +
        ') instead of carrying it. Open it in Neuroglancer and copy the JSON with the { } button.');
    return { state: parseJSON(frag), link: text };
  }
  function parseJSON(t) {
    try { return JSON.parse(t); }
    catch (e) { throw new InputError('The link’s state is not valid JSON. Was the whole address copied?'); }
  }

  function nmPerUnit(dims) {
    return Object.entries(dims).map(([name, [scale, unit]]) => {
      if (!(unit in UNIT_TO_NM)) throw new InputError(`Unsupported unit '${unit}' on axis '${name}'`);
      return [name, Number(scale) * UNIT_TO_NM[unit]];
    });
  }

  // Python's round(v, 3), then str(): the nearest thousandth, with exact ties
  // going to the even digit; whole numbers keep their ".0"
  function round3(v) {
    let r;
    const k = v * 16;              // an exact tie at 3 decimals is an odd multiple of 1/16
    if (Number.isInteger(k) && Math.abs(k) % 2 === 1) {
      const lo = Math.floor(v * 1000);   // exact here
      r = (lo % 2 === 0 ? lo : lo + 1) / 1000;
    } else {
      r = Number(v.toFixed(3));
      if (v < 0 && r === 0) r = -0;
    }
    return r;
  }
  function pyFloat(r) {
    if (Object.is(r, -0)) return '-0.0';
    const s = String(r);
    return /^-?\d+$/.test(s) ? s + '.0' : s;
  }

  function extract(state, link) {
    const rows = []; let skipped = 0;
    const globalDims = state.dimensions;
    for (const layer of state.layers || []) {
      if (layer.type !== 'annotation' || !('annotations' in layer)) continue;
      const src = layer.source;
      let dims = globalDims;
      if (src && typeof src === 'object' && !Array.isArray(src))
        dims = ((src.transform || {}).outputDimensions) || dims;
      if (!dims) throw new InputError(`Layer '${layer.name}': no coordinate space found`);
      const axes = nmPerUnit(dims);
      const missing = AXES.filter(a => !axes.some(([n]) => n === a));
      if (missing.length) throw new InputError(`Layer '${layer.name}': missing axes ${JSON.stringify(missing.sort())}`);
      for (const ann of layer.annotations) {
        if (ann.type !== 'line') { skipped++; continue; }
        const pt = p => Object.fromEntries(axes.map(([ax, s], i) => [ax, Number(p[i]) * s]));
        const a = pt(ann.pointA), b = pt(ann.pointB);
        const row = { layer: layer.name || '', id: ann.id || '' };
        for (const ax of AXES) row[`start ${ax} (nm)`] = round3(a[ax]);
        for (const ax of AXES) row[`end ${ax} (nm)`] = round3(b[ax]);
        row['length (nm)'] = round3(Math.hypot(...AXES.map(k => b[k] - a[k])));
        const segs = [];
        // current Neuroglancer writes one list per linked layer; older links a flat list
        for (const g of ann.segments || []) segs.push(...(typeof g === 'string' ? [g] : g));
        row.segments = segs.map(String).join(';');
        row['neuroglancer url'] = link;
        rows.push(row);
      }
    }
    return { rows, skipped };
  }

  const cell = v => typeof v === 'number' ? pyFloat(v) : String(v);
  // Python's csv module: quote only fields holding a comma, quote or line
  // break, double any quote inside, end every row with \r\n
  function toCSV(rows) {
    const cols = Object.keys(rows[0]);
    const q = s => /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    return [cols, ...rows.map(r => cols.map(c => cell(r[c])))]
      .map(line => line.map(q).join(',')).join('\r\n') + '\r\n';
  }
  function toTSV(rows) {
    const cols = Object.keys(rows[0]);
    const t = s => s.replace(/[\t\r\n]+/g, ' ');
    return [cols, ...rows.map(r => cols.map(c => cell(r[c])))]
      .map(line => line.map(t).join('\t')).join('\n') + '\n';
  }
  // ng_lines_<dataset>[_<crop>].csv, from the layer sources and linked layer names
  function fileName(state) {
    const blob = JSON.stringify(state.layers || []);
    const ds = (blob.match(/\/(jrc_[A-Za-z0-9_-]+?)(?:\.zarr|\.n5|\/)/) || [])[1];
    const crops = [...new Set(blob.match(/crop\d+/g) || [])];
    return ['ng_lines', ds, crops.length === 1 ? crops[0] : null].filter(Boolean).join('_') + '.csv';
  }

  window.NGLines = { loadState, extract, toCSV, toTSV, fileName, InputError };

  const $ = id => document.getElementById(id);
  const input = $('ngin'), status = $('status'), dl = $('dl'), copy = $('copy');
  let current = null;

  function say(msg, err) { status.textContent = msg; status.className = err ? 'err' : ''; }

  function render(rows) {
    const multi = new Set(rows.map(r => r.layer)).size > 1;
    const head = ['#', ...(multi ? ['layer'] : []), 'start z', 'start y', 'start x',
                  'end z', 'end y', 'end x', 'length', 'segments'];
    const units = ['', ...(multi ? [''] : []), 'nm', 'nm', 'nm', 'nm', 'nm', 'nm', 'nm', ''];
    const num = h => /start|end|length|#/.test(h);
    $('out').tHead.innerHTML = '<tr>' + head.map((h, i) =>
      `<th class="${num(h) ? 'num' : ''}">${h}${units[i] ? `<span class="u">${units[i]}</span>` : ''}</th>`).join('') + '</tr>';
    const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
    $('out').tBodies[0].innerHTML = rows.map((r, i) => '<tr>' +
      [i + 1, ...(multi ? [r.layer] : []),
       ...['start z', 'start y', 'start x', 'end z', 'end y', 'end x', 'length']
         .map(k => pyFloat(r[k + ' (nm)'])), r.segments]
      .map((v, j) => `<td class="${num(head[j]) ? 'num' : ''}">${esc(v)}</td>`).join('') + '</tr>').join('');
    $('preview').hidden = false;
  }

  function run() {
    current = null; dl.disabled = copy.disabled = true; $('preview').hidden = true;
    const text = input.value;
    if (!text.trim()) { say(''); return; }
    try {
      const { state, link } = loadState(text);
      const { rows, skipped } = extract(state, link);
      if (!rows.length) throw new InputError('No line annotations found in local annotation layers.');
      current = { rows, name: fileName(state) };
      const layers = [...new Set(rows.map(r => r.layer))];
      say(`${rows.length} line${rows.length === 1 ? '' : 's'} from ${layers.length === 1 ? 'layer “' + layers[0] + '”' : layers.length + ' layers'}` +
          (skipped ? ` · ${skipped} other annotation${skipped === 1 ? '' : 's'} skipped` : ''));
      dl.disabled = copy.disabled = false;
      render(rows);
    } catch (e) {
      say(e instanceof InputError ? e.message : 'Could not read that link: ' + e.message, true);
    }
  }

  input.addEventListener('input', run);
  dl.addEventListener('click', () => {
    if (!current) return;
    const url = URL.createObjectURL(new Blob([toCSV(current.rows)], { type: 'text/csv' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: current.name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  copy.addEventListener('click', async () => {
    if (!current) return;
    try {
      await navigator.clipboard.writeText(toTSV(current.rows));
      const was = copy.textContent; copy.textContent = 'Copied';
      setTimeout(() => { copy.textContent = was; }, 1400);
    } catch (e) { say('The browser blocked the clipboard; use Download CSV instead.', true); }
  });
  run();   // a link restored by the browser on reload
})();
</script>"""


def main():
    html = sh.head("Line export — ECS preservation", 0, EXTRA)
    html += sh.nav("ng-lines.html", 0)
    html += sh.pagehead("Export line annotations",
        "Paste a Neuroglancer link and get its line annotations as a spreadsheet: where "
        "each line starts and ends, how long it is, and which segments it touches. "
        "Everything happens in this page; the link is not sent anywhere.")
    html += BODY + JS + sh.tail(0)
    out = ROOT / "docs" / "ng-lines.html"
    out.write_text(html)
    print(f"built {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
