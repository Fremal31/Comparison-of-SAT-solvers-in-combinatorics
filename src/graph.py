import csv
import html
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import IO, Any, Callable, Optional, Union

from custom_types import (
    NULL_BREAKER,
    NULL_FORMULATOR,
    Result,
)
from run_summary import RunSummary
from utils import format_parameters_tag

logger: logging.Logger = logging.getLogger(__name__)

_SENTINELS = {NULL_FORMULATOR, NULL_BREAKER}


def _noop_append(r: Result) -> None:
    """Placeholder result-appender used until a real writer is created."""
    return None


def _flatten_result(res: Result) -> dict[str, Any]:
    """Converts a Result dataclass to a flat dict, merging the nested *metrics*
    dict into the top level so all fields are accessible by key.
    Internal sentinel values (NULL_FORMULATOR, NULL_BREAKER) are replaced with 'None' for display.
    *parameters* is rendered as the canonical 'k=v,k=v' string used elsewhere
    in the pipeline so CSV cells stay grep-friendly."""
    res_dict = asdict(res) if isinstance(res, Result) else dict(res)
    if 'metrics' in res_dict:
        res_dict.update(res_dict.pop('metrics'))
    res_dict['total_time'] = res.total_time if isinstance(res, Result) else 0.0
    for key in ('formulator', 'breaker'):
        if res_dict.get(key) in _SENTINELS:
            res_dict[key] = 'None'
    params = res_dict.get('parameters')
    if isinstance(params, dict):
        res_dict['parameters'] = format_parameters_tag(params)
    return res_dict



def create_csv_writer(fieldnames: list[str], output_path: str) -> tuple[IO[str], Callable[[Result], None]]:
    """
    Opens *output_path* for writing, writes the CSV header, and returns
    (file_handle, append_fn). Call append_fn(result) to write a single row.
    The caller is responsible for closing the file handle.
    """
    f = open(output_path, "w", newline="")  # noqa: SIM115 - caller owns and closes the handle
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    f.flush()

    def append(res: Result) -> None:
        try:
            res_dict = _flatten_result(res)
            writer.writerow({field: res_dict.get(field, "") for field in fieldnames})
            f.flush()
        except Exception as e:
            logger.warning("Failed to write CSV row: %s", e)

    return f, append


def create_jsonl_writer(
    output_path: str, fieldnames: Optional[list[str]] = None
) -> tuple[IO[str], Callable[[Result], None]]:
    """
    Opens *output_path* for writing and returns (file_handle, append_fn).
    Each result is written as a single JSON line (JSONL format) and flushed
    immediately. The caller is responsible for closing the file handle.

    If *fieldnames* is provided, only those keys appear in each JSON line
    (mirrors the CSV writer's column filter so both outputs stay symmetric
    with the user's *metrics_measured* config). None means write the full
    flattened Result.
    """
    f = open(output_path, "w")  # noqa: SIM115 - caller owns and closes the handle

    def append(res: Result) -> None:
        try:
            res_dict = _flatten_result(res)
            if fieldnames is not None:
                res_dict = {k: res_dict[k] for k in fieldnames if k in res_dict}
            f.write(json.dumps(res_dict, default=str) + "\n")
            f.flush()
        except Exception as e:
            logger.warning("Failed to write JSONL row: %s", e)

    return f, append


def create_all_writers(
    fieldnames: list[str], csv_path: str, jsonl_path: str
) -> tuple[Callable[[], None], Callable[[Result], None]]:
    """
    Creates both a CSV and JSONL writer and returns (close_fn, append_fn).
    Each call to append_fn writes one row to both files immediately.
    Call close_fn when done to close both file handles.

    If one file fails to open, the other is still closed properly.
    """
    csv_file: Optional[IO[str]] = None
    jsonl_file: Optional[IO[str]] = None
    csv_append: Callable[[Result], None] = _noop_append
    jsonl_append: Callable[[Result], None] = _noop_append

    try:
        csv_file, csv_append = create_csv_writer(fieldnames, csv_path)
    except OSError as e:
        logger.warning("Could not open CSV file %s: %s", csv_path, e)

    try:
        jsonl_file, jsonl_append = create_jsonl_writer(jsonl_path, fieldnames=fieldnames)
    except OSError as e:
        logger.warning("Could not open JSONL file %s: %s", jsonl_path, e)

    def append(res: Result) -> None:
        csv_append(res)
        jsonl_append(res)

    def close() -> None:
        if csv_file:
            csv_file.close()
        if jsonl_file:
            jsonl_file.close()

    return close, append


