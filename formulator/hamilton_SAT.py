#!/usr/bin/env python3
"""
g6_to_ham_stdout.py

Read graphs from a graph6 (.g6) file and print DIMACS CNF(s) for the Hamiltonian cycle
decision problem to stdout.

By default only the first non-header graph is processed. Use --all to print every graph's CNF.
"""
import sys
from pathlib import Path
import argparse
from typing import List, Tuple
import networkx as nx

# -----------------------
# Argument parsing
# -----------------------
def parse_args():
    p = argparse.ArgumentParser(description="Read .g6 and print Hamiltonian-cycle CNF(s) to stdout")
    p.add_argument("g6file", type=Path, help="Input graph6 file or '-' for stdin")
    p.add_argument("--all", action="store_true", help="Process all graphs in the file (default: first)")
    p.add_argument("--mode", choices=("cycle","path"), default="cycle", help="Encode cycle (default) or path")
    return p.parse_args()

# -----------------------
# Variable mapper & DIMACS writer (to stdout)
# -----------------------
class VarMapper:
    def __init__(self, n: int):
        self.n = n
    def id(self, v: int, p: int) -> int:
        return v * self.n + p + 1

def print_dimacs(num_vars: int, clauses: List[List[int]], graph_index: int, n_vertices: int):
    """
    Print a DIMACS CNF to stdout. Prepend a few comment lines as header.
    """
    out = sys.stdout
    out.write(f"c graph_index {graph_index}\n")
    out.write(f"c n_vertices {n_vertices}\n")
    out.write(f"p cnf {max(1, num_vars)} {len(clauses)}\n")
    for cl in clauses:
        out.write(" ".join(str(l) for l in cl) + " 0\n")
    out.write("\n")  # separate CNFs with a blank line

# -----------------------
# Hamiltonian encodings
# -----------------------
def ham_cycle_clauses(G: nx.Graph) -> Tuple[int, List[List[int]]]:
    n = G.number_of_nodes()
    if n <= 1:
        return 0, []
    vm = VarMapper(n)
    clauses = []
    nodes = list(range(n))

    # each position has at least one vertex
    for p in range(n):
        clauses.append([vm.id(v, p) for v in nodes])

    # at most one vertex per position (pairwise)
    for p in range(n):
        for i in range(n):
            for j in range(i+1, n):
                clauses.append([-vm.id(i, p), -vm.id(j, p)])

    # each vertex appears at least once
    for v in nodes:
        clauses.append([vm.id(v, p) for p in range(n)])

    # each vertex appears at most once (pairwise over positions)
    for v in nodes:
        for p in range(n):
            for q in range(p+1, n):
                clauses.append([-vm.id(v, p), -vm.id(v, q)])

    # non-edge constraints forbidding adjacent positions (wrap-around)
    for u in range(n):
        for v in range(u+1, n):
            if not G.has_edge(u, v):
                for p in range(n):
                    p_next = (p + 1) % n
                    clauses.append([-vm.id(u, p), -vm.id(v, p_next)])
                    clauses.append([-vm.id(v, p), -vm.id(u, p_next)])

    return n * n, clauses

def ham_path_clauses(G: nx.Graph) -> Tuple[int, List[List[int]]]:
    n = G.number_of_nodes()
    if n == 0:
        return 0, []
    if n == 1:
        return 1, []
    vm = VarMapper(n)
    clauses = []
    nodes = list(range(n))

    # each position has at least one vertex
    for p in range(n):
        clauses.append([vm.id(v, p) for v in nodes])

    # at most one vertex per position (pairwise)
    for p in range(n):
        for i in range(n):
            for j in range(i+1, n):
                clauses.append([-vm.id(i, p), -vm.id(j, p)])

    # each vertex appears at least once
    for v in nodes:
        clauses.append([vm.id(v, p) for p in range(n)])

    # each vertex appears at most once (pairwise)
    for v in nodes:
        for p in range(n):
            for q in range(p+1, n):
                clauses.append([-vm.id(v, p), -vm.id(v, q)])

    # non-edge constraints for positions p -> p+1 without wrap
    for u in range(n):
        for v in range(u+1, n):
            if not G.has_edge(u, v):
                for p in range(n-1):
                    p_next = p + 1
                    clauses.append([-vm.id(u, p), -vm.id(v, p_next)])
                    clauses.append([-vm.id(v, p), -vm.id(u, p_next)])

    return n * n, clauses

# -----------------------
# g6 reader
# -----------------------
def graphs_from_g6_lines(lines):
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if s.startswith(">>"):
            continue
        try:
            G = nx.from_graph6_bytes(s.encode())
        except Exception as e:
            raise RuntimeError(f"Failed to parse graph6 line {i}: {e}")
        yield G

# -----------------------
# Main
# -----------------------
def main():
    args = parse_args()
    g6file = args.g6file

    # read from stdin if "-" is provided
    if str(g6file) == "-":
        content = sys.stdin.read().splitlines()
    else:
        if not g6file.exists():
            print(f"Input file {g6file} not found.", file=sys.stderr)
            sys.exit(2)
        content = g6file.read_text().splitlines()

    graphs = list(graphs_from_g6_lines(content))
    if not graphs:
        print("No graphs found in file.", file=sys.stderr)
        sys.exit(1)

    to_process = graphs if args.all else [graphs[0]]

    for idx, G in enumerate(to_process):
        # relabel nodes to 0..n-1
        n = G.number_of_nodes()
        desired_labels = list(range(n))
        current_nodes_sorted = sorted(G.nodes())
        if current_nodes_sorted != desired_labels:
            mapping = {old: new for new, old in enumerate(current_nodes_sorted)}
            G = nx.relabel_nodes(G, mapping, copy=True)

        # generate clauses
        if args.mode == "cycle":
            num_vars, clauses = ham_cycle_clauses(G)
        else:
            num_vars, clauses = ham_path_clauses(G)

        # print CNF
        print_dimacs(num_vars if num_vars > 0 else 1, clauses, idx, n)

if __name__ == "__main__":
    main()
