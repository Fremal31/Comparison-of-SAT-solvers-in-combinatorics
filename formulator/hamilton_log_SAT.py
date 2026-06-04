#!/usr/bin/env python3
import argparse
import math
import sys
from pathlib import Path

import networkx as nx


def parse_args():
    p = argparse.ArgumentParser(description="Convert .g6 to Logarithmic Hamiltonian SAT CNF")
    p.add_argument("g6file", type=Path, help="Input graph6 file or '-' for stdin")
    p.add_argument("output_dir", type=Path, nargs="?", default=None,
                   help="Output directory; if given, writes one .cnf per graph. "
                        "If omitted, writes to stdout (first graph only unless --all).")
    p.add_argument("--all", action="store_true",
                   help="Process all graphs (stdout mode only; directory mode always processes all)")
    p.add_argument("--mode", choices=("cycle", "path"), default="cycle")
    return p.parse_args()


def get_log_cnf(G, mode):
    n = G.number_of_nodes()
    if n < 2:
        return 1, []

    k = math.ceil(math.log2(n)) if n > 1 else 1

    def bit_var(p, b):
        return p * k + b + 1

    clauses = []

    # Forbid invalid vertex IDs (values >= n when n is not a power of 2)
    for p in range(n):
        for val in range(n, 2**k):
            clause = []
            for b in range(k):
                if (val >> b) & 1:
                    clause.append(-bit_var(p, b))
                else:
                    clause.append(bit_var(p, b))
            clauses.append(clause)

    # All-Different via XOR auxiliary variables
    aux_start = n * k + 1
    curr_aux = aux_start

    for p1 in range(n):
        for p2 in range(p1 + 1, n):
            diff_bits = []
            for b in range(k):
                d_var = curr_aux
                curr_aux += 1
                diff_bits.append(d_var)

                v1 = bit_var(p1, b)
                v2 = bit_var(p2, b)

                clauses.append([-v1, -v2, -d_var])
                clauses.append([v1,  v2,  -d_var])
                clauses.append([v1,  -v2,  d_var])
                clauses.append([-v1,  v2,  d_var])

            clauses.append(diff_bits)

    # Non-edge constraints: consecutive positions must be adjacent in G
    adj = nx.to_numpy_array(G, nodelist=range(n), dtype=int)
    limit = n if mode == "cycle" else n - 1

    for p in range(limit):
        p_next = (p + 1) % n
        for u in range(n):
            for v in range(n):
                if u != v and not adj[u][v]:
                    clause = []
                    for b in range(k):
                        clause.append(-bit_var(p, b)      if (u >> b) & 1 else bit_var(p, b))
                        clause.append(-bit_var(p_next, b) if (v >> b) & 1 else bit_var(p_next, b))
                    clauses.append(clause)

    return curr_aux - 1, clauses


def cnf_lines(idx, num_vars, clauses):
    lines = [f"c graph_index {idx}", "c method logarithmic",
             f"p cnf {num_vars} {len(clauses)}"]
    lines.extend(" ".join(map(str, c)) + " 0" for c in clauses)
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()

    content = (sys.stdin.read().splitlines()
               if str(args.g6file) == "-"
               else args.g6file.read_text().splitlines())

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stem = args.g6file.stem if str(args.g6file) != "-" else "graph"

    graph_idx = 0
    for raw in content:
        line = raw.strip()
        if not line or line.startswith(">>"):
            continue

        G = nx.from_graph6_bytes(line.encode())
        G.number_of_nodes()
        mapping = {old: i for i, old in enumerate(sorted(G.nodes()))}
        G = nx.relabel_nodes(G, mapping)

        num_vars, clauses = get_log_cnf(G, args.mode)
        text = cnf_lines(graph_idx, num_vars, clauses)

        if args.output_dir is not None:
            out_path = args.output_dir / f"{stem}_{graph_idx:04d}.cnf"
            out_path.write_text(text)
        else:
            sys.stdout.write(text + "\n")
            if not args.all:
                break

        graph_idx += 1


if __name__ == "__main__":
    main()