def log_results_to_json(results: list[Result], output_path: str) -> None:
    """
    Writes *results* to a JSON file at *output_path* structured as a nested dict
    keyed by problem → formulator → solver → breaker → parameters. The parameter
    level is always present (empty parameter dicts use the key 'none') so
    parameter sweeps don't collide on the same (problem, formulator, solver,
    breaker) tuple.

    Missing values are written as the string 'None'. Duplicate keys are overwritten
    with a warning printed to stdout.
    """
    structured: dict[str, Any] = {}
    for res in results:
        res_dict = _flatten_result(res)
        problem   = res_dict.get('problem')   or 'None'
        formulator = res_dict.get('formulator') or 'None'
        solver    = res_dict.get('solver')    or 'None'
        breaker   = res_dict.get('breaker')   or 'None'
        params    = res_dict.get('parameters') or 'none'

        target = (structured.setdefault(problem, {})
                            .setdefault(formulator, {})
                            .setdefault(solver, {})
                            .setdefault(breaker, {}))
        if params in target:
            logger.warning(
                "Duplicate result for (%s, %s, %s, %s, %s) — overwriting.",
                problem, formulator, solver, breaker, params,
            )
        target[params] = res_dict

    with open(output_path, "w") as f:
        json.dump(structured, f, indent=2, default=str)


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


