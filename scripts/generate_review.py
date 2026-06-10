#!/usr/bin/env python3
#python scripts/generate_review.py data/icml/post/hallucinator-results.json --output review-post.html
#python scripts/generate_review.py data/icml/pre/hallucinator-results.json data/icml/post/hallucinator-results.json --output review.html

import json
import argparse
import sys
from pathlib import Path


def load_refs(json_path: Path) -> list:
    with open(json_path, encoding="utf-8") as f:
        papers = json.load(f)

    refs = []
    for paper in papers:
        filename = paper["filename"]
        for ref in paper["references"]:
            status = ref.get("effective_status") or ref.get("status", "")
            if status == "skipped":
                continue
            entry: dict = {
                "f": filename,
                "i": ref["index"],
                "n": ref.get("original_number", ref["index"] + 1),
                "t": ref.get("title", ""),
                "s": status,
            }
            raw = ref.get("raw_citation", "")
            if raw:
                entry["r"] = raw
            ref_authors = ref.get("ref_authors", [])
            if ref_authors:
                entry["a"] = ref_authors
            found_authors = ref.get("found_authors", [])
            if found_authors:
                entry["fa"] = found_authors
            url = ref.get("paper_url")
            if url:
                entry["u"] = url
            source = ref.get("source")
            if source:
                entry["src"] = source
            refs.append(entry)
    return refs


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{
  --bg: #1a1a2e;
  --surface: #16213e;
  --card: #0f3460;
  --text: #e0e0e0;
  --dim: #888;
  --green: #4ecca3;
  --red: #e74c3c;
  --yellow: #f39c12;
  --blue: #3498db;
  --border: #2a2a4a;
  --real-color: #4ecca3;
  --hall-color: #e74c3c;
  --unc-color: #888;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  padding-top: 130px;
}}
/* ── Top bar ─────────────────────────────── */
#topbar {{
  position: fixed;
  top: 0; left: 0; right: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0.6rem 1.5rem;
  z-index: 100;
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: center;
}}
#topbar h1 {{
  color: var(--green);
  font-size: 1.1rem;
  margin-right: 0.5rem;
  white-space: nowrap;
}}
.filter-btn {{
  padding: 0.3rem 0.8rem;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  cursor: pointer;
  font-size: 0.85rem;
  white-space: nowrap;
}}
.filter-btn.active {{ border-color: var(--green); color: var(--green); }}
#progress-wrap {{
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.8rem;
  white-space: nowrap;
  font-size: 0.85rem;
}}
#progress-text {{ color: var(--dim); }}
#progress-bar-outer {{
  width: 120px;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}}
