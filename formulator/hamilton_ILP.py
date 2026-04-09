#!/usr/bin/env python3
"""
hamilton_ILP.py

Read graphs from a graph6 (.g6) file and print LP formulation(s) for the
Hamiltonian cycle decision problem to stdout.

By default only the first graph is processed. Use --all to print every graph's LP.
Multiple LPs are separated by blank lines.
"""
import sys
import argparse
import networkx as nx
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Read .g6 and print Hamiltonian-cycle LP(s) to stdout")
    p.add_argument("g6file", type=Path, help="Input .g6 file or '-'")
    p.add_argument("--all", action="store_true", help="Process all graphs in the file (default: first)")
    p.add_argument("--mode", choices=("cycle", "path"), default="cycle")
    return p.parse_args()


def graphs_from_g6_lines(lines):
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith(">>"):
            continue
        try:
            yield nx.from_graph6_bytes(s.encode())
        except Exception as e:
            raise RuntimeError(f"Failed to parse graph6 line {i}: {e}")


def print_lp(G: nx.Graph, idx: int) -> None:
    n = G.number_of_nodes()
    nodes = list(range(n))

    # Relabel to 0..n-1
    current = sorted(G.nodes())
    if current != nodes:
        mapping = {old: new for new, old in enumerate(current)}
        G = nx.relabel_nodes(G, mapping, copy=True)

    first_edge = next(iter(G.edges()))
    first_var = f"x_{first_edge[0]}_{first_edge[1]}"

    print(f"\\ Graph {idx} - Nodes: {n}")
    print("Minimize")
    print(f"obj: 0 {first_var}")
    print("Subject To")

    # Degree constraints
    for i in nodes:
        adj = list(G.neighbors(i))
        print(f"out_{i}: " + " + ".join(f"x_{i}_{j}" for j in adj) + " = 1")
        print(f"in_{i}: " + " + ".join(f"x_{j}_{i}" for j in adj) + " = 1")

    # Subtour elimination (MTZ)
    for i in range(1, n):
        for j in range(1, n):
            if i != j and G.has_edge(i, j):
                print(f"  mtz_{i}_{j}: u_{i} - u_{j} + {n} x_{i}_{j} <= {n - 1}")

    print("Bounds")
    for i in range(1, n):
        print(f"  1 <= u_{i} <= {n}")

    print("Binaries")
    for u, v in G.edges():
        print(f"  x_{u}_{v}")
        print(f"  x_{v}_{u}")
    print("End")
    print()  # blank line separator between LPs


def main():
    args = parse_args()

    if str(args.g6file) == "-":
        content = sys.stdin.read().splitlines()
    else:
        if not args.g6file.exists():
            print(f"Input file {args.g6file} not found.", file=sys.stderr)
            sys.exit(2)
        content = args.g6file.read_text().splitlines()

    graphs = list(graphs_from_g6_lines(content))
    if not graphs:
        print("No graphs found in file.", file=sys.stderr)
        sys.exit(1)

    to_process = graphs if args.all else [graphs[0]]

    for idx, G in enumerate(to_process):
        print_lp(G, idx)


if __name__ == "__main__":
    main()
