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

from custom_types import CRITICAL_STATUSES, PlotResult, Result, RunOutcome, Status
from results_io import _flatten_result
from run_summary import RunSummary

logger: logging.Logger = logging.getLogger(__name__)

_HTML_COLLAPSIBLE_FIELDS = ('stdout', 'stderr', 'error')
_HTML_COLLAPSIBLE_THRESHOLD = 80
_HTML_SEARCH_SKIP_FIELDS = frozenset({'stdout', 'stderr', 'error'})

_STATUS_OK = {Status.SAT, Status.OK}


def _build_status_class_map() -> dict[str, str]:
    """Derives the status→CSS-class map from the Status enum (single source of
    truth) so adding a Status doesn't require editing this module. 'CONFLICT'
    is added explicitly: it is a verdict produced by run_summary, not a Status."""
    m: dict[str, str] = {}
    for st in Status:
        if st in _STATUS_OK:
            m[st.value] = 'status-sat'
        elif st is Status.UNSAT:
            m[st.value] = 'status-unsat'
        elif st is Status.TIMEOUT:
            m[st.value] = 'status-timeout'
        elif st in CRITICAL_STATUSES:
            m[st.value] = 'status-error'
        else:
            m[st.value] = 'status-unknown'
    m['CONFLICT'] = 'status-error'
    return m


_HTML_STATUS_CLASS: dict[str, str] = _build_status_class_map()

_STATUS_SORT_PRIORITY: dict[str, int] = {
    'status-error': 0,
    'status-timeout': 1,
    'status-unknown': 2,
    'status-unsat': 3,
    'status-sat': 4,
}


def _status_priority(status_text: str) -> int:
    """Triage rank for a status/verdict string (lower = more attention)."""
    cls = _HTML_STATUS_CLASS.get(status_text.upper(), 'status-unknown')
    return _STATUS_SORT_PRIORITY.get(cls, 2)