#progress-bar {{ height: 100%; background: var(--green); width: 0%; transition: width 0.2s; }}
#export-btn {{
  padding: 0.3rem 0.9rem;
  border-radius: 20px;
  border: none;
  background: var(--green);
  color: #000;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
}}
#export-btn:hover {{ opacity: 0.85; }}
#jump-btn {{
  padding: 0.3rem 0.9rem;
  border-radius: 20px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  cursor: pointer;
  font-size: 0.85rem;
}}
/* ── Confusion matrix bar ────────────────── */
#matrix-bar {{
  position: fixed;
  top: 58px; left: 0; right: 0;
  background: #11192b;
  border-bottom: 1px solid var(--border);
  padding: 0.35rem 1.5rem;
  z-index: 99;
  display: flex;
  gap: 1.5rem;
  font-size: 0.8rem;
  align-items: center;
  flex-wrap: wrap;
}}
.mx-cell {{ display: flex; align-items: center; gap: 0.35rem; }}
.mx-label {{ color: var(--dim); }}
.mx-tp {{ color: var(--green); font-weight: 700; }}
.mx-fp {{ color: var(--yellow); font-weight: 700; }}
.mx-tn {{ color: var(--blue); font-weight: 700; }}
.mx-fn {{ color: var(--red); font-weight: 700; }}
.mx-div {{ color: var(--border); }}
/* ── Main content ────────────────────────── */
#main {{ padding: 1rem 1.5rem 3rem; }}
.paper-block {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 0.75rem;
}}
.paper-header {{
  padding: 0.6rem 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  user-select: none;
}}
.paper-header:hover {{ background: var(--card); border-radius: 8px; }}
.paper-arrow {{ color: var(--dim); transition: transform 0.15s; font-size: 0.75rem; }}
.paper-block.open .paper-arrow {{ transform: rotate(90deg); }}
.paper-name {{ font-weight: 600; font-size: 0.95rem; }}
.paper-meta {{ color: var(--dim); font-size: 0.8rem; margin-left: auto; white-space: nowrap; }}
.paper-refs {{ display: none; padding: 0 0.75rem 0.75rem; }}
.paper-block.open .paper-refs {{ display: block; }}
/* ── Ref card ────────────────────────────── */
.ref-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  transition: border-color 0.15s;
}}
.ref-card.annotated-real    {{ border-left: 3px solid var(--real-color); }}
.ref-card.annotated-hallucinated {{ border-left: 3px solid var(--hall-color); }}
.ref-card.annotated-uncertain {{ border-left: 3px solid var(--unc-color); }}
.ref-header {{ display: flex; align-items: flex-start; gap: 0.6rem; margin-bottom: 0.4rem; }}
.status-badge {{
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  white-space: nowrap;
  flex-shrink: 0;
}}
.badge-not_found {{ background: #5c1010; color: #ff9f9f; }}
.badge-mismatch  {{ background: #5c3d00; color: #ffd080; }}
.badge-verified  {{ background: #0b3d25; color: #4ecca3; }}
.ref-num {{ color: var(--dim); font-size: 0.8rem; flex-shrink: 0; padding-top: 0.1rem; }}
.ref-title {{ font-size: 0.95rem; font-weight: 600; }}
.ref-title a {{ color: var(--text); text-decoration: none; }}
.ref-title a:hover {{ color: var(--green); text-decoration: underline; }}
.ref-authors {{ font-size: 0.8rem; color: var(--dim); margin: 0.2rem 0 0.4rem; }}
.ref-authors .cited {{ color: var(--dim); }}
.ref-authors .found {{ color: var(--blue); }}
.ref-authors .mismatch-arrow {{ color: var(--border); margin: 0 0.3rem; }}
.raw-toggle {{
  font-size: 0.72rem;
  color: var(--dim);
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  text-decoration: underline;
  margin-bottom: 0.4rem;
  display: block;
}}
.raw-citation {{
  font-size: 0.75rem;
  color: var(--dim);
  background: var(--surface);
  border-radius: 4px;
  padding: 0.4rem 0.6rem;
  margin-bottom: 0.4rem;
  display: none;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
}}
.ref-footer {{ display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.4rem; }}
.ref-link {{
  font-size: 0.75rem;
  color: var(--blue);
  text-decoration: none;
}}
.ref-link:hover {{ text-decoration: underline; }}
/* ── Annotation buttons ──────────────────── */
.ann-btns {{ display: flex; gap: 0.4rem; margin-left: auto; }}
.ann-btn {{
  padding: 0.2rem 0.65rem;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 500;
  transition: all 0.1s;
}}
.ann-btn:hover {{ opacity: 0.8; }}
.ann-btn.selected-real         {{ background: var(--real-color); color: #000; border-color: var(--real-color); }}
.ann-btn.selected-hallucinated {{ background: var(--hall-color); color: #fff; border-color: var(--hall-color); }}
.ann-btn.selected-uncertain    {{ background: #555; color: #fff; border-color: #555; }}
/* ── Empty state ─────────────────────────── */
#empty-msg {{ color: var(--dim); text-align: center; padding: 3rem; font-size: 0.95rem; }}
/* ── Shortcut hint ───────────────────────── */
#shortcut-hint {{
  position: fixed;
  bottom: 1rem; right: 1.5rem;
  font-size: 0.72rem;
  color: var(--dim);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.7rem;
}}
</style>
</head>
<body>

<div id="topbar">
  <h1>Hallucinator Review</h1>
  <button class="filter-btn active" data-filter="all">All</button>
  <button class="filter-btn" data-filter="not_found">Not Found</button>
  <button class="filter-btn" data-filter="mismatch">Mismatch</button>
  <button class="filter-btn" data-filter="verified">Verified</button>
  <div id="progress-wrap">
    <span id="progress-text">0 / 0 reviewed</span>
    <div id="progress-bar-outer"><div id="progress-bar"></div></div>
    <button id="jump-btn" title="Jump to next unannotated">Next unannotated</button>
    <button id="export-btn">Export CSV</button>
  </div>
</div>

<div id="matrix-bar">
  <span style="color:var(--dim);font-weight:600;">Confusion matrix:</span>
  <span class="mx-cell"><span class="mx-label">TP</span><span class="mx-tp" id="mx-tp">0</span></span>
  <span class="mx-div">|</span>
  <span class="mx-cell"><span class="mx-label">FP</span><span class="mx-fp" id="mx-fp">0</span></span>
  <span class="mx-div">|</span>
  <span class="mx-cell"><span class="mx-label">TN</span><span class="mx-tn" id="mx-tn">0</span></span>
  <span class="mx-div">|</span>
  <span class="mx-cell"><span class="mx-label">FN</span><span class="mx-fn" id="mx-fn">0</span></span>
  <span class="mx-div">|</span>
  <span class="mx-cell"><span class="mx-label">Precision</span><span id="mx-prec" style="font-weight:700;">—</span></span>
  <span class="mx-div">|</span>
  <span class="mx-cell"><span class="mx-label">Recall</span><span id="mx-rec" style="font-weight:700;">—</span></span>
  <span class="mx-div">|</span>
  <span class="mx-cell"><span class="mx-label">F1</span><span id="mx-f1" style="font-weight:700;">—</span></span>
  <span style="color:var(--dim);font-size:0.75rem;margin-left:0.5rem;">(predicted positive = not_found or mismatch)</span>
</div>

<div id="main"></div>

<div id="shortcut-hint">
  Shortcuts (on focused card): <strong>R</strong> Real &nbsp; <strong>H</strong> Hallucinated &nbsp; <strong>U</strong> Uncertain &nbsp; <strong>↑↓</strong> Navigate
</div>

<script>
// Raw data with short field names (f=filename, i=index, n=ref_num, t=title,
// s=status, r=raw_citation, a=ref_authors, fa=found_authors, u=paper_url, src=source)
const DATA = {data_json};
const STORAGE_KEY = 'hallucinator_review_annotations';

// ── State ─────────────────────────────────────────────────────────────────
let annotations = {{}};
try {{ annotations = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}'); }} catch(e) {{}}

let currentFilter = 'all';
let focusedGlobalIdx = -1;

// ── Field accessors (map short keys to readable names) ────────────────────
const F = {{
  filename:     r => r.f,
  index:        r => r.i,
  ref_num:      r => r.n,
  title:        r => r.t || '',
  status:       r => r.s,
  raw_citation: r => r.r || '',
  ref_authors:  r => r.a || [],
  found_authors:r => r.fa || [],
  paper_url:    r => r.u || null,
  source:       r => r.src || null,
}};

// ── Lookup indices for fast filtering & global-idx mapping ────────────────
// globalIdx = position in DATA array; filteredIdx = position in current filtered view
let filteredToGlobal = [];  // filteredIdx -> globalIdx

function buildFilterIndex() {{
  filteredToGlobal = [];
  DATA.forEach((ref, gi) => {{
    if (currentFilter === 'all' || F.status(ref) === currentFilter)
      filteredToGlobal.push(gi);
  }});
}}

function filteredRef(fi) {{ return DATA[filteredToGlobal[fi]]; }}
function filteredCount() {{ return filteredToGlobal.length; }}

// ── Helpers ───────────────────────────────────────────────────────────────
function refKey(ref) {{ return F.filename(ref) + '::' + F.index(ref); }}
function getAnnotation(ref) {{ return annotations[refKey(ref)] || null; }}

function setAnnotation(ref, label) {{
  const key = refKey(ref);
  if (label === null) delete annotations[key];
  else annotations[key] = label;
  try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations)); }} catch(e) {{}}
  updateProgress();
  updateMatrix();
}}

function scholarUrl(title) {{
  return 'https://scholar.google.com/scholar?q=' + encodeURIComponent(title);
}}

function escapeHtml(s) {{
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// ── Rendering ─────────────────────────────────────────────────────────────
// Papers are rendered eagerly (headers only), refs are rendered lazily on open.
// Each paper-block stores its filteredIdx range; refs render when paper is opened.

// byFile: filename -> [{{filteredIdx, globalIdx}}]
let byFile = {{}};
let fileOrder = [];

function buildByFile() {{
  byFile = {{}};
  fileOrder = [];
  filteredToGlobal.forEach((gi, fi) => {{
    const ref = DATA[gi];
    const fname = F.filename(ref);
    if (!byFile[fname]) {{ byFile[fname] = []; fileOrder.push(fname); }}
    byFile[fname].push({{fi, gi}});
  }});
}}

function renderAll() {{
  buildFilterIndex();
  buildByFile();
  const main = document.getElementById('main');

  if (filteredCount() === 0) {{
    main.innerHTML = '<div id="empty-msg">No references match the current filter.</div>';
    updateProgress();
    updateMatrix();
    return;
  }}

  // Render paper blocks (collapsed by default — user opens to see cards)
  const frag = document.createDocumentFragment();
  fileOrder.forEach(fname => {{
    const entries = byFile[fname];
    const block = document.createElement('div');
    block.className = 'paper-block';
    block.dataset.file = fname;
    block.innerHTML = paperHeaderHtml(fname, entries);
    block.querySelector('.paper-header').addEventListener('click', () => openPaper(block, fname));
    frag.appendChild(block);
  }});

  main.innerHTML = '';
  main.appendChild(frag);
  updateProgress();
  updateMatrix();
}}

function paperHeaderHtml(fname, entries) {{
  const shortName = fname.replace(/.*\\//, '').replace(/\\.pdf$/i, '');
  const annotated = entries.filter(e => getAnnotation(DATA[e.gi]) !== null).length;
  const statusCounts = {{}};
  entries.forEach(e => {{
    const s = F.status(DATA[e.gi]);
    statusCounts[s] = (statusCounts[s] || 0) + 1;
  }});
  const metaParts = Object.entries(statusCounts).map(([s, n]) => `${{n}} ${{s.replace('_',' ')}}`);
  return `<div class="paper-header">
    <span class="paper-arrow">▶</span>
    <span class="paper-name">${{escapeHtml(shortName)}}</span>
    <span class="paper-meta">${{escapeHtml(metaParts.join(' · '))}} &nbsp;·&nbsp; ${{annotated}}/${{entries.length}} reviewed</span>
  </div>
  <div class="paper-refs"></div>`;
}}

function openPaper(block, fname) {{
  const isOpen = block.classList.contains('open');
  block.classList.toggle('open', !isOpen);
  if (isOpen) return;  // collapsed — nothing to render

  const refsDiv = block.querySelector('.paper-refs');
  if (refsDiv.children.length > 0) return;  // already rendered

  const entries = byFile[fname] || [];
  const frag = document.createDocumentFragment();
  entries.forEach(e => {{
    const card = buildRefCard(DATA[e.gi], e.fi);
    frag.appendChild(card);
  }});
  refsDiv.appendChild(frag);
}}

function buildRefCard(ref, fi) {{
  const ann = getAnnotation(ref);
  const card = document.createElement('div');
  card.className = 'ref-card' + (ann ? ` annotated-${{ann}}` : '');
  card.dataset.globalIdx = DATA.indexOf(ref);
  card.dataset.filteredIdx = fi;
  card.tabIndex = 0;
  card.innerHTML = refCardInner(ref, fi);
  attachCardEvents(card, ref, fi);
  return card;
}}

function refCardInner(ref, fi) {{
  const ann = getAnnotation(ref);
  const status = F.status(ref);
  const title = F.title(ref);
  const url = F.paper_url(ref);
  const source = F.source(ref);
  const refAuthors = F.ref_authors(ref);
  const foundAuthors = F.found_authors(ref);

  const titleHtml = url
    ? `<a href="${{escapeHtml(url)}}" target="_blank">${{escapeHtml(title)}}</a>`
    : escapeHtml(title);

  let authorsHtml = '';
  if (status === 'mismatch' && refAuthors.length > 0) {{
    authorsHtml = `<div class="ref-authors">
      <span class="cited">Cited: ${{escapeHtml(refAuthors.join('; '))}}</span>`;
    if (foundAuthors.length > 0)
      authorsHtml += `<span class="mismatch-arrow"> → </span><span class="found">Found: ${{escapeHtml(foundAuthors.join('; '))}}</span>`;
    authorsHtml += `</div>`;
  }} else if (refAuthors.length > 0) {{
    authorsHtml = `<div class="ref-authors cited">Authors: ${{escapeHtml(refAuthors.join('; '))}}</div>`;
  }}

  const raw = F.raw_citation(ref);
  const rawHtml = raw
    ? `<button class="raw-toggle">show raw citation</button><div class="raw-citation">${{escapeHtml(raw)}}</div>`
    : '';

  const sourceLabel = source ? ` · ${{escapeHtml(source)}}` : '';
  const paperLink = url
    ? `<a class="ref-link" href="${{escapeHtml(url)}}" target="_blank">Open paper ↗${{sourceLabel}}</a>`
    : '';

  let annBtns = '<div class="ann-btns">';
  for (const [label, text] of [['real','Real'],['hallucinated','Hallucinated'],['uncertain','Uncertain']]) {{
    const sel = ann === label ? `selected-${{label}}` : '';
    annBtns += `<button class="ann-btn ${{sel}}" data-label="${{label}}">${{text}}</button>`;
  }}
  annBtns += '</div>';

  return `<div class="ref-header">
    <span class="status-badge badge-${{status}}">${{status.replace('_',' ')}}</span>
    <span class="ref-num">#${{F.ref_num(ref)}}</span>
    <span class="ref-title">${{titleHtml}}</span>
  </div>
  ${{authorsHtml}}
  ${{rawHtml}}
  <div class="ref-footer">
    <a class="ref-link" href="${{scholarUrl(title)}}" target="_blank">Google Scholar ↗</a>
    ${{paperLink}}
    ${{annBtns}}
  </div>`;
}}

function attachCardEvents(card, ref, fi) {{
  card.addEventListener('focus', () => {{ focusedGlobalIdx = parseInt(card.dataset.globalIdx); }});

  const rawToggle = card.querySelector('.raw-toggle');
  if (rawToggle) {{
    rawToggle.addEventListener('click', () => {{
      const raw = rawToggle.nextElementSibling;
      const open = raw.style.display === 'block';
      raw.style.display = open ? 'none' : 'block';
      rawToggle.textContent = open ? 'show raw citation' : 'hide raw citation';
    }});
  }}

  card.querySelectorAll('.ann-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{
      e.stopPropagation();
      const label = btn.dataset.label;
      const current = getAnnotation(ref);
      setAnnotation(ref, current === label ? null : label);
      updateCardAppearance(card, ref);
      updatePaperMeta(F.filename(ref));
    }});
  }});
}}

function updateCardAppearance(card, ref) {{
  const ann = getAnnotation(ref);
  card.className = 'ref-card' + (ann ? ` annotated-${{ann}}` : '');
  card.querySelectorAll('.ann-btn').forEach(btn => {{
    const label = btn.dataset.label;
    btn.className = 'ann-btn' + (ann === label ? ` selected-${{label}}` : '');
  }});
}}

function updatePaperMeta(fname) {{
  const block = document.querySelector(`.paper-block[data-file="${{CSS.escape(fname)}}"]`);
  if (!block) return;
  const entries = byFile[fname] || [];
  const annotated = entries.filter(e => getAnnotation(DATA[e.gi]) !== null).length;
  const statusCounts = {{}};
  entries.forEach(e => {{
    const s = F.status(DATA[e.gi]);
    statusCounts[s] = (statusCounts[s] || 0) + 1;
  }});
  const metaParts = Object.entries(statusCounts).map(([s, n]) => `${{n}} ${{s.replace('_',' ')}}`);
  block.querySelector('.paper-meta').innerHTML =
    `${{escapeHtml(metaParts.join(' · '))}} &nbsp;·&nbsp; ${{annotated}}/${{entries.length}} reviewed`;
}}

// ── Progress ──────────────────────────────────────────────────────────────
function updateProgress() {{
  const total = filteredCount();
  let done = 0;
  filteredToGlobal.forEach(gi => {{ if (getAnnotation(DATA[gi]) !== null) done++; }});
  document.getElementById('progress-text').textContent = `${{done}} / ${{total}} reviewed`;
  document.getElementById('progress-bar').style.width = (total > 0 ? done / total * 100 : 0) + '%';
}}

// ── Confusion matrix ──────────────────────────────────────────────────────
function updateMatrix() {{
  let tp = 0, fp = 0, tn = 0, fn = 0;
  DATA.forEach(ref => {{
    const ann = getAnnotation(ref);
    if (!ann || ann === 'uncertain') return;
    const pos = (F.status(ref) === 'not_found' || F.status(ref) === 'mismatch');
    if (pos  && ann === 'hallucinated') tp++;
    else if (pos  && ann === 'real')        fp++;
    else if (!pos && ann === 'real')        tn++;
    else if (!pos && ann === 'hallucinated') fn++;
  }});

  document.getElementById('mx-tp').textContent = tp;
  document.getElementById('mx-fp').textContent = fp;
  document.getElementById('mx-tn').textContent = tn;
  document.getElementById('mx-fn').textContent = fn;

  const prec = tp+fp > 0 ? tp/(tp+fp) : null;
  const rec  = tp+fn > 0 ? tp/(tp+fn) : null;
  const f1   = prec && rec && (prec+rec) > 0 ? 2*prec*rec/(prec+rec) : null;

  document.getElementById('mx-prec').textContent = prec !== null ? (prec*100).toFixed(1)+'%' : '—';
  document.getElementById('mx-rec').textContent  = rec  !== null ? (rec *100).toFixed(1)+'%' : '—';
  document.getElementById('mx-f1').textContent   = f1   !== null ? (f1  *100).toFixed(1)+'%' : '—';
}}

// ── Filter buttons ────────────────────────────────────────────────────────
document.querySelectorAll('.filter-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    currentFilter = btn.dataset.filter;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderAll();
  }});
}});

