"""Self-contained HTML report: a sortable/filterable results table, a verdict
summary with agreement banner and per-method leaderboard, and embedded plot
links. The data aggregation lives in run_summary.py; this module only renders.
"""

import html
import logging
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from custom_types import Result
from results_io import _flatten_result
from run_summary import RunSummary

logger: logging.Logger = logging.getLogger(__name__)

_HTML_COLLAPSIBLE_FIELDS = ('stdout', 'stderr', 'error')
_HTML_COLLAPSIBLE_THRESHOLD = 80
_HTML_SEARCH_SKIP_FIELDS = frozenset({'stdout', 'stderr', 'error'})
_HTML_STATUS_CLASS = {
    'SAT': 'status-sat',
    'UNSAT': 'status-unsat',
    'OK': 'status-sat',
    'TIMEOUT': 'status-timeout',
    'ERROR': 'status-error',
    'EXIT_ERROR': 'status-error',
    'MISSING_OUTPUT': 'status-error',
    'PARSER_ERROR': 'status-error',
    'BREAKER_ERROR': 'status-error',
    'CONFLICT': 'status-error',
    'UNKNOWN': 'status-unknown',
}

_HTML_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 1.5rem; }
h1 { margin-top: 0; }
.meta { color: #666; font-size: 0.9rem; margin-bottom: 1rem; }
.controls { margin-bottom: 0.75rem; display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.controls input { padding: 0.4rem 0.6rem; font-size: 0.95rem; min-width: 280px; }
.controls .count { color: #666; font-size: 0.9rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { border: 1px solid #ccc; padding: 0.35rem 0.55rem; text-align: left; vertical-align: top; }
th { background: #f0f0f0; cursor: pointer; user-select: none; position: sticky; top: 0; white-space: nowrap; }
th.sorted-asc::after { content: ' ▲'; color: #555; }
th.sorted-desc::after { content: ' ▼'; color: #555; }
tbody tr:nth-child(even) { background: #fafafa; }
tbody tr.hidden { display: none; }
td { white-space: nowrap; max-width: 30rem; overflow: hidden; text-overflow: ellipsis; }
td details { white-space: normal; }
td details pre { background: #f4f4f4; padding: 0.5rem; overflow-x: auto; max-height: 20rem; margin: 0.3rem 0 0; }
.status-sat { background: #d4edda !important; color: #155724; font-weight: 600; }
.status-unsat { background: #d1ecf1 !important; color: #0c5460; font-weight: 600; }
.status-timeout { background: #fff3cd !important; color: #856404; font-weight: 600; }
.status-error { background: #f8d7da !important; color: #721c24; font-weight: 600; }
.status-unknown { background: #e2e3e5 !important; color: #383d41; }
.summary { margin-bottom: 1.5rem; }
.summary h2 { margin-bottom: 0.5rem; }
.summary-table { width: auto; min-width: 40%; margin-top: 0.5rem; }
.banner { padding: 0.6rem 0.9rem; border-radius: 4px; font-weight: 600; margin: 0.5rem 0; }
.banner-ok { background: #d4edda; color: #155724; }
.banner-conflict { background: #f8d7da; color: #721c24; }
.plots { margin-top: 2rem; }
.plots h2 { margin-bottom: 0.5rem; }
.plot { margin: 1rem 0; padding: 0.5rem; border: 1px solid #ddd; background: #fff; }
.plot h3 { margin: 0 0 0.5rem; font-size: 1rem; color: #444; }
.plot svg { max-width: 100%; height: auto; }
@media (prefers-color-scheme: dark) {
  body { background: #1e1e1e; color: #e0e0e0; }
  th { background: #2d2d2d; }
  tbody tr:nth-child(even) { background: #252525; }
  td details pre { background: #2a2a2a; }
  .plot { background: #2a2a2a; border-color: #444; }
  .meta, .controls .count { color: #aaa; }
}
"""

_HTML_SCRIPT = """
(function() {
  const table = document.getElementById('results-table');
  if (!table) return;
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const headers = Array.from(table.tHead.rows[0].cells);
  const filterInput = document.getElementById('filter');
  const countLabel = document.getElementById('row-count');
  const total = rows.length;

  function updateCount(visible) {
    countLabel.textContent = visible === total
      ? `${total} rows`
      : `${visible} of ${total} rows`;
  }

  let filterTimer = null;
  function applyFilter(q) {
    let visible = 0;
    for (const row of rows) {
      const match = !q || row.dataset.search.includes(q);
      row.classList.toggle('hidden', !match);
      if (match) visible++;
    }
    updateCount(visible);
  }
  filterInput.addEventListener('input', function() {
    const q = this.value.toLowerCase();
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => applyFilter(q), 120);
  });

  let sortState = { col: -1, dir: 1 };
  function compare(a, b, col, numeric) {
    const av = a.cells[col].dataset.sort ?? a.cells[col].textContent.trim();
    const bv = b.cells[col].dataset.sort ?? b.cells[col].textContent.trim();
    if (numeric) {
      const an = parseFloat(av), bn = parseFloat(bv);
      const aBad = isNaN(an), bBad = isNaN(bn);
      if (aBad && bBad) return 0;
      if (aBad) return 1;
      if (bBad) return -1;
      return an - bn;
    }
    return av.localeCompare(bv);
  }

  headers.forEach((th, i) => {
    th.addEventListener('click', () => {
      const dir = (sortState.col === i) ? -sortState.dir : 1;
      sortState = { col: i, dir };
      const numeric = th.dataset.numeric === '1';
      const sorted = rows.slice().sort((a, b) => dir * compare(a, b, i, numeric));
      for (const r of sorted) tbody.appendChild(r);
      headers.forEach(h => h.classList.remove('sorted-asc', 'sorted-desc'));
      th.classList.add(dir === 1 ? 'sorted-asc' : 'sorted-desc');
    });
  });

  updateCount(total);
})();
"""

_NUMERIC_FIELDS = {
    'time', 'cpu_time', 'total_time', 'break_time', 'conversion_time',
    'cpu_usage_avg', 'memory_peak_mb', 'conversion_cpu_time', 'conversion_memory_mb',
    'break_cpu_time', 'break_memory_mb', 'exit_code',
    'restarts', 'conflicts', 'branches', 'decisions', 'propagations',
    'nodes', 'iterations', 'objective',
}


def _html_cell(field: str, value: Any) -> str:
    """Renders a single table cell. Long stdout/stderr/error use <details>;
    status gets a CSS class for color-coding; numerics carry data-sort."""
    if value is None:
        return '<td></td>'
    if isinstance(value, Enum):
        value = value.value
    text = str(value)

    if field in _HTML_COLLAPSIBLE_FIELDS and len(text) > _HTML_COLLAPSIBLE_THRESHOLD:
        preview = html.escape(text[:_HTML_COLLAPSIBLE_THRESHOLD]) + '…'
        return (
            f'<td><details><summary>{preview}</summary>'
            f'<pre>{html.escape(text)}</pre></details></td>'
        )

    if field == 'status':
        cls = _HTML_STATUS_CLASS.get(text.upper())
        if cls:
            return f'<td class="{cls}">{html.escape(text)}</td>'
        return f'<td>{html.escape(text)}</td>'

    if field in _NUMERIC_FIELDS:
        try:
            num = float(text)
            if field in {'time', 'cpu_time', 'total_time', 'break_time', 'conversion_time'}:
                display = f'{num:.4f}'
            elif field.endswith('_mb') or field == 'cpu_usage_avg':
                display = f'{num:.2f}'
            else:
                display = text
            return f'<td data-sort="{num}">{html.escape(display)}</td>'
        except (ValueError, TypeError):
            pass

    return f'<td>{html.escape(text)}</td>'


def _collect_plot_links(plots_dir: str, html_path: str) -> list[tuple[str, str]]:
    """Returns a list of (title, src) where src is a relative URL from the HTML
    file to each .svg in plots_dir. Inlining was tried but matplotlib emits
    huge SVGs (the regular benchmark produced a 24 MB self-contained file that
    froze Firefox); referencing the files keeps the HTML compact and lets the
    browser load plots lazily."""
    p = Path(plots_dir)
    if not p.is_dir():
        return []
    html_dir = Path(html_path).resolve().parent
    plots: list[tuple[str, str]] = []
    for svg_path in sorted(p.glob('*.svg')):
        try:
            rel = Path(os.path.relpath(svg_path.resolve(), html_dir))
        except ValueError:
            rel = svg_path.resolve()
        plots.append((svg_path.stem, rel.as_posix()))
    return plots


def render_summary_html(summary: RunSummary) -> str:
    """HTML fragment for a RunSummary: an agreement banner, a verdict table,
    and the per-method leaderboard. Injected at the top of the full report."""
    conflicts = summary.conflicts
    if conflicts:
        banner = (
            f'<div class="banner banner-conflict">&#9888; {len(conflicts)} conflict(s): '
            f'solvers disagree on some instances (highlighted below)</div>'
        )
    else:
        banner = (
            '<div class="banner banner-ok">&#10003; No conflicts: all solvers and '
            'encodings agree on every instance</div>'
        )

    rows: list[str] = []
    for i in summary.instances:
        cls = _HTML_STATUS_CLASS.get(i.verdict, 'status-unknown')
        agree = len(i.sat_solvers) + len(i.unsat_solvers)
        solvers = ", ".join(i.sat_solvers + i.unsat_solvers)
        extra = f" (+{i.inconclusive} inconclusive)" if i.inconclusive else ""
        fastest = i.fastest_method or "-"
        ftime = f"{i.fastest_time:.3f}" if i.fastest_time is not None else "-"
        rows.append(
            f'<tr><td>{html.escape(i.problem)}</td>'
            f'<td>{html.escape(i.params_tag or "-")}</td>'
            f'<td class="{cls}">{html.escape(i.verdict)}</td>'
            f'<td>{html.escape(fastest)}</td>'
            f'<td>{ftime}</td>'
            f'<td>{agree}{html.escape(extra)}</td>'
            f'<td>{html.escape(solvers)}</td></tr>'
        )
    table = (
        '<table class="summary-table">'
        '<thead><tr><th>Problem</th><th>Parameters</th><th>Verdict</th>'
        '<th>Fastest</th><th>Time&nbsp;s</th><th>Agreeing</th><th>Solvers</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )

    leaderboard = ''
    if summary.solver_stats:
        lb_rows = ''.join(
            f'<tr><td>{html.escape(s.method)}</td><td>{s.solved}</td>'
            f'<td>{s.timeouts}</td><td>{s.errors}</td>'
            f'<td>{s.par2:.3f}</td><td>{s.median_time:.3f}</td></tr>'
            for s in summary.solver_stats
        )
        leaderboard = (
            '<h3>Leaderboard (by PAR-2, lower is better)</h3>'
            '<table class="summary-table">'
            '<thead><tr><th>Method</th><th>Solved</th><th>Timeouts</th>'
            '<th>Errors</th><th>PAR-2</th><th>Median&nbsp;s</th></tr></thead>'
            f'<tbody>{lb_rows}</tbody></table>'
        )

    return f'<section class="summary"><h2>Summary</h2>{banner}{table}{leaderboard}</section>'


def log_results_to_html(
    results: list[Result],
    output_path: str,
    fieldnames: Optional[list[str]] = None,
    plots_dir: Optional[str] = None,
    summary: Optional[RunSummary] = None,
) -> None:
    """
    Writes *results* as a self-contained HTML file at *output_path* with a
    sortable, filterable table. If *fieldnames* is given, only those columns
    appear (mirrors the CSV/JSONL filter). If *plots_dir* is given, every
    .svg file in that directory is embedded inline below the table. If
    *summary* is given, its verdict table and agreement banner are rendered
    above the raw results table.
    """
    if fieldnames is None and results:
        fieldnames = list(_flatten_result(results[0]).keys())
    elif fieldnames is None:
        fieldnames = []

    rows_html: list[str] = []
    for res in results:
        flat = _flatten_result(res)
        cells = ''.join(_html_cell(f, flat.get(f)) for f in fieldnames)
        search_parts: list[str] = []
        for f in fieldnames:
            if f in _HTML_SEARCH_SKIP_FIELDS:
                continue
            v = flat.get(f)
            if v is None:
                continue
            if isinstance(v, Enum):
                v = v.value
            search_parts.append(str(v).lower())
        search_blob = html.escape(' '.join(search_parts), quote=True)
        rows_html.append(f'<tr data-search="{search_blob}">{cells}</tr>')

    header_cells = ''.join(
        f'<th data-numeric="{1 if f in _NUMERIC_FIELDS else 0}">{html.escape(f)}</th>'
        for f in fieldnames
    )

    plots_section = ''
    if plots_dir:
        plots = _collect_plot_links(plots_dir, output_path)
        if plots:
            blocks = ''.join(
                f'<div class="plot"><h3>{html.escape(title)}</h3>'
                f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(title)}" loading="lazy"></div>'
                for title, src in plots
            )
            plots_section = f'<section class="plots"><h2>Plots</h2>{blocks}</section>'

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SAT Solver Benchmark Results</title>
<style>{_HTML_STYLE}</style>
</head>
<body>
<h1>SAT Solver Benchmark Results</h1>
<div class="meta">Generated {timestamp} · {len(results)} results</div>
{render_summary_html(summary) if summary is not None else ''}
<div class="controls">
<input id="filter" type="search" placeholder="Filter rows (matches any column)…">
<span id="row-count" class="count"></span>
</div>
<table id="results-table">
<thead><tr>{header_cells}</tr></thead>
<tbody>
{chr(10).join(rows_html)}
</tbody>
</table>
{plots_section}
<script>{_HTML_SCRIPT}</script>
</body>
</html>
"""
    with open(output_path, 'w') as out_file:
        out_file.write(doc)
