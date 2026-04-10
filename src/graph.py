import csv
import json
from dataclasses import asdict
from typing import List, Dict, Any, Tuple, Callable, IO, Optional, Union
from pathlib import Path

from custom_types import Result, STATUS_SAT, STATUS_UNSAT, NULL_FORMULATOR


def _flatten_result(res: Result) -> Dict[str, Any]:
    """Converts a Result dataclass to a flat dict, merging the nested *metrics*
    dict into the top level so all fields are accessible by key."""
    res_dict = asdict(res) if isinstance(res, Result) else dict(res)
    if 'metrics' in res_dict:
        res_dict.update(res_dict.pop('metrics'))
    res_dict['total_time'] = res.total_time if isinstance(res, Result) else 0.0
    return res_dict



def create_csv_writer(fieldnames: List[str], output_path: str) -> Tuple[IO[str], Callable[[Result], None]]:
    """
    Opens *output_path* for writing, writes the CSV header, and returns
    (file_handle, append_fn). Call append_fn(result) to write a single row.
    The caller is responsible for closing the file handle.
    """
    f = open(output_path, "w", newline="")
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    f.flush()

    def append(res: Result) -> None:
        try:
            res_dict = _flatten_result(res)
            writer.writerow({field: res_dict.get(field, "") for field in fieldnames})
            f.flush()
        except Exception as e:
            print(f"Warning: failed to write CSV row: {e}")

    return f, append


def create_jsonl_writer(output_path: str) -> Tuple[IO[str], Callable[[Result], None]]:
    """
    Opens *output_path* for writing and returns (file_handle, append_fn).
    Each result is written as a single JSON line (JSONL format) and flushed
    immediately. The caller is responsible for closing the file handle.
    """
    f = open(output_path, "w")

    def append(res: Result) -> None:
        try:
            res_dict = _flatten_result(res)
            f.write(json.dumps(res_dict, default=str) + "\n")
            f.flush()
        except Exception as e:
            print(f"Warning: failed to write JSONL row: {e}")

    return f, append


def create_all_writers(fieldnames: List[str], csv_path: str, jsonl_path: str) -> Tuple[Callable[[], None], Callable[[Result], None]]:
    """
    Creates both a CSV and JSONL writer and returns (close_fn, append_fn).
    Each call to append_fn writes one row to both files immediately.
    Call close_fn when done to close both file handles.

    If one file fails to open, the other is still closed properly.
    """
    csv_file: Optional[IO[str]] = None
    jsonl_file: Optional[IO[str]] = None
    csv_append: Callable[[Result], None] = lambda r: None
    jsonl_append: Callable[[Result], None] = lambda r: None

    try:
        csv_file, csv_append = create_csv_writer(fieldnames, csv_path)
    except OSError as e:
        print(f"Warning: could not open CSV file {csv_path}: {e}")

    try:
        jsonl_file, jsonl_append = create_jsonl_writer(jsonl_path)
    except OSError as e:
        print(f"Warning: could not open JSONL file {jsonl_path}: {e}")

    def append(res: Result) -> None:
        csv_append(res)
        jsonl_append(res)

    def close() -> None:
        if csv_file:
            csv_file.close()
        if jsonl_file:
            jsonl_file.close()

    return close, append


def log_results_to_json(results: List[Result], output_path: str) -> None:
    """
    Writes *results* to a JSON file at *output_path* structured as a nested dict
    keyed by problem → formulator → solver → breaker.

    Missing values are written as the string 'None'. Duplicate keys are overwritten
    with a warning printed to stdout.
    """
    structured: Dict[str, Any] = {}
    for res in results:
        res_dict = _flatten_result(res)
        problem   = res_dict.get('problem')   or 'None'
        formulator = res_dict.get('formulator') or 'None'
        solver    = res_dict.get('solver')    or 'None'
        breaker   = res_dict.get('breaker')   or 'None'

        target = structured.setdefault(problem, {}).setdefault(formulator, {}).setdefault(solver, {})
        if breaker in target:
            print(f"Warning: duplicate result for ({problem}, {formulator}, {solver}, {breaker}) — overwriting.")
        target[breaker] = res_dict

    with open(output_path, "w") as f:
        json.dump(structured, f, indent=2, default=str)


