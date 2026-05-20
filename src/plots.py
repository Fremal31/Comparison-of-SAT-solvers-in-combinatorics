"""Matplotlib plot generation for benchmark results.

matplotlib and pandas are imported lazily inside generate_plots (not at module
top) on purpose: the framework runs without them installed, importing this
module must not pull in matplotlib, and the Agg backend / svg-fonttype settings
must be applied before pyplot is first imported. Do not hoist these imports.
"""

import logging
from pathlib import Path
from typing import Any, Optional, Union

from custom_types import Result
from results_io import _flatten_result

logger: logging.Logger = logging.getLogger(__name__)


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
