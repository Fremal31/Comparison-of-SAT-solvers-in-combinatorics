#!/usr/bin/env python3
"""
circular_ILP.py

Read a graph from a sparse6 (.s6) or graph6 (.g6) file and print an LP
formulation (CPLEX LP format, for HiGHS) of the circular chromatic *index*
decision problem to stdout.

The circular chromatic index is an *edge* colouring: assign each edge a colour
in Z_p so that any two edges sharing an endpoint have colours at circular
distance at least q. This is the circular (p, q)-colouring of the line graph,
so the model has one one-hot block per edge and a forbidden-pair constraint for
every pair of incident edges and every too-close colour pair. The verdict
(feasible / infeasible) matches the SAT edge encoding and the CP-SAT model on
the same (graph, p, q); only the formulation differs.

Multigraphs are handled: parallel edges share both endpoints and so conflict.
The graphs used here are loopless (a loop would be incident to itself and admit
no colouring).

Usage:
    circular_ILP.py <graph.s6|.g6|-> --pq=P/Q
"""
import sys
import argparse
import networkx as nx
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(
        description="Print the circular-chromatic-index (edge) LP for one (p, q)."
    )
    p.add_argument("graph", type=Path, help="Input .s6/.g6 file or '-'")
    p.add_argument("--pq", required=True, help="Single ratio P/Q, e.g. 29/6")
    return p.parse_args()


def read_graph(path: Path) -> nx.MultiGraph:
    raw = sys.stdin.buffer.read() if str(path) == "-" else path.read_bytes()
    line = raw.strip().splitlines()[0].strip()
    # sparse6 starts with ':' (optionally after a '>>sparse6<<' header).
    body = line.split(b"<<", 1)[-1] if line.startswith(b">>") else line
    if body.startswith(b":"):
        return nx.MultiGraph(nx.from_sparse6_bytes(line))
    return nx.MultiGraph(nx.from_graph6_bytes(line))


def circular_dist(a: int, b: int, p: int) -> int:
    d = abs(a - b)
    return min(d, p - d)


def print_lp(G: nx.MultiGraph, p: int, q: int) -> None:
    edges = list(G.edges())  # multiset: parallel edges listed separately
    m = len(edges)

    # Incident (conflicting) edge pairs: share at least one endpoint.
    conflicts = [
        (i, j)
        for i in range(m)
        for j in range(i + 1, m)
        if set(edges[i]) & set(edges[j])
    ]
    # Colour pairs that are too close on the circle Z_p (forbidden together).
    forbidden = [
        (k, l) for k in range(p) for l in range(p) if circular_dist(k, l, p) < q
    ]

    out = sys.stdout.write
    out(f"\\ Circular chromatic index (edge), p/q = {p}/{q}, "
        f"|V|={G.number_of_nodes()} |E|={m}\n")
    out("Minimize\n")
    out(f" obj: 0 x_0_0\n")
    out("Subject To\n")
    # Exactly one colour per edge.
    for i in range(m):
        out(f" oh_{i}: " + " + ".join(f"x_{i}_{k}" for k in range(p)) + " = 1\n")
    # Incident edges may not take colours closer than q.
    for (i, j) in conflicts:
        for (k, l) in forbidden:
            out(f" c_{i}_{j}_{k}_{l}: x_{i}_{k} + x_{j}_{l} <= 1\n")
    out("Binaries\n")
    for i in range(m):
        for k in range(p):
            out(f" x_{i}_{k}\n")
    out("End\n")


def main():
    args = parse_args()
    try:
        p_str, q_str = args.pq.split("/")
        p, q = int(p_str), int(q_str)
    except Exception:
        print(f"Bad --pq value {args.pq!r}; expected P/Q.", file=sys.stderr)
        sys.exit(2)

    if str(args.graph) != "-" and not args.graph.exists():
        print(f"Input file {args.graph} not found.", file=sys.stderr)
        sys.exit(2)

    G = read_graph(args.graph)
    print_lp(G, p, q)


if __name__ == "__main__":
    main()
