#!/usr/bin/env python3
"""
Compute confusion matrix and classification metrics from hallucinator review annotations.
Always writes both a CSV and an HTML report.
If a hallucinator-results.csv exists in the same directory as the annotations file,
it is merged automatically to enrich the FP-by-source-DB breakdown.

Usage:
    python scripts/compute_stats.py data/icml/pre/review-annotations.csv:Pre data/icml/post/review-annotations.csv:Post
    python scripts/compute_stats.py ... --output results/icml-stats   # writes icml-stats.csv + icml-stats.html

Label interpretation (from the review tool):
    ""            (empty)       = verified ref, assumed real  → TN
    "hallucinated"              = tool was right, paper is fake → TP
    "real"                      = tool was wrong, paper is real → FP
    "uncertain"                 = extraction error / can't verify → FN
"""

import csv
import math
import sys
import argparse
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    fn_not_found: int = 0
    fn_mismatch: int = 0
    fp_not_found: int = 0
    fp_mismatch: int = 0
    per_paper_tp: dict = field(default_factory=lambda: defaultdict(int))
    per_paper_fp: dict = field(default_factory=lambda: defaultdict(int))
    per_paper_fn: dict = field(default_factory=lambda: defaultdict(int))
    per_paper_tn: dict = field(default_factory=lambda: defaultdict(int))
    fp_by_source: dict = field(default_factory=lambda: defaultdict(int))
    tp_refs: list = field(default_factory=list)   # (paper_short, ref_num, raw_citation, status)
    total_papers: int = 0


# ── Math helpers ───────────────────────────────────────────────────────────

def _div(a: int, b: int) -> Optional[float]:
    return a / b if b > 0 else None


def _pct(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{decimals}f}%"