// ── Jump to next unannotated ──────────────────────────────────────────────
document.getElementById('jump-btn').addEventListener('click', jumpToNext);

function jumpToNext(startAfterGlobal) {{
  const start = typeof startAfterGlobal === 'number' ? startAfterGlobal : focusedGlobalIdx;
  // Find next unannotated in filteredToGlobal after current position
  const startFi = filteredToGlobal.indexOf(start);
  for (let i = 1; i <= filteredToGlobal.length; i++) {{
    const fi = (startFi + i) % filteredToGlobal.length;
    const gi = filteredToGlobal[fi];
    if (getAnnotation(DATA[gi]) === null) {{
      // Ensure paper is open and card is rendered
      const fname = F.filename(DATA[gi]);
      const block = document.querySelector(`.paper-block[data-file="${{CSS.escape(fname)}}"]`);
      if (block && !block.classList.contains('open')) {{
        block.classList.add('open');
        openPaper(block, fname);
      }}
      setTimeout(() => {{
        const card = document.querySelector(`.ref-card[data-filtered-idx="${{fi}}"]`);
        if (card) {{
          card.scrollIntoView({{behavior: 'smooth', block: 'center'}});
          card.focus();
        }}
      }}, 30);
      return;
    }}
  }}
  alert('All visible refs are annotated!');
}}