def generate_plots(
    results: list[Result], output_dir: str, timeout: Optional[float] = None, suffix: str = ".svg"
) -> None:
    """
    Generates three PNG plots from *results* and saves them to *output_dir*:
    a per-problem wall-clock time bar chart, a status counts stacked bar,
    and a CPU time box plot per solver. Individual plot failures are caught
    and printed as warnings without aborting the remaining plots.

    If matplotlib and pandas are not available, logs a warning and returns without error.
    """
    try:
        import matplotlib
        import pandas as pd
        matplotlib.use(backend='Agg')  # plot generation on headless
        if suffix.lower() == 'svg' or suffix.lower() == '.svg':
            matplotlib.rcParams['svg.fonttype'] = 'none'

        import matplotlib.pyplot as plt
    except ImportError as e:
        logger.warning("Visualization skipped: '%s' is not installed.", e.name)
        return
    except Exception as e:
        logger.warning("Visualization skipped: Failed to initialize plotting backend: %s", e)
        return

    if not results:
        logger.info("No data to visualize.")
        return

    df = pd.DataFrame([_flatten_result(res) for res in results])
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for col in ('time', 'cpu_time', 'break_time', 'conversion_time'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df['config'] = (
        df.get('formulator', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('solver', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('breaker', pd.Series('None', index=df.index)).fillna('None')
    )

    PLOT_HEIGHT = 6
    PLOT_DPI = 150
    SAVE_KWARGS: dict[str, Any] = {'dpi': PLOT_DPI, 'bbox_inches': 'tight'}

    # 1. Stacked bar chart per (problem, parameters) — time breakdown per config
    if {'time', 'config', 'problem'}.issubset(df.columns):
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        group_keys = ['problem', 'parameters'] if 'parameters' in df.columns else ['problem']
        for group_vals, group in df.groupby(group_keys):
            try:
                if isinstance(group_vals, tuple):
                    problem, params_tag = group_vals[0], group_vals[1] if len(group_vals) > 1 else ''
                else:
                    problem, params_tag = group_vals, ''

                time_cols: list[str] = ['time', 'break_time', 'conversion_time']
                available: list[str] = [c for c in time_cols if c in group.columns]
                grp = group.groupby('config')[available].sum()

                grp['solve_time'] = grp['time']

                parts = ['solve_time']
                colors = ['steelblue']
                labels = ['Solve Time']

                if 'break_time' in grp.columns and grp['break_time'].sum() > 0:
                    parts.append('break_time')
                    colors.append('tomato')
                    labels.append('Break Time')

                if 'conversion_time' in grp.columns and grp['conversion_time'].sum() > 0:
                    parts.append('conversion_time')
                    colors.append('goldenrod')
                    labels.append('Conversion Time')

                plot_df = grp[parts]
                fig, ax = plt.subplots(figsize=(max(8, len(grp) * 1.5), PLOT_HEIGHT))
                plot_df.plot(kind='bar', stacked=True, ax=ax, color=colors, legend=False)
                max_bar = plot_df.sum(axis=1).max()
                show_timeout = timeout is not None and max_bar >= timeout * 0.5
                if show_timeout and timeout is not None: # mypy
                    ax.axhline(y=timeout, color='red', linestyle='--', linewidth=1)
                handles: list[Union[Patch, Line2D]] = [Patch(color=c, label=lbl) for c, lbl in zip(colors, labels)]
                if show_timeout:
                    handles.append(Line2D([0], [0], color='red', linestyle='--', linewidth=1, label='Timeout'))
                ax.legend(handles=handles)
                title = f'Total Wall-Clock Time — {problem}'
                if params_tag:
                    title += f' ({params_tag})'
                ax.set_title(title)
                ax.set_xlabel('Formulator / Solver / Breaker')
                ax.set_ylabel('Time (s)')
                plt.xticks(rotation=30, ha='right')

                safe_params = params_tag.replace('=', '').replace(',', '_') if params_tag else ''
                filename = f"time_{problem}{'_' + safe_params if safe_params else ''}{suffix}"
                plt.savefig(out / filename, **SAVE_KWARGS)

                plt.close()
            except Exception as e:
                logger.warning("Could not generate time chart for %s: %s", group_vals, e)

    # 2. Stacked bar — status counts per formulator/solver/breaker config
    try:
        if {'status', 'config'}.issubset(df.columns):
            status_counts = df.groupby(['config', 'status']).size().unstack(fill_value=0)
            fig, ax = plt.subplots(figsize=(max(10, len(status_counts) * 1.5), PLOT_HEIGHT))
            status_counts.plot(kind='bar', stacked=True, ax=ax)
            ax.set_title('Result Status Counts per Configuration')
            ax.set_xlabel('Formulator / Solver / Breaker')
            ax.set_ylabel('Count')
            ax.legend(title='Status')
            plt.xticks(rotation=30, ha='right')
            plt.savefig((out / 'status_counts').with_suffix(suffix=suffix), **SAVE_KWARGS)
            plt.close()
    except Exception as e:
        logger.warning("Could not generate status chart: %s", e)

    # 3. Box plot — CPU time distribution per solver
    try:
        if {'cpu_time', 'solver'}.issubset(df.columns):
            solvers = df['solver'].unique()
            data = [df[df['solver'] == s]['cpu_time'].dropna().values for s in solvers]
            fig, ax = plt.subplots(figsize=(max(8, len(solvers) * 1.5), PLOT_HEIGHT))
            ax.boxplot(data, label=list(solvers))
            ax.set_title('CPU Time Distribution per Solver')
            ax.set_xlabel('Solver')
            ax.set_ylabel('CPU Time (s)')
            plt.xticks(rotation=30, ha='right')
            plt.savefig((out / 'cpu_time_distribution').with_suffix(suffix=suffix), **SAVE_KWARGS)
            plt.close()
    except Exception as e:
        logger.warning("Could not generate CPU time box plot: %s", e)


def read_results_from_csv(csv_path: str) -> Any:
    """Reads a results CSV from *csv_path* and returns it as a pandas DataFrame."""
    import pandas as pd
    return pd.read_csv(csv_path)

def render_summary_html(summary: RunSummary) -> str:
    """HTML fragment for a RunSummary: an agreement banner plus a verdict
    table, designed to be injected at the top of the full results report.
    The data aggregation lives in run_summary.py; this renderer stays in
    graph.py because it reuses the report's status-colour classes."""
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
        rows.append(
            f'<tr><td>{html.escape(i.problem)}</td>'
            f'<td>{html.escape(i.params_tag or "-")}</td>'
            f'<td class="{cls}">{html.escape(i.verdict)}</td>'
            f'<td>{agree}{html.escape(extra)}</td>'
            f'<td>{html.escape(solvers)}</td></tr>'
        )
    table = (
        '<table class="summary-table">'
        '<thead><tr><th>Problem</th><th>Parameters</th><th>Verdict</th>'
        '<th>Agreeing</th><th>Solvers</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )
    return f'<section class="summary"><h2>Summary</h2>{banner}{table}</section>'