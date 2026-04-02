import csv
import json
from dataclasses import asdict
from typing import List, Dict, Any
from pathlib import Path

from custom_types import Result


def _flatten_result(res: Result) -> Dict[str, Any]:
    res_dict = asdict(res) if isinstance(res, Result) else dict(res)
    if 'metrics' in res_dict:
        res_dict.update(res_dict.pop('metrics'))
    return res_dict


def log_results(results: List[Result], fieldnames: List[str], output_path: str) -> None:
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in results:
            res_dict = _flatten_result(res)
            writer.writerow({field: res_dict.get(field, "") for field in fieldnames})


def save_json(results: List[Result], output_path: str) -> None:
    structured = {}
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


def generate_plots(results: List[Result], output_dir: str) -> None:
    import pandas as pd
    import matplotlib.pyplot as plt

    if not results:
        print("No data to visualize.")
        return

    df = pd.DataFrame([_flatten_result(res) for res in results])
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for col in ('time', 'cpu_time'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df['config'] = (
        df.get('formulator', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('solver', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('breaker', pd.Series('None', index=df.index)).fillna('None')
    )

    # 1. Bar chart per problem — time per formulator/solver/breaker config
    if {'time', 'config', 'problem'}.issubset(df.columns):
        for problem, group in df.groupby('problem'):
            try:
                means = group.groupby('config')['time'].mean()
                fig, ax = plt.subplots(figsize=(max(8, len(means) * 1.5), 6))
                means.plot(kind='bar', ax=ax)
                ax.set_title(f'Mean Wall-Clock Time — {problem}')
                ax.set_xlabel('Formulator / Solver / Breaker')
                ax.set_ylabel('Time (s)')
                plt.xticks(rotation=30, ha='right')
                plt.tight_layout()
                plt.savefig(out / f'time_{problem}.png')
                plt.close()
            except Exception as e:
                print(f"Warning: could not generate time chart for {problem}: {e}")

    # 2. Stacked bar — status counts per formulator/solver/breaker config
    try:
        if {'status', 'config'}.issubset(df.columns):
            status_counts = df.groupby(['config', 'status']).size().unstack(fill_value=0)
            fig, ax = plt.subplots(figsize=(max(10, len(status_counts) * 1.5), 6))
            status_counts.plot(kind='bar', stacked=True, ax=ax)
            ax.set_title('Result Status Counts per Configuration')
            ax.set_xlabel('Formulator / Solver / Breaker')
            ax.set_ylabel('Count')
            ax.legend(title='Status')
            plt.xticks(rotation=30, ha='right')
            plt.tight_layout()
            plt.savefig(out / 'status_counts.png')
            plt.close()
    except Exception as e:
        print(f"Warning: could not generate status chart: {e}")

    # 3. Box plot — CPU time distribution per solver
    try:
        if {'cpu_time', 'solver'}.issubset(df.columns):
            solvers = df['solver'].unique()
            data = [df[df['solver'] == s]['cpu_time'].dropna().values for s in solvers]
            fig, ax = plt.subplots(figsize=(max(8, len(solvers) * 1.5), 6))
            ax.boxplot(data, labels=solvers)
            ax.set_title('CPU Time Distribution per Solver')
            ax.set_xlabel('Solver')
            ax.set_ylabel('CPU Time (s)')
            plt.xticks(rotation=30, ha='right')
            plt.tight_layout()
            plt.savefig(out / 'cpu_time_distribution.png')
            plt.close()
    except Exception as e:
        print(f"Warning: could not generate CPU time box plot: {e}")


def read_results_from_csv(csv_path: str):
    import pandas as pd
    try:
        return pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"File {csv_path} not found.")
    except pd.errors.EmptyDataError:
        print(f"File {csv_path} is empty.")
    except pd.errors.ParserError:
        print(f"Could not parse the file {csv_path}.")
    return None
