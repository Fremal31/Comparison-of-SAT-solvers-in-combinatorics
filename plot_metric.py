#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import pandas as pd

def setup_matplotlib(fmt: str):
    """Setup headless backend and SVG settings."""
    try:
        import matplotlib
        matplotlib.use('Agg')  # Headless support
        if fmt.lower() == 'svg':
            matplotlib.rcParams['svg.fonttype'] = 'none'  # Editable text in SVGs
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        print("Error: matplotlib is required to run this script.", file=sys.stderr)
        sys.exit(1)

def build_config_column(df: pd.DataFrame) -> pd.Series:
    return (
        df.get('formulator', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('solver', pd.Series('None', index=df.index)).fillna('None') + ' / ' +
        df.get('breaker', pd.Series('None', index=df.index)).fillna('None')
    )

def plot_bar(plt, df: pd.DataFrame, metrics: list, group_by: str, title: str, output: Path, fmt: str) -> None:
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
    
    final_out = output.with_suffix(f".{fmt}")
    plt.savefig(final_out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {final_out}")

def plot_box(plt, df: pd.DataFrame, metrics: list, group_by: str, title: str, output: Path, fmt: str) -> None:
    for col in metrics:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    groups = df[group_by].unique()
    for metric in metrics:
        fig, ax = plt.subplots(figsize=(max(8, len(groups) * 1.5), 6))
        data = [df[df[group_by] == g][metric].dropna().values for g in groups]
        ax.boxplot(data, labels=list(groups))
        ax.set_title(f"{title} — {metric}")
        ax.set_xlabel(group_by)
        ax.set_ylabel(metric)
        plt.xticks(rotation=30, ha='right')

        out = output.parent / f"{output.stem}_{metric}.{fmt}"
        plt.savefig(out, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved: {out}")

def plot_per_problem(plt, df: pd.DataFrame, metrics: list, group_by: str, title: str, output_dir: Path, fmt: str) -> None:
    if 'problem' not in df.columns:
        print("No 'problem' column in CSV.")
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
        
        out = (output_dir / f"{'_'.join(metrics)}_{problem}").with_suffix(f".{fmt}")
        plt.savefig(out, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved: {out}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Plot any numeric metric from benchmark results CSV.")
    parser.add_argument("csv", type=Path, help="Path to results CSV")
    parser.add_argument("metrics", nargs="+", help="Numeric column(s) to plot")
    parser.add_argument("--plot", choices=["bar", "box"], default="bar", help="Plot type")
    parser.add_argument("--group-by", default="config", help="Column to group by")
    parser.add_argument("--per-problem", action="store_true", default=True)
    parser.add_argument("--no-per-problem", action="store_false", dest="per_problem")
    parser.add_argument("--output", type=Path, default=Path("./plots"), help="Output directory")
    parser.add_argument("--title", default=None)
    parser.add_argument("--format", choices=["png", "svg", "pdf"], default="svg", help="File format (default: svg)")

    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    plt = setup_matplotlib(args.format)
    df = pd.read_csv(args.csv)

    if args.group_by == "config":
        df['config'] = build_config_column(df)

    title = args.title or f"{' / '.join(args.metrics)} by {args.group_by}"

    if args.per_problem:
        args.output.mkdir(parents=True, exist_ok=True)
        plot_per_problem(plt, df, args.metrics, args.group_by, title, args.output, args.format)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        base_path = args.output if args.output.suffix in ['.png', '.svg', '.pdf'] else args.output / f"{'_'.join(args.metrics)}"
        
        if args.plot == "box":
            plot_box(plt, df, args.metrics, args.group_by, title, base_path, args.format)
        else:
            plot_bar(plt, df, args.metrics, args.group_by, title, base_path, args.format)

if __name__ == "__main__":
    main()
