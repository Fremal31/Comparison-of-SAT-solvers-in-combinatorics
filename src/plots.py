"""Matplotlib plot generation for benchmark results.

matplotlib and pandas are imported lazily inside generate_plots (not at module
top) on purpose: the framework runs without them installed, importing this
module must not pull in matplotlib, and the Agg backend / svg-fonttype settings
must be applied before pyplot is first imported. Do not hoist these imports.

Plots are grouped into toggleable *classes* (mirrored by VisualizationConfig):
  - per_problem : one time-breakdown bar chart per instance (parent_problem,
                  parameters), embedded as expandable rows in the HTML report
  - comparison  : cross-solver charts — status counts, CPU-time box plot, and
                  the cactus/survival plot (instances solved vs time)
A per_solver class is intentionally absent: there is no per-solver plot today,
so adding the helper and its toggle together is left for when one is needed.
"""

import logging
from pathlib import Path
from typing import Any, Optional, Union

from custom_types import PlotResult, Result, Status
from results_io import _flatten_result

logger: logging.Logger = logging.getLogger(__name__)

PLOT_HEIGHT = 6
PLOT_WIDTH = 11
PLOT_DPI = 150
_SOLVED = (Status.SAT.value, Status.UNSAT.value)


def _hbar_height(n: int) -> float:
    """Figure height (inches) for a horizontal bar/box chart with *n* rows.
    Horizontal layout means the chart grows downward with the number of configs
    instead of sideways, so long 'formulator / solver / breaker' labels stay
    readable and the figure never gets squished when fit to the page width."""
    return min(max(2.5, 0.5 * n + 1.6), 40)


def _plot_per_problem(df: Any, out: Path, suffix: str, save_kwargs: dict[str, Any],
                      timeout: Optional[float], plt: Any) -> dict[tuple[str, str], str]:
    """Stacked bar of the wall-clock time breakdown (solve / break / conversion)
    across configs, one figure per instance (parent_problem, parameters) — so
    every encoding of an instance is compared in a single chart, and the key
    lines up with the verdict table. Returns {(instance, params_tag): path} for
    the charts written."""
    written: dict[tuple[str, str], str] = {}
    if not {'time', 'config', 'instance'}.issubset(df.columns):
        return written
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    group_keys = ['instance', 'parameters'] if 'parameters' in df.columns else ['instance']
    for group_vals, group in df.groupby(group_keys):
        try:
            if isinstance(group_vals, tuple):
                instance, params_tag = group_vals[0], group_vals[1] if len(group_vals) > 1 else ''
            else:
                instance, params_tag = group_vals, ''

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
            fig, ax = plt.subplots(figsize=(PLOT_WIDTH, _hbar_height(len(grp))))
            plot_df.plot(kind='barh', stacked=True, ax=ax, color=colors, legend=False)
            max_bar = plot_df.sum(axis=1).max()
            show_timeout = timeout is not None and max_bar >= timeout * 0.5
            if show_timeout and timeout is not None:  # mypy
                ax.axvline(x=timeout, color='red', linestyle='--', linewidth=1)
            handles: list[Union[Patch, Line2D]] = [Patch(color=c, label=lbl) for c, lbl in zip(colors, labels)]
            if show_timeout:
                handles.append(Line2D([0], [0], color='red', linestyle='--', linewidth=1, label='Timeout'))
            ax.legend(handles=handles)
            title = f'Total Wall-Clock Time — {instance}'
            if params_tag:
                title += f' ({params_tag})'
            ax.set_title(title)
            ax.set_xlabel('Time (s)')
            ax.set_ylabel('Formulator / Solver / Breaker')

            safe_params = str(params_tag).replace('=', '').replace(',', '_') if params_tag else ''
            filename = f"time_{instance}{'_' + safe_params if safe_params else ''}{suffix}"
            plt.savefig(out / filename, **save_kwargs)
            plt.close()
            written[(str(instance), str(params_tag) if params_tag else '')] = str(out / filename)
        except Exception as e:
            logger.warning("Could not generate time chart for %s: %s", group_vals, e)
    return written