def _fmt(v: Optional[float], decimals: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def _mcc(tp: int, fp: int, tn: int, fn: int) -> Optional[float]:
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / denom if denom else None




# ── Data loading ───────────────────────────────────────────────────────────

def load_annotations(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_raw_citations(json_path: Path) -> dict:
    """Return dict of (filename, ref_index_str) -> raw_citation from results JSON."""
    import json
    with open(json_path, encoding="utf-8") as f:
        papers = json.load(f)
    m = {}
    for paper in papers:
        for ref in paper.get("references", []):
            key = (paper["filename"], str(ref["index"]))
            m[key] = ref.get("raw_citation", "") or ""
    return m


def load_source_map(results_path: Path) -> dict:
    # value: (source_db, paper_url)
    m = {}
    with open(results_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Join key uses Ref# (1-based original number), matching RefNum in annotations
            m[(row["Filename"], row.get("Ref#", ""))] = (
                row.get("Source", "") or "unknown",
                row.get("PaperURL", "") or None,
            )
    return m


def compute_counts(rows: list[dict], source_map: dict = None, raw_citation_map: dict = None) -> Counts:
    c = Counts()
    papers = set()
    for row in rows:
        filename = row["Filename"]
        ref_num  = row["RefNum"]   # 1-based, matches Ref# in hallucinator-results.csv
        status   = row["PredictedStatus"]
        label    = row["ManualLabel"].strip()
        papers.add(filename)

        predicted_pos = status in ("not_found", "mismatch")
        if not predicted_pos:
            c.tn += 1
            c.per_paper_tn[filename] += 1
        elif label == "hallucinated":
            c.tp += 1
            c.per_paper_tp[filename] += 1
            paper_short = filename.split("/")[-1].replace(".pdf", "")
            raw = (raw_citation_map.get((filename, row["RefIndex"]), "") if raw_citation_map else "") or row.get("Title", "")
            c.tp_refs.append((paper_short, ref_num, raw, status))
        elif label == "real":
            c.fp += 1
            c.per_paper_fp[filename] += 1
            if status == "not_found": c.fp_not_found += 1
            else:                     c.fp_mismatch  += 1
            if source_map:
                c.fp_by_source[source_map.get((filename, ref_num), ("unknown", None))[0]] += 1
        else:
            c.fn += 1
            c.per_paper_fn[filename] += 1
            if status == "not_found": c.fn_not_found += 1
            else:                     c.fn_mismatch  += 1

    c.total_papers = len(papers)
    return c


# ── Console output ─────────────────────────────────────────────────────────

def _rq1_rates(c: Counts) -> dict:
    total = c.tp + c.fp + c.tn + c.fn
    return {
        "total":       total,
        "flagged":     c.tp + c.fp + c.fn,
        "refs_per_paper": total / c.total_papers if c.total_papers else None,
        "flagged_rate":   _div(c.tp + c.fp + c.fn, total),
        "hall_rate":      _div(c.tp,  total),
        "fp_rate":        _div(c.fp,  total),
        "fn_rate":        _div(c.fn,  total),
    }


def print_dataset_report(label: str, c: Counts, show_source: bool = False):
    r = _rq1_rates(c)
    w = 52
    print("═" * w)
    print(f"  {label}  ({c.total_papers} papers · {r['total']} checkable refs)")
    print("═" * w)
    print(f"\n  Refs per paper (avg)   {r['refs_per_paper']:>6.1f}")
    print(f"  Flagged by tool        {r['flagged']:>6}  ({_pct(r['flagged_rate'])} of checkable refs)")

    print(f"\n  Confusion Matrix:")
    print(f"                       Predicted +   Predicted -")
    print(f"    Actual +  (hall.)  {c.tp:>10} (TP)  {c.fn:>10} (FN)")
    print(f"    Actual -  (real)   {c.fp:>10} (FP)  {c.tn:>10} (TN)")

    if c.tp_refs:
        print(f"\n  Confirmed hallucinations ({c.tp}):")
        for paper, ref_num, raw, status in sorted(c.tp_refs, key=lambda x: (x[0], int(x[1]) if x[1].isdigit() else 0)):
            tag = "[mismatch]" if status == "mismatch" else ""
            print(f"    {paper}  #{ref_num:>3}  {raw[:80]}{' …' if len(raw)>80 else ''}  {tag}")
    else:
        print(f"\n  No confirmed hallucinations.")
    print()


def print_comparison(datasets: list[tuple[str, Counts]]):
    labels = [l for l, _ in datasets]
    counts = [c for _, c in datasets]
    col_w  = max(10, max(len(l) for l in labels) + 2)
    rlw    = 28

    def row(name, values, bold=False):
        print(f"  {name:<{rlw}}" + "".join(f"{v:>{col_w}}" for v in values))

    sep  = "═" * (rlw + col_w * len(datasets) + 2)
    thin = "─" * (rlw + col_w * len(datasets) + 2)
    print(sep)
    print(f"  {'RQ1 Comparison':<{rlw}}" + "".join(f"{l:>{col_w}}" for l in labels))
    print(thin)

    rates = [_rq1_rates(c) for c in counts]
    row("Papers",                    [c.total_papers for c in counts])
    row("Checkable refs",            [r["total"]   for r in rates])
    row("Refs per paper (avg)",      [f"{r['refs_per_paper']:.1f}" for r in rates])
    print(thin)
    row("Flagged by tool",           [r["flagged"] for r in rates])
    row("  Confirmed hallucinated",  [c.tp for c in counts])
    row("  False positive",          [c.fp for c in counts])
    row("  Extraction error",        [c.fn for c in counts])
    print(thin)
    row("Flagged rate",              [_pct(r["flagged_rate"]) for r in rates])
    row("  Hallucination rate",      [_pct(r["hall_rate"])    for r in rates])
    row("  False positive rate",     [_pct(r["fp_rate"])      for r in rates])
    row("  Extraction error rate",   [_pct(r["fn_rate"])      for r in rates])
    print(sep)
    print()


# ── CSV output ─────────────────────────────────────────────────────────────

def write_csv(path: Path, datasets: list[tuple[str, Counts]]):
    rows = []
    for label, c in datasets:
        r = _rq1_rates(c)
        rows.append({
            "Dataset":              label,
            "Papers":               c.total_papers,
            "Checkable_Refs":       r["total"],
            "Refs_Per_Paper":       f"{r['refs_per_paper']:.2f}" if r["refs_per_paper"] else "",
            "Flagged":              r["flagged"],
            "Confirmed_Hallucinated": c.tp,
            "False_Positive":       c.fp,
            "Extraction_Error":     c.fn,
            "Verified":             c.tn,
            "Flagged_Rate":         _fmt(r["flagged_rate"]),
            "Hallucination_Rate":   _fmt(r["hall_rate"]),
            "False_Positive_Rate":  _fmt(r["fp_rate"]),
            "Extraction_Error_Rate":_fmt(r["fn_rate"]),
        })
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"CSV  → {path}")


# ── HTML output ────────────────────────────────────────────────────────────

def _he(s) -> str:
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")




def _rate_bar(value: int, total: int, color: str, label: str) -> str:
    pct = value / total * 100 if total else 0
    return (f'<div style="margin-bottom:0.9rem">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:3px">'
            f'<span style="color:var(--dim)">{label}</span>'
            f'<span style="color:{color};font-weight:700">{value:,} &nbsp;({pct:.1f}%)</span>'
            f'</div>'
            f'<div style="background:var(--border);border-radius:3px;height:10px">'
            f'<div style="width:{pct:.2f}%;background:{color};height:100%;border-radius:3px"></div>'
            f'</div></div>')


def _mx_cell(value: int, sublabel: str, color: str, bg: str) -> str:
    return (f'<td style="text-align:center;padding:1rem 1.4rem;background:{bg};border-radius:6px">'
            f'<div style="font-size:1.8rem;font-weight:700;color:{color}">{value}</div>'
            f'<div style="font-size:0.72rem;color:var(--dim);margin-top:2px">{sublabel}</div>'
            f'</td>')


def _section_html(label: str, c: Counts, show_source: bool) -> str:
    r = _rq1_rates(c)
    total   = r["total"]
    flagged = r["flagged"]

    # ── stat cards ────────────────────────────────────────────────
    cards = [
        ("Papers",         c.total_papers,                   "var(--blue)"),
        ("Checkable Refs", total,                             "var(--text)"),
        ("Refs / Paper",   f"{r['refs_per_paper']:.1f}",     "var(--dim)"),
        ("Flagged",        flagged,                           "var(--yellow)"),
        ("Verified",       c.tn,                              "var(--green)"),
    ]
    cards_html = '<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:2rem">'
    for card_label, val, color in cards:
        cards_html += (f'<div class="stat-card"><span class="number" style="color:{color}">{val}</span>'
                       f'<span class="label">{card_label}</span></div>')
    cards_html += '</div>'

    # ── confusion matrix ──────────────────────────────────────────
    matrix_html = f'''
<h3 style="margin-bottom:1rem">Confusion Matrix
  <span style="color:var(--dim);font-weight:400;font-size:0.8rem">&nbsp;({_pct(r["flagged_rate"])} flagged)</span>
</h3>
<table style="border-collapse:separate;border-spacing:5px;margin-bottom:2rem">
  <thead><tr>
    <th style="font-weight:400;color:var(--dim);padding:0 0.5rem"></th>
    <th style="font-weight:400;color:var(--dim);text-align:center;padding:0 0.5rem">Predicted +<br><small>flagged</small></th>
    <th style="font-weight:400;color:var(--dim);text-align:center;padding:0 0.5rem">Predicted −<br><small>verified</small></th>
  </tr></thead>
  <tbody>
    <tr>
      <td style="color:var(--dim);font-size:0.8rem;padding-right:0.5rem;white-space:nowrap">Actual +<br><small>hallucinated</small></td>
      {_mx_cell(c.tp, "TP", "var(--green)",  "#0b3d25")}
      {_mx_cell(c.fn, "FN", "var(--red)",    "#3d0b0b")}
    </tr>
    <tr>
      <td style="color:var(--dim);font-size:0.8rem;padding-right:0.5rem;white-space:nowrap">Actual −<br><small>real</small></td>
      {_mx_cell(c.fp, "FP", "var(--yellow)", "#3d2e00")}
      {_mx_cell(c.tn, "TN", "var(--blue)",   "#0b1e3d")}
    </tr>
  </tbody>
</table>'''

    # ── TP reference list ─────────────────────────────────────────
    if c.tp_refs:
        tp_html = f'<h3 style="margin-bottom:0.75rem;color:var(--green)">Confirmed Hallucinations ({c.tp})</h3>'
        tp_html += '<table class="data-table" style="margin-bottom:2rem"><thead><tr><th>Paper</th><th>#</th><th>Raw Citation</th><th>Status</th></tr></thead><tbody>'
        for paper, ref_num, raw, status in sorted(c.tp_refs, key=lambda x: (x[0], int(x[1]) if x[1].isdigit() else 0)):
            badge_color = "var(--yellow)" if status == "mismatch" else "var(--red)"
            tp_html += (f'<tr>'
                        f'<td style="font-family:monospace;font-size:0.8rem;white-space:nowrap">{_he(paper)}</td>'
                        f'<td style="text-align:right;color:var(--dim)">{_he(ref_num)}</td>'
                        f'<td style="font-size:0.82rem">{_he(raw)}</td>'
                        f'<td style="color:{badge_color};font-size:0.8rem;white-space:nowrap">{_he(status)}</td>'
                        f'</tr>')
        tp_html += '</tbody></table>'
    else:
        tp_html = '<p style="color:var(--dim);font-size:0.85rem;margin-bottom:2rem">No confirmed hallucinations.</p>'

    return f'''
  <div>
    <h2 style="color:var(--green);margin-bottom:1.5rem;border-bottom:1px solid var(--border);padding-bottom:0.5rem">{_he(label)}</h2>
    {cards_html}
    {matrix_html}
    {tp_html}
  </div>'''


def _comparison_html(datasets: list[tuple[str, Counts]]) -> str:
    labels = [l for l, _ in datasets]
    counts = [c for _, c in datasets]
    rates  = [_rq1_rates(c) for c in counts]

    header = "<tr><th></th>" + "".join(f"<th style='text-align:right'>{_he(l)}</th>" for l in labels) + "</tr>"

    def trow(name, vals, bold=False, indent=False, color=None):
        style = "font-weight:700;" if bold else ""
        name_cell = f'<td style="color:var(--dim);padding-left:{"1.5rem" if indent else "0"}">{name}</td>'
        val_cells = "".join(
            f'<td style="text-align:right;{style}{"color:"+color+";" if color else ""}">{v}</td>'
            for v in vals
        )
        return f"<tr>{name_cell}{val_cells}</tr>"

    def sep_row():
        return f'<tr><td colspan="{len(labels)+1}" style="padding:2px 0;border-bottom:1px solid var(--border)"></td></tr>'

    rows_html = ""
    rows_html += trow("Papers",                   [str(c.total_papers) for c in counts])
    rows_html += trow("Checkable refs",           [f"{r['total']:,}" for r in rates])
    rows_html += trow("Refs per paper (avg)",     [f"{r['refs_per_paper']:.1f}" for r in rates])
    rows_html += sep_row()
    rows_html += trow("Flagged by tool",          [f"{r['flagged']:,}" for r in rates], bold=True)
    rows_html += trow("Confirmed hallucinated",   [str(c.tp) for c in counts], indent=True, color="var(--green)")
    rows_html += trow("False positive",           [str(c.fp) for c in counts], indent=True, color="var(--blue)")
    rows_html += trow("Extraction error",         [str(c.fn) for c in counts], indent=True, color="var(--red)")
    rows_html += sep_row()
    rows_html += trow("Flagged rate",             [_pct(r["flagged_rate"]) for r in rates], bold=True)
    rows_html += trow("Hallucination rate",       [_pct(r["hall_rate"])    for r in rates], indent=True, color="var(--green)")
    rows_html += trow("False positive rate",      [_pct(r["fp_rate"])      for r in rates], indent=True, color="var(--blue)")
    rows_html += trow("Extraction error rate",    [_pct(r["fn_rate"])      for r in rates], indent=True, color="var(--red)")

    return f'''
<section style="margin-bottom:3rem">
  <h2 style="color:var(--green);margin-bottom:1.5rem;border-bottom:1px solid var(--border);padding-bottom:0.5rem">Comparison</h2>
  <table class="data-table" style="max-width:520px">
    <thead>{header}</thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>'''


def write_html(path: Path, datasets: list[tuple[str, Counts]], show_source: bool):
    section_bodies = [_section_html(label, c, show_source) for label, c in datasets]
    if len(section_bodies) > 1:
        sections = (f'<div style="display:grid;grid-template-columns:repeat({len(section_bodies)},1fr);'
                    f'gap:2rem;margin-bottom:3rem">' + "".join(section_bodies) + '</div>')
    else:
        sections = f'<div style="margin-bottom:3rem">{section_bodies[0]}</div>'
    comparison = _comparison_html(datasets) if len(datasets) > 1 else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hallucinator Statistics</title>
<style>
:root {{
  --bg: #1a1a2e; --surface: #16213e; --card: #0f3460;
  --text: #e0e0e0; --dim: #888; --border: #2a2a4a;
  --green: #4ecca3; --red: #e74c3c; --yellow: #f39c12; --blue: #3498db;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; }}
h1 {{ color: var(--green); margin-bottom: 0.25rem; font-size: 1.8rem; }}
h2 {{ font-size: 1.3rem; }}
h3 {{ font-size: 1rem; color: var(--text); }}
.subtitle {{ color: var(--dim); margin-bottom: 2.5rem; font-size: 0.9rem; }}
.stat-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
              padding: 1rem 1.5rem; text-align: center; min-width: 120px; }}
.stat-card .number {{ font-size: 2rem; font-weight: bold; display: block; }}
.stat-card .label  {{ font-size: 0.8rem; color: var(--dim); }}
.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
.data-table th {{ background: var(--surface); color: var(--dim); font-weight: 600;
                  text-align: left; padding: 0.5rem 0.75rem;
                  border-bottom: 1px solid var(--border); }}
.data-table td {{ padding: 0.45rem 0.75rem; border-bottom: 1px solid var(--border); }}
.data-table tbody tr:hover {{ background: var(--surface); }}
</style>
</head>
<body>
<h1>Hallucinator Statistics After Manual Review </h1>
<p class="subtitle">RQ1 — How did the unverifiable-reference rate change after the LLM-era onset?<br>
<small>Flagged = not found or mismatch after DB lookup &nbsp;|&nbsp;
Confirmed hallucinated = manually verified fake &nbsp;|&nbsp;
False positive = real paper with DB gap &nbsp;|&nbsp;
Extraction error = parser failure, can't judge</small></p>
{sections}
{comparison}
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    print(f"HTML → {path}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compute confusion matrix and metrics from hallucinator review annotations."
    )
    parser.add_argument(
        "datasets", nargs="+", metavar="CSV[:LABEL]",
        help="review-annotations.csv path, optionally with a :Label suffix",
    )
    parser.add_argument(
        "--output", "-o", metavar="BASE", default="hallucinator-stats",
        help="Output base name (default: hallucinator-stats). Writes BASE.csv and BASE.html",
    )
    args = parser.parse_args()

    datasets: list[tuple[str, Counts]] = []
    any_source = False

    for spec in args.datasets:
        path_str, label = spec.rsplit(":", 1) if ":" in spec else (spec, Path(spec).stem)
        path = Path(path_str)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)

        # Auto-discover hallucinator-results.csv and .json in the same directory
        source_map = None
        results_csv = path.parent / "hallucinator-results.csv"
        if results_csv.exists():
            source_map = load_source_map(results_csv)
            any_source = True

        raw_citation_map = None
        results_json = path.parent / "hallucinator-results.json"
        if results_json.exists():
            raw_citation_map = load_raw_citations(results_json)

        rows = load_annotations(path)
        c = compute_counts(rows, source_map, raw_citation_map)
        datasets.append((label, c))
        print_dataset_report(label, c, show_source=source_map is not None)

    if len(datasets) > 1:
        print_comparison(datasets)

    base = Path(args.output)
    base.parent.mkdir(parents=True, exist_ok=True)
    write_csv(base.with_suffix(".csv"), datasets)
    write_html(base.with_suffix(".html"), datasets, show_source=any_source)


if __name__ == "__main__":
    main()