def generate_plots(results: List[Result], output_dir: str, timeout: Optional[float] = None) -> None:
    """
    Generates three PNG plots from *results* and saves them to *output_dir*:
    a per-problem wall-clock time bar chart, a status counts stacked bar,
    and a CPU time box plot per solver. Individual plot failures are caught
    and printed as warnings without aborting the remaining plots.
    """
    import pandas as pd
    import matplotlib.pyplot as plt

    if not results:
        print("No data to visualize.")
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
    SAVE_KWARGS: Dict[str, Any] = dict(dpi=PLOT_DPI, bbox_inches='tight')

    # 1. Stacked bar chart per problem — time breakdown per config
    if {'time', 'config', 'problem'}.issubset(df.columns):
        for problem, group in df.groupby('problem'):
            try:
                time_cols: List[str] = ['time', 'break_time', 'conversion_time']
                available: List[str] = [c for c in time_cols if c in group.columns]
                grp = group.groupby('config')[available].mean()

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
                if show_timeout:
                    if timeout is not None: # mypy
                        ax.axhline(y=timeout, color='red', linestyle='--', linewidth=1)
                from matplotlib.patches import Patch
                from matplotlib.lines import Line2D
                handles: List[Union[Patch, Line2D]] = [Patch(color=c, label=l) for c, l in zip(colors, labels)]
                if show_timeout:
                    handles.append(Line2D([0], [0], color='red', linestyle='--', linewidth=1, label='Timeout'))
                ax.legend(handles=handles)
                ax.set_title(f'Mean Wall-Clock Time — {problem}')
                ax.set_xlabel('Formulator / Solver / Breaker')
                ax.set_ylabel('Time (s)')
                plt.xticks(rotation=30, ha='right')
                plt.savefig(out / f'time_{problem}.png', **SAVE_KWARGS)
                plt.close()
            except Exception as e:
                print(f"Warning: could not generate time chart for {problem}: {e}")

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
            plt.savefig(out / 'status_counts.png', **SAVE_KWARGS)
            plt.close()
    except Exception as e:
        print(f"Warning: could not generate status chart: {e}")

    # 3. Box plot — CPU time distribution per solver
    try:
        if {'cpu_time', 'solver'}.issubset(df.columns):
            solvers = df['solver'].unique()
            data = [df[df['solver'] == s]['cpu_time'].dropna().values for s in solvers]
            fig, ax = plt.subplots(figsize=(max(8, len(solvers) * 1.5), PLOT_HEIGHT))
            ax.boxplot(data, labels=list(solvers))
            ax.set_title('CPU Time Distribution per Solver')
            ax.set_xlabel('Solver')
            ax.set_ylabel('CPU Time (s)')
            plt.xticks(rotation=30, ha='right')
            plt.savefig(out / 'cpu_time_distribution.png', **SAVE_KWARGS)
            plt.close()
    except Exception as e:
        print(f"Warning: could not generate CPU time box plot: {e}")


def read_results_from_csv(csv_path: str) -> Any:
    """Reads a results CSV from *csv_path* and returns it as a pandas DataFrame."""
    import pandas as pd
    return pd.read_csv(csv_path)

def validate_status(results: List[Result]) -> List[str]:
    DEFINITIVE_STATUSES = {STATUS_SAT, STATUS_UNSAT}

    groups: Dict[Tuple[str, str], Dict[str, set]] = {}
    for result in results:
        if result.status not in DEFINITIVE_STATUSES:
            continue
        key = (result.problem, result.formulator)
        if key not in groups:
            groups[key] = {STATUS_SAT: set(), STATUS_UNSAT: set()}
        groups[key][result.status].add(result.solver)

    warnings: List[str] = []
    for (problem, formulator), status_dict in sorted(groups.items()):
        sat_set = status_dict.get(STATUS_SAT, set())
        unsat_set = status_dict.get(STATUS_UNSAT, set())
        if sat_set and unsat_set:
            sat = ", ".join(sorted(status_dict.get(STATUS_SAT, set())))
            unsat = ", ".join(sorted(status_dict.get(STATUS_UNSAT, set())))

            warnings.append(f"CONFLICT on {problem} {formulator}: {STATUS_SAT} by [{sat}], {STATUS_UNSAT} by [{unsat}]")

    return warnings