// ── Keyboard shortcuts ────────────────────────────────────────────────────
document.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  const focused = document.activeElement;
  const isCard = focused && focused.classList.contains('ref-card');

  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
    e.preventDefault();
    const curFi = isCard ? parseInt(focused.dataset.filteredIdx) : -1;
    const delta = e.key === 'ArrowDown' ? 1 : -1;
    const nextFi = curFi + delta;
    if (nextFi < 0 || nextFi >= filteredCount()) return;
    const nextGi = filteredToGlobal[nextFi];
    const fname = F.filename(DATA[nextGi]);
    const block = document.querySelector(`.paper-block[data-file="${{CSS.escape(fname)}}"]`);
    if (block && !block.classList.contains('open')) {{ block.classList.add('open'); openPaper(block, fname); }}
    setTimeout(() => {{
      const card = document.querySelector(`.ref-card[data-filtered-idx="${{nextFi}}"]`);
      if (card) {{ card.scrollIntoView({{behavior:'smooth',block:'center'}}); card.focus(); }}
    }}, 30);
    return;
  }}

  if (!isCard) return;
  const curFi = parseInt(focused.dataset.filteredIdx);
  const ref = filteredRef(curFi);
  if (!ref) return;

  let label = null;
  if (e.key === 'r' || e.key === 'R') label = 'real';
  else if (e.key === 'h' || e.key === 'H') label = 'hallucinated';
  else if (e.key === 'u' || e.key === 'U') label = 'uncertain';
  else return;

  e.preventDefault();
  const current = getAnnotation(ref);
  setAnnotation(ref, current === label ? null : label);
  updateCardAppearance(focused, ref);
  updatePaperMeta(F.filename(ref));

  // Auto-advance to next unannotated
  setTimeout(() => jumpToNext(filteredToGlobal[curFi]), 50);
}});

