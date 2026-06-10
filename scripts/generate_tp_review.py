#!/usr/bin/env python3
#python3 generate_tp_review.py PATH/TO/review-annotations.csv --results-json PATH/TO/hallucinator-results.json --output tp-review --era pre|post|auto

import argparse
import csv
import json
import os
import sys
from html import escape

BASE_CATEGORIES = [
    "Typo",
    "Author mistake",
    "Reference generator format mistake",
    "Missing part of title/reference",
    "Paper not found",
]
POST_ONLY_CATEGORIES = [
    "Possible hallucination",
]

CHECKABLE_POSITIVE = {"not_found", "mismatch"}


def detect_era(rows):
    prefixes = {r["Filename"].split("/")[0].lower() for r in rows if r.get("Filename")}
    joined = " ".join(prefixes)
    if "post" in joined:
        return "post"
    if "pre" in joined:
        return "pre"
    return "pre"


def load_raw_map(json_path):
    """Map (basename, str(index)) -> raw_citation, canonicalised on basename."""
    m = {}
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    for paper in data:
        base = os.path.basename(paper.get("filename", ""))
        for ref in paper.get("references", []):
            m[(base, str(ref.get("index")))] = ref.get("raw_citation", "") or ""
    return m


def main():
    ap = argparse.ArgumentParser(description="Generate a TP review HTML + CSV.")
    ap.add_argument("annotations_csv", help="Path to review-annotations.csv")
    ap.add_argument("--results-json", default=None,
                    help="Optional hallucinator-results.json for raw citations")
    ap.add_argument("--output", default="tp-review",
                    help="Output prefix (default: tp-review)")
    ap.add_argument("--era", choices=["pre", "post", "auto"], default="auto",
                    help="Category set to use (default: auto-detect from filenames)")
    args = ap.parse_args()

    with open(args.annotations_csv, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Filename") != "Filename"]

    era = detect_era(rows) if args.era == "auto" else args.era
    categories = BASE_CATEGORIES[:]
    if era == "post":
        categories = BASE_CATEGORIES + POST_ONLY_CATEGORIES

    raw_map = load_raw_map(args.results_json) if args.results_json else {}

    tps = []
    for r in rows:
        status = (r.get("PredictedStatus") or "").strip()
        label = (r.get("ManualLabel") or "").strip().lower()
        if status in CHECKABLE_POSITIVE and label == "hallucinated":
            base = os.path.basename(r.get("Filename", ""))
            raw = raw_map.get((base, r.get("RefIndex")), "") or r.get("Title", "") or ""
            tps.append({
                "paper": base,
                "filename": r.get("Filename", ""),
                "ref_index": r.get("RefIndex", ""),
                "ref_num": r.get("RefNum", ""),
                "status": status,
                "raw": raw,
            })

    if not tps:
        print("No TP rows found (PredictedStatus in {not_found,mismatch} AND "
              "ManualLabel == 'hallucinated').", file=sys.stderr)

    csv_path = f"{args.output}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Paper", "Filename", "RefIndex", "RefNum",
                    "PredictedStatus", "RawCitation", "ReviewCategory", "ReviewNote"])
        for t in tps:
            w.writerow([t["paper"], t["filename"], t["ref_index"], t["ref_num"],
                        t["status"], t["raw"], "", ""])

    html_path = f"{args.output}.html"
    payload = json.dumps(tps, ensure_ascii=False)
    cats = json.dumps(categories, ensure_ascii=False)
    html = (HTML_TEMPLATE
            .replace("__ERA__", escape(era.upper()))
            .replace("__COUNT__", str(len(tps)))
            .replace("/*__DATA__*/", payload)
            .replace("/*__CATEGORIES__*/", cats))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"era               : {era}")
    print(f"TPs filtered      : {len(tps)}")
    print(f"CSV  -> {csv_path}")
    print(f"HTML -> {html_path}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TP Review (__ERA__)</title>
<style>
  :root{
    --bg:#0f1729; --panel:#16203a; --panel2:#1b2745; --line:#2a3a5e;
    --text:#e6edf7; --muted:#8aa0c4; --green:#43c59e; --amber:#e0a13c;
    --red:#d9586a; --blue:#5aa9e6;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:1180px;margin:0 auto;padding:28px 22px 80px}
  h1{color:var(--green);margin:0 0 4px;font-size:24px}
  .sub{color:var(--muted);margin:0 0 18px;font-size:13px}
  .bar{display:flex;gap:14px;align-items:center;flex-wrap:wrap;
       position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:5;
       border-bottom:1px solid var(--line)}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;
        padding:8px 14px;min-width:96px}
  .stat .n{font-size:20px;font-weight:700}
  .stat .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
  .stat.done .n{color:var(--green)}
  button{background:var(--panel2);color:var(--text);border:1px solid var(--line);
         border-radius:8px;padding:9px 14px;font-size:13px;cursor:pointer}
  button:hover{border-color:var(--green);color:var(--green)}
  .spacer{flex:1}
  table{width:100%;border-collapse:collapse;margin-top:14px}
  th{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;
     text-align:left;padding:10px 10px;border-bottom:1px solid var(--line)}
  td{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  tr.labeled{background:rgba(67,197,158,.06)}
  .paper{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--blue);
         white-space:nowrap}
  .num{color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
  .raw{max-width:520px}
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;
         border:1px solid}
  .badge.not_found{color:var(--amber);border-color:var(--amber)}
  .badge.mismatch{color:var(--red);border-color:var(--red)}
  select,input.note{width:100%;background:var(--panel);color:var(--text);
         border:1px solid var(--line);border-radius:8px;padding:8px}
  select:focus,input.note:focus{outline:none;border-color:var(--green)}
  .colcat{width:230px} .colnote{width:200px}
  .empty{color:var(--muted);padding:40px;text-align:center}
</style>
</head>
<body>
<div class="wrap">
  <h1>Confirmed-Hallucination Review &middot; __ERA__</h1>
  <p class="sub">Re-label each true positive. Selections are saved in this browser; use Export to download your decisions.</p>

  <div class="bar">
    <div class="stat"><div class="n">__COUNT__</div><div class="l">TPs</div></div>
    <div class="stat done"><div class="n" id="doneN">0</div><div class="l">Labeled</div></div>
    <div class="spacer"></div>
    <button onclick="exportCSV()">Export CSV</button>
    <button onclick="exportJSON()">Export JSON</button>
    <button onclick="clearAll()">Clear</button>
  </div>

  <table id="tbl">
    <thead><tr>
      <th>Paper</th><th class="num">#</th><th>Raw Citation</th><th>Status</th>
      <th class="colcat">Category</th><th class="colnote">Notes</th>
    </tr></thead>
    <tbody id="body"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">No TPs in this file.</div>
</div>

<script>
const DATA = /*__DATA__*/;
const CATEGORIES = /*__CATEGORIES__*/;
const ERA = "__ERA__";
const KEY = "tp_review_" + ERA;

function rid(t){ return t.filename + "||" + t.ref_index; }
function load(){ try{ return JSON.parse(localStorage.getItem(KEY)) || {}; }catch(e){ return {}; } }
function save(s){ try{ localStorage.setItem(KEY, JSON.stringify(s)); }catch(e){} }
let state = load();

function refreshDone(){
  let n = 0;
  for(const t of DATA){ const s = state[rid(t)]; if(s && s.category) n++; }
  document.getElementById("doneN").textContent = n;
}

function render(){
  const body = document.getElementById("body");
  if(!DATA.length){ document.getElementById("tbl").style.display="none";
                    document.getElementById("empty").style.display="block"; return; }
  body.innerHTML = "";
  DATA.forEach(t => {
    const id = rid(t);
    const cur = state[id] || {category:"", note:""};
    const tr = document.createElement("tr");
    if(cur.category) tr.classList.add("labeled");

    const opts = ['<option value="">— select —</option>']
      .concat(CATEGORIES.map(c => `<option ${c===cur.category?"selected":""}>${c}</option>`)).join("");

    tr.innerHTML =
      `<td class="paper">${t.paper.replace(/\.pdf$/,'')}</td>`+
      `<td class="num">${t.ref_num}</td>`+
      `<td class="raw">${escapeHtml(t.raw)}</td>`+
      `<td><span class="badge ${t.status}">${t.status}</span></td>`+
      `<td class="colcat"><select>${opts}</select></td>`+
      `<td class="colnote"><input class="note" value="${escapeAttr(cur.note)}" placeholder="optional"></td>`;

    const sel = tr.querySelector("select");
    const note = tr.querySelector("input.note");
    sel.addEventListener("change", () => {
      state[id] = {category: sel.value, note: note.value};
      tr.classList.toggle("labeled", !!sel.value);
      save(state); refreshDone();
    });
    note.addEventListener("input", () => {
      state[id] = {category: sel.value, note: note.value};
      save(state);
    });
    body.appendChild(tr);
  });
  refreshDone();
}

function escapeHtml(s){ return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function escapeAttr(s){ return escapeHtml(s).replace(/"/g,"&quot;"); }

function rowsForExport(){
  return DATA.map(t => {
    const s = state[rid(t)] || {category:"", note:""};
    return {Paper:t.paper, Filename:t.filename, RefIndex:t.ref_index, RefNum:t.ref_num,
            PredictedStatus:t.status, RawCitation:t.raw,
            ReviewCategory:s.category||"", ReviewNote:s.note||""};
  });
}
function download(name, text, type){
  const b = new Blob([text], {type});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}
function exportCSV(){
  const cols = ["Paper","Filename","RefIndex","RefNum","PredictedStatus","RawCitation","ReviewCategory","ReviewNote"];
  const esc = v => '"'+String(v==null?"":v).replace(/"/g,'""')+'"';
  const lines = [cols.join(",")].concat(rowsForExport().map(r => cols.map(c => esc(r[c])).join(",")));
  download("tp-review-labeled.csv", lines.join("\n"), "text/csv");
}
function exportJSON(){ download("tp-review-labeled.json", JSON.stringify(rowsForExport(), null, 2), "application/json"); }
function clearAll(){ if(confirm("Clear all labels in this browser?")){ state={}; save(state); render(); } }

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
