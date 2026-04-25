#!/usr/bin/env python3
"""Splits a multi-graph g6 file into one file per graph in an output directory."""

import sys
import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Split a .g6 file into one file per graph")
    p.add_argument("g6file",     type=Path, help="Input graph6 file")
    p.add_argument("output_dir", type=Path, help="Directory to write individual graph files into")
    p.add_argument("--suffix",   default=".cpsat", help="File suffix for output files (default: .cpsat)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for line in args.g6file.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith(">>"):
            continue
        out_file = args.output_dir / f"graph_{count:04d}{args.suffix}"
        out_file.write_text(s + "\n")
        count += 1

    if count == 0:
        print(f"No graphs found in {args.g6file}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