def _plot_status_counts(df: Any, out: Path, suffix: str, save_kwargs: dict[str, Any], plt: Any) -> Optional[str]:
    """Stacked bar of result-status counts per formulator/solver/breaker config."""
    try:
        if {'status', 'config'}.issubset(df.columns):
            status_counts = df.groupby(['config', 'status']).size().unstack(fill_value=0)
            fig, ax = plt.subplots(figsize=(PLOT_WIDTH, _hbar_height(len(status_counts))))
            status_counts.plot(kind='barh', stacked=True, ax=ax)
            ax.set_title('Result Status Counts per Configuration')
            ax.set_xlabel('Count')
            ax.set_ylabel('Formulator / Solver / Breaker')
            ax.legend(title='Status')
            path = (out / 'status_counts').with_suffix(suffix=suffix)
            plt.savefig(path, **save_kwargs)
            plt.close()
            return str(path)
    except Exception as e:
        logger.warning("Could not generate status chart: %s", e)
    return None


def _plot_cpu_box(df: Any, out: Path, suffix: str, save_kwargs: dict[str, Any], plt: Any) -> Optional[str]:
    """Box plot of CPU-time distribution per solver, over solved runs only.
    Timeouts are censored at the cap and errors sit near zero.n."""
    try:
        if not {'cpu_time', 'solver'}.issubset(df.columns):
            return None
        has_status = 'status' in df.columns
        src = df[df['status'].isin(_SOLVED)] if has_status else df
        labels: list[str] = []
        data: list[Any] = []
        for s in df['solver'].unique():
            vals = src[src['solver'] == s]['cpu_time'].dropna().to_numpy()
            if not len(vals):
                continue
            total = int((df['solver'] == s).sum())
            labels.append(f"{s} ({len(vals)}/{total} solved)" if has_status else str(s))
            data.append(vals)
        if not data:
            logger.info("CPU time box plot skipped: no solved runs.")
            return None
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH, _hbar_height(len(data))))
        ax.boxplot(data, orientation='horizontal', tick_labels=labels)
        ax.set_title('CPU Time Distribution per Solver (solved runs)')
        ax.set_xlabel('CPU Time (s)')
        ax.set_ylabel('Solver')
        path = (out / 'cpu_time_distribution').with_suffix(suffix=suffix)
        plt.savefig(path, **save_kwargs)
        plt.close()
        return str(path)
    except Exception as e:
        logger.warning("Could not generate CPU time box plot: %s", e)
    return None


def _plot_cactus(df: Any, out: Path, suffix: str, save_kwargs: dict[str, Any],
                 timeout: Optional[float], plt: Any) -> Optional[str]:
    """Cactus / survival plot: for each method (formulator/solver/breaker) the
    solved runs are sorted ascending by solve time, then plotted as count
    solved (x) vs time (y). The line reaching furthest right solved the most
    instances; a flatter line is faster. The SAT-competition comparison view."""
    try:
        if not {'time', 'config', 'status'}.issubset(df.columns):
            return None
        solved = df[df['status'].isin(_SOLVED)].copy()
        solved = solved.dropna(subset=['time'])
        if solved.empty:
            logger.info("Cactus plot skipped: no solved instances.")
            return None

        fig, ax = plt.subplots(figsize=(10, PLOT_HEIGHT))
        plotted = False
        for method, group in solved.groupby('config'):
            times = group['time'].sort_values().to_numpy()
            if len(times) == 0:
                continue
            ax.plot(range(1, len(times) + 1), times, marker='.', markersize=4,
                    linewidth=1.2, label=str(method))
            plotted = True
        if not plotted:
            plt.close()
            return None

        if timeout is not None:
            ax.axhline(y=timeout, color='red', linestyle='--', linewidth=1, label='Timeout')
        ax.set_title('Cactus Plot — Instances Solved vs Time')
        ax.set_xlabel('Instances solved')
        ax.set_ylabel('Solve time (s)')
        ax.margins(x=0.01)
        # Legend outside the axes (to the right) so it never covers the curves;
        # bbox_inches='tight' on save expands the canvas to fit it.
        ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize='small',
                  title='Formulator / Solver / Breaker', borderaxespad=0)
        path = (out / 'cactus').with_suffix(suffix=suffix)
        plt.savefig(path, **save_kwargs)
        plt.close()
        return str(path)
    except Exception as e:
        logger.warning("Could not generate cactus plot: %s", e)
    return None