_HTML_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 1.5rem; }
h1 { margin-top: 0; }
.meta { color: #666; font-size: 0.9rem; margin-bottom: 1rem; }
.controls { margin-bottom: 0.75rem; display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.controls input { padding: 0.4rem 0.6rem; font-size: 0.95rem; min-width: 280px; }
.controls .count { color: #666; font-size: 0.9rem; }
.chip { padding: 0.25rem 0.65rem; border: 1px solid #bbb; border-radius: 999px; cursor: pointer; }
.chip { background: #f5f5f5; color: inherit; font: inherit; font-size: 0.82rem; }
.chip:hover { border-color: #888; }
.chip.active { background: #0d6efd; color: #fff; border-color: #0d6efd; }
.chip .chip-count { opacity: 0.65; margin-left: 0.3rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { border: 1px solid #ccc; padding: 0.35rem 0.55rem; text-align: left; vertical-align: top; }
th { background: #f0f0f0; user-select: none; position: sticky; top: 0; white-space: nowrap; }
table.sortable th { cursor: pointer; }
table.sortable th:focus-visible { outline: 2px solid #0d6efd; outline-offset: -2px; }
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
.summary h3 { margin: 1rem 0 0.25rem; }
.run-info { color: #555; font-size: 0.95rem; margin: 0 0 0.6rem; }
.run-info .outcome-ok { color: #155724; font-weight: 600; }
.run-info .outcome-warn { color: #856404; font-weight: 600; }
.run-info .outcome-error { color: #721c24; font-weight: 600; }
.summary-table { width: auto; min-width: 40%; margin-top: 0.5rem; }
.verdict-details { margin-top: 1rem; }
.verdict-details > summary { cursor: pointer; font-size: 1.05rem; font-weight: 600; }
.verdict-details > summary:hover { color: #0d6efd; }
.verdict-details .summary-table { width: 100%; }
.summary-table tr.has-plot { cursor: pointer; }
.summary-table tr.has-plot:hover > td { background: #eef4ff; }
.summary-table .toggle { color: #888; font-size: 0.8em; }
.summary-table tr.detail-row > td { white-space: normal; max-width: none; overflow: visible; background: #fafafa; }
.summary-table tr.detail-row img { max-width: 1200px; width: 100%; height: auto; display: block; margin: 0.5rem auto; }
.banner { padding: 0.6rem 0.9rem; border-radius: 4px; font-weight: 600; margin: 0.5rem 0; }
.banner-ok { background: #d4edda; color: #155724; }
.banner-conflict { background: #f8d7da; color: #721c24; }
.conflict-list { margin: 0.25rem 0 0.75rem; padding-left: 1.4rem; font-size: 0.9rem; }
.conflict-list li { margin: 0.15rem 0; }
.conflict-list .status-sat, .conflict-list .status-unsat { padding: 0 0.25rem; border-radius: 3px; }
.plots { margin-top: 2rem; }
.plots h2 { margin-bottom: 0.5rem; }
.plot { margin: 1rem 0; padding: 0.5rem; border: 1px solid #ddd; background: #fff; }
.plot h3 { margin: 0 0 0.5rem; font-size: 1rem; color: #444; }
.plot img, .plot svg { max-width: 100%; height: auto; display: block; }
@media (prefers-color-scheme: dark) {
  body { background: #1e1e1e; color: #e0e0e0; }
  th { background: #2d2d2d; }
  tbody tr:nth-child(even) { background: #252525; }
  td details pre { background: #2a2a2a; }
  .plot { background: #2a2a2a; border-color: #444; }
  .meta, .controls .count { color: #aaa; }
  .chip { background: #2d2d2d; border-color: #555; }
  .chip:hover { border-color: #888; }
  .chip.active { background: #0d6efd; border-color: #0d6efd; }
  .summary-table tr.has-plot:hover > td { background: #2a3a4a; }
  .summary-table tr.detail-row > td { background: #252525; }
  .run-info { color: #aaa; }
  .run-info .outcome-ok { color: #4ade80; }
  .run-info .outcome-warn { color: #fbbf24; }
  .run-info .outcome-error { color: #f87171; }
}
"""

_HTML_SCRIPT = """
(function() {
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

  // Make any table.sortable click-to-sort. Rows are reattached via a single
  // DocumentFragment so sorting thousands of rows is one reflow, not one per row.
  function makeSortable(table) {
    const tbody = table.tBodies[0];
    if (!tbody || !table.tHead) return null;
    const headers = Array.from(table.tHead.rows[0].cells);
    let sortCol = -1, sortDir = 1;
    function sortBy(i, dir) {
      const numeric = headers[i].dataset.numeric === '1';
      // Pair each data row with the detail row that follows it (the inline plot)
      // so they move together and sorting never orphans a plot from its row.
      const pairs = [];
      let cur = null;
      for (const r of Array.from(tbody.rows)) {
        if (r.classList.contains('detail-row')) { if (cur) cur.detail = r; }
        else { cur = { row: r, detail: null }; pairs.push(cur); }
      }
      pairs.sort((a, b) => dir * compare(a.row, b.row, i, numeric));
      const frag = document.createDocumentFragment();
      for (const p of pairs) { frag.appendChild(p.row); if (p.detail) frag.appendChild(p.detail); }
      tbody.appendChild(frag);
      headers.forEach(h => h.classList.remove('sorted-asc', 'sorted-desc'));
      headers[i].classList.add(dir === 1 ? 'sorted-asc' : 'sorted-desc');
      sortCol = i; sortDir = dir;
    }
    headers.forEach((th, i) => {
      th.tabIndex = 0;
      th.setAttribute('role', 'button');
      const run = () => sortBy(i, sortCol === i ? -sortDir : 1);
      th.addEventListener('click', run);
      th.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); }
      });
    });
    return sortBy;
  }

  const resultsTable = document.getElementById('results-table');
  let statusIdx = -1;
  if (resultsTable && resultsTable.tHead) {
    statusIdx = Array.from(resultsTable.tHead.rows[0].cells)
      .findIndex(h => h.dataset.field === 'status');
  }
  document.querySelectorAll('table.sortable').forEach(t => {
    const sortBy = makeSortable(t);
    // Default the results table to status order so conflicts/errors/timeouts
    // sit at the top on load.
    if (sortBy && t === resultsTable && statusIdx >= 0) sortBy(statusIdx, 1);
  });

  // Expandable verdict rows: clicking a row with an inline plot toggles the
  // detail row that follows it.
  document.querySelectorAll('tr.has-plot').forEach(row => {
    row.addEventListener('click', () => {
      const detail = row.nextElementSibling;
      if (!detail || !detail.classList.contains('detail-row')) return;
      detail.classList.toggle('hidden');
      const tg = row.querySelector('.toggle');
      if (tg) tg.textContent = detail.classList.contains('hidden') ? '\\u25B8' : '\\u25BE';
    });
  });

  if (!resultsTable) return;
  const tbody = resultsTable.tBodies[0];
  const rows = Array.from(tbody.rows);
  const total = rows.length;
  const filterInput = document.getElementById('filter');
  const countLabel = document.getElementById('row-count');
  const chips = Array.from(document.querySelectorAll('.chip'));
  const activeStatuses = new Set();
  let query = '';

  function updateCount(visible) {
    countLabel.textContent = visible === total
      ? `${total} rows`
      : `${visible} of ${total} rows`;
  }
  function apply() {
    let visible = 0;
    for (const row of rows) {
      const textOk = !query || row.dataset.search.includes(query);
      const statusOk = activeStatuses.size === 0 || activeStatuses.has(row.dataset.status);
      const show = textOk && statusOk;
      if (row.classList.contains('hidden') === show) row.classList.toggle('hidden', !show);
      if (show) visible++;
    }
    updateCount(visible);
  }

  let filterTimer = null;
  filterInput.addEventListener('input', function() {
    query = this.value.toLowerCase();
    clearTimeout(filterTimer);
    filterTimer = setTimeout(apply, 120);
  });
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const s = chip.dataset.status;
      if (activeStatuses.has(s)) { activeStatuses.delete(s); chip.classList.remove('active'); }
      else { activeStatuses.add(s); chip.classList.add('active'); }
      apply();
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
        prio = _status_priority(text)
        cls_attr = f' class="{cls}"' if cls else ''
        return f'<td{cls_attr} data-sort="{prio}">{html.escape(text)}</td>'

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


# How a run ended -> (display label, CSS class).
_OUTCOME_DISPLAY = {
    RunOutcome.COMPLETED: ('Completed', 'outcome-ok'),
    RunOutcome.INTERRUPTED: ('Interrupted — partial results', 'outcome-warn'),
    RunOutcome.ERROR: ('Aborted after an error — partial results', 'outcome-error'),
}


def _format_duration(seconds: float) -> str:
    """Human-readable wall-clock duration: '1h 02m 03s', '2m 03s', or '3.4s'."""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}h {m:02d}m {s:02d}s'
    if m:
        return f'{m}m {s:02d}s'
    return f'{seconds:.1f}s'


def _rel_to_html(target: str, html_path: str) -> str:
    """Relative URL from the HTML file to *target* (a plot file). Plots are
    referenced rather than inlined: matplotlib emits huge SVGs (the regular
    benchmark produced a 24 MB self-contained file that froze Firefox), so
    referencing keeps the HTML compact and lets the browser load plots lazily.
    The plot set comes from PlotResult (what this run wrote), not a directory
    glob, so stale plots from earlier runs are never picked up."""
    html_dir = Path(html_path).resolve().parent
    try:
        return Path(os.path.relpath(Path(target).resolve(), html_dir)).as_posix()
    except ValueError:  # e.g. different drive on Windows
        return Path(target).resolve().as_posix()


def render_summary_html(
    summary: RunSummary,
    per_problem_plots: Optional[dict[tuple[str, str], str]] = None,
    total_time: Optional[float] = None,
    outcome: Optional[RunOutcome] = None,
) -> str:
    """HTML fragment for a RunSummary, ordered for a glance: an agreement banner
    (the correctness gate), then the per-method PAR-2 leaderboard (the headline
    result), then the per-instance verdict table in a <details> that defaults
    open only when small or when a conflict needs attention — so a 200+ instance
    run doesn't bury the leaderboard. Injected at the top of the full report."""
    conflicts = summary.conflicts
    if conflicts:
        items = ''.join(
            f'<li><strong>{html.escape(c.problem)}</strong>'
            f'{html.escape(f" ({c.params_tag})") if c.params_tag else ""}: '
            f'<span class="status-sat">SAT</span> by {html.escape(", ".join(c.sat_solvers))}; '
            f'<span class="status-unsat">UNSAT</span> by {html.escape(", ".join(c.unsat_solvers))}</li>'
            for c in conflicts
        )
        banner = (
            f'<div class="banner banner-conflict">&#9888; {len(conflicts)} conflict(s): '
            f'solvers disagree on the instance(s) below</div>'
            f'<ul class="conflict-list">{items}</ul>'
        )
    else:
        banner = (
            '<div class="banner banner-ok">&#10003; No conflicts: all solvers and '
            'encodings agree on every instance</div>'
        )

    info_parts: list[str] = []
    if outcome:
        fallback = (outcome.value if hasattr(outcome, 'value') else str(outcome), 'outcome-ok')
        label, cls = _OUTCOME_DISPLAY.get(outcome, fallback)
        info_parts.append(f'<span class="{cls}">{html.escape(label)}</span>')
    if total_time is not None:
        info_parts.append(f'Finished in {_format_duration(total_time)}')
    run_info = f'<div class="run-info">{" · ".join(info_parts)}</div>' if info_parts else ''

    rows: list[str] = []
    for i in summary.instances:
        cls = _HTML_STATUS_CLASS.get(i.verdict, 'status-unknown')
        prio = _status_priority(i.verdict)
        n_sat = len(i.sat_solvers)
        n_unsat = len(i.unsat_solvers)
        agree = n_sat + n_unsat
        total = agree + i.inconclusive
        extra = f" ({i.inconclusive} inconclusive)" if i.inconclusive else ""
        # On a CONFLICT the definitive runs split across verdicts, so "N agree"
        # would be a lie — show the SAT/UNSAT breakdown instead.
        agree_body = f"{n_sat} SAT / {n_unsat} UNSAT" if i.verdict == "CONFLICT" else f"{agree}/{total}"
        fastest = i.fastest_method or "-"
        ftime = f"{i.fastest_time:.3f}" if i.fastest_time is not None else "-"
        ftime_sort = i.fastest_time if i.fastest_time is not None else ''

        plot_src = per_problem_plots.get((i.problem, i.params_tag)) if per_problem_plots else None
        toggle = '<span class="toggle">&#9656;</span> ' if plot_src else ''
        row_cls = ' class="has-plot"' if plot_src else ''
        rows.append(
            f'<tr{row_cls}><td>{toggle}{html.escape(i.problem)}</td>'
            f'<td>{html.escape(i.params_tag or "-")}</td>'
            f'<td class="{cls}" data-sort="{prio}">{html.escape(i.verdict)}</td>'
            f'<td>{html.escape(fastest)}</td>'
            f'<td data-sort="{ftime_sort}">{ftime}</td>'
            f'<td data-sort="{agree}">{html.escape(agree_body + extra)}</td></tr>'
        )
        if plot_src:
            rows.append(
                f'<tr class="detail-row hidden"><td colspan="6">'
                f'<img loading="lazy" src="{html.escape(plot_src, quote=True)}" '
                f'alt="Time breakdown — {html.escape(i.problem)}"></td></tr>'
            )
    table = (
        '<table class="summary-table sortable">'
        '<thead><tr><th>Problem</th><th>Parameters</th><th data-numeric="1">Verdict</th>'
        '<th>Fastest</th><th data-numeric="1">Time&nbsp;s</th>'
        '<th data-numeric="1">Agreeing&nbsp;/&nbsp;runs</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )
    # Collapse the per-instance table by default on large runs so it doesn't
    # push the leaderboard off-screen; keep it open when small or when there is
    # a conflict the reader should actually look at.
    n_inst = len(summary.instances)
    n_conf = len(conflicts)
    open_attr = ' open' if (conflicts or n_inst <= 12) else ''
    label = f'Per-instance verdicts ({n_inst} instance{"" if n_inst == 1 else "s"}'
    label += f', {n_conf} conflict{"" if n_conf == 1 else "s"})' if conflicts else ')'
    verdict_section = (
        f'<details class="verdict-details"{open_attr}>'
        f'<summary>{html.escape(label)}</summary>{table}</details>'
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
            '<table class="summary-table sortable">'
            '<thead><tr><th>Method</th><th data-numeric="1">Solved</th>'
            '<th data-numeric="1">Timeouts</th><th data-numeric="1">Errors</th>'
            '<th data-numeric="1">PAR-2</th>'
            '<th data-numeric="1">Median&nbsp;s<br><small>(solved only)</small></th></tr></thead>'
            f'<tbody>{lb_rows}</tbody></table>'
        )

    return (
        f'<section class="summary"><h2>Summary</h2>{run_info}{banner}'
        f'{leaderboard}{verdict_section}</section>'
    )


def log_results_to_html(
    results: list[Result],
    output_path: str,
    fieldnames: Optional[list[str]] = None,
    plots: Optional[PlotResult] = None,
    summary: Optional[RunSummary] = None,
    total_time: Optional[float] = None,
    outcome: Optional[RunOutcome] = None,
) -> None:
    """
    Writes *results* as a self-contained HTML file at *output_path* with a
    sortable, filterable table. If *fieldnames* is given, only those columns
    appear (mirrors the CSV/JSONL filter). If *plots* is given, its comparison
    charts are linked in a Plots section below the table, and its per-problem
    charts are embedded as expandable rows in the verdict table. If *summary*
    is given, its verdict table and agreement banner are rendered above the raw
    results table. *total_time* (wall-clock seconds) and *outcome* (how the run
    ended) are shown as a run-info line at the top of the summary. When the
    results carry a 'status' column the table loads sorted by status (failures
    first) and gains per-status filter chips.
    """
    if fieldnames is None and results:
        fieldnames = list(_flatten_result(results[0]).keys())
    elif fieldnames is None:
        fieldnames = []

    rows_html: list[str] = []
    status_counts: dict[str, int] = {}
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

        raw_status = flat.get('status')
        if isinstance(raw_status, Enum):
            raw_status = raw_status.value
        status_key = str(raw_status).upper() if raw_status is not None else ''
        if status_key:
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
        status_attr = f' data-status="{html.escape(status_key, quote=True)}"' if status_key else ''
        rows_html.append(f'<tr data-search="{search_blob}"{status_attr}>{cells}</tr>')

    header_cells = ''.join(
        f'<th data-field="{html.escape(f, quote=True)}" '
        f'data-numeric="{1 if (f in _NUMERIC_FIELDS or f == "status") else 0}">{html.escape(f)}</th>'
        for f in fieldnames
    )

    chips_html = ''
    if status_counts:
        ordered = sorted(status_counts, key=lambda s: (_status_priority(s), s))
        buttons = ''.join(
            f'<button type="button" class="chip" data-status="{html.escape(s, quote=True)}">'
            f'{html.escape(s)}<span class="chip-count">{status_counts[s]}</span></button>'
            for s in ordered
        )
        chips_html = f'<div class="controls chips">{buttons}</div>'

    # Per-problem charts are embedded in the verdict table (keyed by instance);
    # the cross-solver comparison charts go in the Plots section below.
    per_problem_rel: Optional[dict[tuple[str, str], str]] = None
    if plots is not None and plots.per_problem:
        per_problem_rel = {k: _rel_to_html(v, output_path) for k, v in plots.per_problem.items()}

    plots_section = ''
    if plots is not None and plots.comparison:
        blocks = ''.join(
            f'<div class="plot"><h3>{html.escape(Path(p).stem)}</h3>'
            f'<img src="{html.escape(_rel_to_html(p, output_path), quote=True)}" '
            f'alt="{html.escape(Path(p).stem)}" loading="lazy"></div>'
            for p in plots.comparison
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
{render_summary_html(summary, per_problem_rel, total_time, outcome) if summary is not None else ''}
{plots_section}
<div class="controls">
<input id="filter" type="search" placeholder="Filter rows (matches any column)…">
<span id="row-count" class="count"></span>
</div>
{chips_html}
<table id="results-table" class="sortable">
<thead><tr>{header_cells}</tr></thead>
<tbody>
{chr(10).join(rows_html)}
</tbody>
</table>
<script>{_HTML_SCRIPT}</script>
</body>
</html>
"""
    with open(output_path, 'w') as out_file:
        out_file.write(doc)
