#!/usr/bin/env python3
"""Hamiltonian cycle/path solver using Google OR-Tools CP-SAT (add_circuit constraint)."""

import sys
import argparse
from pathlib import Path

import networkx as nx
from ortools.sat.python import cp_model


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read .g6 and solve Hamiltonian cycle/path via CP-SAT")
    p.add_argument("g6file", type=Path, help="Input graph6 file")
    p.add_argument("--all",  action="store_true", help="Process all graphs in the file (default: first)")
    p.add_argument("--mode", choices=("cycle", "path"), default="cycle")
    return p.parse_args()


def graphs_from_g6(path: Path):
    for i, line in enumerate(path.read_text().splitlines()):
        s = line.strip()
        if not s or s.startswith(">>"):
            continue
        try:
            yield nx.from_graph6_bytes(s.encode())
        except Exception as e:
            raise RuntimeError(f"Failed to parse graph6 line {i}: {e}")


def solve(G: "nx.Graph", mode: str) -> None:
    n = G.number_of_nodes()

    if n == 0:
        print("UNKNOWN")
        print("conflicts: 0")
        print("branches: 0")
        print("wall_time: 0.000000")
        return

    model = cp_model.CpModel()
    arcs = []

    for u, v in G.edges():
        lit_uv = model.new_bool_var(f"arc_{u}_{v}")
        lit_vu = model.new_bool_var(f"arc_{v}_{u}")
        arcs.append((u, v, lit_uv))
        arcs.append((v, u, lit_vu))

    if mode == "path":
        # Dummy depot node d=n bridges path endpoints, turning path → circuit.
        # The depot connects to every real node in both directions.
        d = n
        for v in range(n):
            arcs.append((v, d, model.new_bool_var(f"arc_{v}_depot")))
            arcs.append((d, v, model.new_bool_var(f"arc_depot_{v}")))

    model.add_circuit(arcs)

    solver = cp_model.CpSolver()
    status = solver.solve(model)

    print(solver.status_name(status))
    print(f"conflicts: {solver.num_conflicts}")
    print(f"branches: {solver.num_branches}")
    print(f"wall_time: {solver.wall_time:.6f}")


def main() -> None:
    args = parse_args()

    graphs = graphs_from_g6(args.g6file)
    for G in graphs:
        solve(G, args.mode)
        if not args.all:
            break


if __name__ == "__main__":
    main()