// ── Export CSV ────────────────────────────────────────────────────────────
document.getElementById('export-btn').addEventListener('click', () => {{
  const rows = ['Filename,RefIndex,RefNum,Title,PredictedStatus,ManualLabel'];
  DATA.forEach(ref => {{
    const label = getAnnotation(ref) || '';
    const title = F.title(ref).replace(/"/g, '""');
    rows.push(`"${{F.filename(ref)}}","${{F.index(ref)}}","${{F.ref_num(ref)}}","${{title}}","${{F.status(ref)}}","${{label}}"`);
  }});
  const blob = new Blob([rows.join('\\n')], {{type: 'text/csv'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'review-annotations.csv'; a.click();
  URL.revokeObjectURL(url);
}});

// ── Boot ──────────────────────────────────────────────────────────────────
renderAll();
</script>
</body>
</html>
"""


def generate_html(refs: list, title: str = "Hallucinator Review") -> str:
    data_json = json.dumps(refs, ensure_ascii=False, separators=(",", ":"))
    return HTML_TEMPLATE.format(title=title, data_json=data_json)


def main():
    parser = argparse.ArgumentParser(description="Generate standalone HTML review tool from hallucinator JSON output.")
    parser.add_argument("inputs", nargs="+", metavar="JSON", help="One or more hallucinator-results.json files")
    parser.add_argument("--output", "-o", default="review.html", help="Output HTML file (default: review.html)")
    parser.add_argument("--title", default="Hallucinator Review", help="Page title")
    args = parser.parse_args()

    all_refs = []
    for path_str in args.inputs:
        p = Path(path_str)
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)
        refs = load_refs(p)
        print(f"Loaded {len(refs)} reviewable refs from {p.name}")
        all_refs.extend(refs)

    print(f"Total refs: {len(all_refs)}")
    status_counts = {}
    for r in all_refs:
        status_counts[r["s"]] = status_counts.get(r["s"], 0) + 1
    for s, n in sorted(status_counts.items()):
        print(f"  {s}: {n}")

    html = generate_html(all_refs, title=args.title)
    out = Path(args.output)
    out.write_text(html, encoding="utf-8")
    print(f"\nGenerated: {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
