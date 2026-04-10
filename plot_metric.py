#!/usr/bin/env python3
"""
plot_metric.py — Generic post-run plotter for benchmark results.

Reads a results CSV and generates bar charts or box plots for any numeric column,
grouped by solver, formulator/solver/breaker config, or problem.

Usage:
    python3 plot_metric.py results.csv memory_peak_mb
    python3 plot_metric.py results.csv cpu_time --plot box --group-by solver
    python3 plot_metric.py results.csv conversion_time break_time time --plot bar --group-by config
    python3 plot_metric.py results.csv conflicts --per-problem --output ./plots
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def build_config_column(df: pd.DataFrame) -> pd.Series:
    return (
        df.get('formulator', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('solver', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('breaker', pd.Series('None', index=df.index)).fillna('None')
    )


def plot_bar(df: pd.DataFrame, metrics: list, group_by: str, title: str, output: Path) -> None:
    for col in metrics:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    grouped = df.groupby(group_by)[metrics].mean()
    fig, ax = plt.subplots(figsize=(max(8, len(grouped) * 1.5), 6))

    if len(metrics) == 1:
        grouped.plot(kind='bar', ax=ax, color='steelblue', legend=False)
        ax.set_ylabel(metrics[0])
    else:
        grouped.plot(kind='bar', ax=ax)
        ax.set_ylabel('Value')

    ax.set_title(title)
    ax.set_xlabel(group_by)
    plt.xticks(rotation=30, ha='right')
    plt.savefig(output, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output}")


def plot_box(df: pd.DataFrame, metrics: list, group_by: str, title: str, output: Path) -> None:
    for col in metrics:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    groups = df[group_by].unique()
    for metric in metrics:
        data = [df[df[group_by] == g][metric].dropna().values for g in groups]
        fig, ax = plt.subplots(figsize=(max(8, len(groups) * 1.5), 6))
        ax.boxplot(data, labels=list(groups))
        ax.set_title(f"{title} — {metric}")
        ax.set_xlabel(group_by)
        ax.set_ylabel(metric)
        plt.xticks(rotation=30, ha='right')
        out = output.with_name(f"{output.stem}_{metric}{output.suffix}")
        plt.savefig(out, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved: {out}")


def plot_per_problem(df: pd.DataFrame, metrics: list, group_by: str, title: str, output_dir: Path) -> None:
    if 'problem' not in df.columns:
        print("No 'problem' column in CSV — cannot split per problem.")
        return

    for col in metrics:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    for problem, group in df.groupby('problem'):
        grouped = group.groupby(group_by)[metrics].mean()
        fig, ax = plt.subplots(figsize=(max(8, len(grouped) * 1.5), 6))

        if len(metrics) == 1:
            grouped.plot(kind='bar', ax=ax, color='steelblue', legend=False)
            ax.set_ylabel(metrics[0])
        else:
            grouped.plot(kind='bar', ax=ax)
            ax.set_ylabel('Value')

        ax.set_title(f"{title} — {problem}")
        ax.set_xlabel(group_by)
        plt.xticks(rotation=30, ha='right')
        out = output_dir / f"{'_'.join(metrics)}_{problem}.png"
        plt.savefig(out, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot any numeric metric from benchmark results CSV."
    )
    parser.add_argument("csv", type=Path, help="Path to results CSV")
    parser.add_argument("metrics", nargs="+", help="Numeric column(s) to plot")
    parser.add_argument("--plot", choices=["bar", "box"], default="bar", help="Plot type (default: bar)")
    parser.add_argument("--group-by", default="config",
                        help="Column to group by: 'solver', 'config', 'formulator', etc. (default: config)")
    parser.add_argument("--per-problem", action="store_true", default=True, help="Generate one plot per problem (default: true)")
    parser.add_argument("--no-per-problem", action="store_false", dest="per_problem", help="Generate a single combined plot across all problems")
    parser.add_argument("--output", type=Path, default=Path("./plots"), help="Output directory or file path")
    parser.add_argument("--title", default=None, help="Custom plot title")

    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(args.csv)

    if args.group_by == "config":
        df['config'] = build_config_column(df)

    missing = [m for m in args.metrics if m not in df.columns]
    if missing:
        print(f"Columns not found in CSV: {missing}", file=sys.stderr)
        print(f"Available: {list(df.columns)}", file=sys.stderr)
        sys.exit(1)

    title = args.title or f"{'  /  '.join(args.metrics)} by {args.group_by}"

    if args.per_problem:
        args.output.mkdir(parents=True, exist_ok=True)
        plot_per_problem(df, args.metrics, args.group_by, title, args.output)
    elif args.plot == "box":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        out = args.output if args.output.suffix == ".png" else args.output / f"{'_'.join(args.metrics)}_box.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        plot_box(df, args.metrics, args.group_by, title, out)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        out = args.output if args.output.suffix == ".png" else args.output / f"{'_'.join(args.metrics)}_bar.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        plot_bar(df, args.metrics, args.group_by, title, out)


if __name__ == "__main__":
    main()