def generate_plots(
    results: list[Result], output_dir: str, timeout: Optional[float] = None, suffix: str = ".svg",
    per_problem: bool = True, comparison: bool = True,
) -> PlotResult:
    """
    Generates plots from *results* into *output_dir* (default SVG). Which plot
    classes run is controlled by *per_problem* and *comparison*:

      per_problem — one time-breakdown bar chart per instance (parent_problem,
                    parameters), keyed to match the verdict table
      comparison  — status counts, CPU-time box plot, and cactus/survival plot

    Both default to True (the historical "all plots" behaviour). Returns a
    PlotResult listing exactly the files written so the HTML embeds this run's
    plots rather than globbing the directory. Individual plot failures are
    caught and logged without aborting the rest. If matplotlib and pandas are
    not available, logs a warning and returns an empty PlotResult.
    """
    result = PlotResult()
    if not (per_problem or comparison):
        logger.info("Visualization: all plot classes disabled, nothing to do.")
        return result

    try:
        import matplotlib
        import pandas as pd
        matplotlib.use(backend='Agg')  # plot generation on headless
        if suffix.lower() == 'svg' or suffix.lower() == '.svg':
            matplotlib.rcParams['svg.fonttype'] = 'none'

        matplotlib.rcParams.update({
            'font.size': 12, 'axes.titlesize': 15, 'axes.labelsize': 13,
            'xtick.labelsize': 11, 'ytick.labelsize': 11, 'legend.fontsize': 10,
        })

        import matplotlib.pyplot as plt
    except ImportError as e:
        logger.warning("Visualization skipped: '%s' is not installed.", e.name)
        return result
    except Exception as e:
        logger.warning("Visualization skipped: Failed to initialize plotting backend: %s", e)
        return result

    if not results:
        logger.info("No data to visualize.")
        return result

    df = pd.DataFrame([_flatten_result(res) for res in results])
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for col in ('time', 'cpu_time', 'break_time', 'conversion_time'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'status' in df.columns:
        df['status'] = df['status'].map(lambda s: s.value if hasattr(s, 'value') else s)

    df['config'] = (
        df.get('formulator', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('solver', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('breaker', pd.Series('None', index=df.index)).fillna('None')
    )

    if 'problem' in df.columns:
        prob = df['problem']
    elif 'parent_problem' in df.columns:
        prob = df['parent_problem']
    else:
        prob = None
    if 'parent_problem' in df.columns and prob is not None:
        parent = df['parent_problem']
        df['instance'] = parent.where(parent.notna() & (parent.astype(str).str.strip() != ''), prob)
    elif prob is not None:
        df['instance'] = prob

    save_kwargs: dict[str, Any] = {'dpi': PLOT_DPI, 'bbox_inches': 'tight'}

    if per_problem:
        result.per_problem = _plot_per_problem(df, out, suffix, save_kwargs, timeout, plt)

    if comparison:
        for path in (
            _plot_status_counts(df, out, suffix, save_kwargs, plt),
            _plot_cpu_box(df, out, suffix, save_kwargs, plt),
            _plot_cactus(df, out, suffix, save_kwargs, timeout, plt),
        ):
            if path:
                result.comparison.append(path)

    return result
