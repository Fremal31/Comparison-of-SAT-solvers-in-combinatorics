#!/usr/bin/env python3
"""
hamilton_SAT_improved.py

Improvements over the naive positional encoding:
  1. Symmetry breaking: vertex 0 is fixed at position 0 (cuts 2n equivalent solutions).
  2. Ladder (sequential) AMO: O(n) clauses per constraint vs O(n^2) pairwise.
  3. Edge-variable encoding (--mode edge): uses x[u,v] edge variables + degree
     constraints + DFS-order subtour breaking via auxiliary ordering variables.
     Propagates much more strongly than the positional encoding.

Usage:
  python hamilton_SAT_improved.py graph.g6 [--all] [--mode cycle|path|edge]
"""
import sys
from pathlib import Path
import argparse
from typing import List, Tuple
import networkx as nx


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("g6file", type=Path, help="Input graph6 file or '-' for stdin")
    p.add_argument("--all", action="store_true", help="Process all graphs (default: first)")
    p.add_argument("--mode", choices=("cycle", "path", "edge"), default="edge",
                   help="Encoding: positional cycle, positional path, or edge-variable (default: edge)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# DIMACS output
# ---------------------------------------------------------------------------
def print_dimacs(num_vars: int, clauses: List[List[int]], graph_index: int, n_vertices: int):
    out = sys.stdout
    out.write(f"c graph_index {graph_index}\n")
    out.write(f"c n_vertices {n_vertices}\n")
    out.write(f"p cnf {max(1, num_vars)} {len(clauses)}\n")
    for cl in clauses:
        out.write(" ".join(str(l) for l in cl) + " 0\n")
    out.write("\n")


# ---------------------------------------------------------------------------
# Variable counter (fresh variables on demand)
# ---------------------------------------------------------------------------
class VarCounter:
    def __init__(self):
        self._count = 0

    def fresh(self) -> int:
        self._count += 1
        return self._count

    @property
    def count(self):
        return self._count


# ---------------------------------------------------------------------------
# AMO encodings
# ---------------------------------------------------------------------------

def amo_pairwise(lits: List[int]) -> List[List[int]]:
    """Classic O(n^2) pairwise AMO — kept for reference/small n."""
    clauses = []
    for i in range(len(lits)):
        for j in range(i + 1, len(lits)):
            clauses.append([-lits[i], -lits[j]])
    return clauses


def amo_ladder(lits: List[int], vc: VarCounter) -> List[List[int]]:
    """
    Ladder / sequential AMO encoding (Sinz 2005).
    Introduces n-1 auxiliary 'register' variables r[1..n-1].
    Total clauses: 3(n-1), much better than n(n-1)/2 pairwise.

    Semantics: r[i] means "at least one of lits[0..i] is true."
    """
    clauses = []
    n = len(lits)
    if n <= 1:
        return clauses
    if n == 2:
        clauses.append([-lits[0], -lits[1]])
        return clauses

    # allocate register variables
    regs = [vc.fresh() for _ in range(n - 1)]

    # x[0] => r[0]
    clauses.append([-lits[0], regs[0]])

    for i in range(1, n - 1):
        # x[i] => r[i]
        clauses.append([-lits[i], regs[i]])
        # r[i-1] => r[i]   (register propagates forward)
        clauses.append([-regs[i - 1], regs[i]])
        # x[i] and r[i-1] can't both be true  (at most one)
        clauses.append([-lits[i], -regs[i - 1]])

    # last literal: x[n-1] and r[n-2] can't both be true
    clauses.append([-lits[n - 1], -regs[n - 2]])

    return clauses


def alo(lits: List[int]) -> List[int]:
    """At-least-one clause."""
    return lits[:]


# ---------------------------------------------------------------------------
# POSITIONAL ENCODING (improved: ladder AMO + symmetry breaking)
# ---------------------------------------------------------------------------

class PosVarMapper:
    def __init__(self, n: int, start: int):
        self.n = n
        self.start = start  # first fresh variable index

    def id(self, v: int, p: int) -> int:
        return self.start + v * self.n + p


def ham_cycle_positional(G: nx.Graph) -> Tuple[int, List[List[int]]]:
    """
    Positional encoding with:
      - Symmetry breaking: vertex 0 fixed at position 0
      - Ladder AMO instead of pairwise
    """
    n = G.number_of_nodes()
    if n <= 1:
        return 1, []

    vc = VarCounter()

    # positional variables: x[v,p] = vertex v is at position p
    # allocate n*n variables first
    pos_vars_start = 1
    vm = PosVarMapper(n, pos_vars_start)
    vc._count = n * n  # reserve space for positional vars

    clauses = []
    nodes = list(range(n))

    # --- Symmetry breaking: fix vertex 0 at position 0 ---
    # Unit clause: x[0,0] = true
    clauses.append([vm.id(0, 0)])
    # x[0,p] = false for p > 0
    for p in range(1, n):
        clauses.append([-vm.id(0, p)])

    # --- Each position has exactly one vertex ---
    for p in range(n):
        # ALO
        clauses.append(alo([vm.id(v, p) for v in nodes]))
        # AMO (ladder)
        clauses.extend(amo_ladder([vm.id(v, p) for v in nodes], vc))

    # --- Each vertex appears exactly once ---
    for v in nodes:
        # ALO
        clauses.append(alo([vm.id(v, p) for p in range(n)]))
        # AMO (ladder)
        clauses.extend(amo_ladder([vm.id(v, p) for p in range(n)], vc))

    # --- Non-edge constraints (adjacency in cycle) ---
    for u in range(n):
        for v in range(u + 1, n):
            if not G.has_edge(u, v):
                for p in range(n):
                    p_next = (p + 1) % n
                    clauses.append([-vm.id(u, p), -vm.id(v, p_next)])
                    clauses.append([-vm.id(v, p), -vm.id(u, p_next)])

    return vc.count, clauses


def ham_path_positional(G: nx.Graph) -> Tuple[int, List[List[int]]]:
    """Positional path encoding with ladder AMO."""
    n = G.number_of_nodes()
    if n == 0:
        return 0, []
    if n == 1:
        return 1, []

    vc = VarCounter()
    vm = PosVarMapper(n, 1)
    vc._count = n * n

    clauses = []
    nodes = list(range(n))

    for p in range(n):
        clauses.append(alo([vm.id(v, p) for v in nodes]))
        clauses.extend(amo_ladder([vm.id(v, p) for v in nodes], vc))

    for v in nodes:
        clauses.append(alo([vm.id(v, p) for p in range(n)]))
        clauses.extend(amo_ladder([vm.id(v, p) for p in range(n)], vc))

    for u in range(n):
        for v in range(u + 1, n):
            if not G.has_edge(u, v):
                for p in range(n - 1):
                    clauses.append([-vm.id(u, p), -vm.id(v, p + 1)])
                    clauses.append([-vm.id(v, p), -vm.id(u, p + 1)])

    return vc.count, clauses


# ---------------------------------------------------------------------------
# EDGE-VARIABLE ENCODING
# ---------------------------------------------------------------------------
#
# Variables:
#   e[u,v]  — edge {u,v} is in the Hamiltonian cycle           (n*(n-1)/2 at most)
#   o[v]    — ordering variable: position of v in cycle        (used for subtour elim)
#
# Constraints:
#   1. Degree: each vertex has exactly 2 selected edges
#      → exactly-one on each "pair" of neighbors (via ladder AMO on the two selected)
#      → actually: sum of e[u,v] for v in N(u) = 2
#      Encoded as: ALO-2 (at least 2) + AMO-2 (at most 2)
#
#   2. Connectivity (subtour elimination via ordering):
#      Fix vertex 0 as root (order = 0). For every edge {u,v} with u,v != 0:
#        e[u,v] = 1  =>  |o[u] - o[v]| = 1   (they are adjacent in cycle)
#      We use the standard directed auxiliary approach:
#        For each edge {u,v} in G, two directed arc variables a[u->v], a[v->u]
#        e[u,v] = 1  =>  a[u->v]=1 XOR a[v->u]=1
#        a[u->v] = 1 and u != 0  =>  o[v] = o[u] + 1  (mod n, but root anchors it)
#
# In practice, the most competitive pure-SAT approach for Ham cycle uses:
#   - Edge variables + degree-2 constraint
#   - Auxiliary "next" pointer variables (each vertex has exactly one successor)
#   - Connectivity via reachability from vertex 0 using these pointers
#
# This is the "successor encoding" described in:
#   Anbulagan & Adi Botea, "Extending Compact Encoding for Hamiltonian Cycle"
# ---------------------------------------------------------------------------

def ham_cycle_edge(G: nx.Graph) -> Tuple[int, List[List[int]]]:
    """
    Edge-variable encoding with successor variables and reachability-based
    subtour elimination. Much stronger unit propagation than positional.

    Variables:
      e[u,v]   : edge {u,v} selected (one per undirected edge in G)
      s[u][v]  : vertex v is the successor of u in the cycle direction
                 (directed, so s[u][v] != s[v][u] in general)
      r[u][k]  : vertex u is reachable from vertex 0 in k steps
                 (for subtour elimination, k = 1..n-1)
    """
    n = G.number_of_nodes()
    if n <= 2:
        return 1, []

    vc = VarCounter()
    clauses = []
    edges = list(G.edges())
    nodes = list(range(n))
    neighbors = {v: list(G.neighbors(v)) for v in nodes}

    # --- Edge variables ---
    edge_var = {}
    for u, v in edges:
        ev = vc.fresh()
        edge_var[(u, v)] = ev
        edge_var[(v, u)] = ev

    # --- Successor variables: s[u][v] = v is successor of u ---
    # Only for (u,v) where {u,v} is an edge in G
    succ_var = {}
    for u in nodes:
        for v in neighbors[u]:
            succ_var[(u, v)] = vc.fresh()

    # --- Degree constraints: each vertex has exactly 2 incident edges ---
    for u in nodes:
        nbr_edges = [edge_var[(u, v)] for v in neighbors[u]]
        if len(nbr_edges) < 2:
            # graph is not 2-connected here, trivially no Ham cycle
            clauses.append([])  # empty clause = UNSAT
            return vc.count, clauses

        # ALO-2: at least 2 edges selected
        # Encode as: not possible that fewer than 2 are true
        # = for every pair of neighbors (v,w), at least one of the others OR both v,w
        # Simplest: negate the "at most 1" condition
        # ALO-2 ↔ ¬(at most 1 true) ↔ for all pairs (i,j): e_i ∨ e_j ... not quite
        # Correct ALO-2: ∑ >= 2  ↔  for every (n-1) subset of size n-1, at least one true
        # Easier: use the totalizer / add explicit clause "sum >= 2"
        # We'll use: for each vertex, at least 2 neighbors selected:
        #   for every pair (i,j) of non-neighbors of u (in edge sense): 
        #     this is complex; instead use the simpler "for all pairs, not both false"
        # Best practical approach: 
        #   AMO(nbr_edges) restricted to "exactly 2" via:
        #   (a) add ALO clause (trivial, just the big OR)
        #   (b) AMO-2: "at most 2" = for every triple, at least one is false
        #       = for all i<j<k: ¬e_i ∨ ¬e_j ∨ ¬e_k

        # At least 2: we use a simple encoding
        # Negate "sum <= 1": for every pair NOT both selected => at least one other must be
        # Cleanest: "for each v in N(u), if e[u,v]=0 then sum of rest >= 2"
        # We use a known EK-2 encoding: ALO-2 = big OR of all pairs
        # i.e. at least one pair is both true:  OR_{i<j} (e_i AND e_j)
        # = Tseitin: aux_ij <=> (e_i AND e_j), then OR(aux_ij)
        # For degree constraint this is manageable for sparse graphs.

        # Simpler tractable approach for sparse graphs (cubic etc.):
        # For cubic graphs: exactly 2 out of 3 edges
        # Use: (a ∨ b), (a ∨ c), (b ∨ c)  [ALO-2 for 3 vars]
        # and: ¬(a ∧ b ∧ c)               [AMO-2 for 3 vars]
        # Generalized:

        # ALO-2: for each subset of size (len-1), at least one of those is true
        # = for each neighbor v: OR of all edges except e[u,v]  ... that's ALO-1 of rest
        # Hmm that's weaker. Let's do it properly.

        # For a list of k literals, "at least 2 are true":
        # = NOT (at most 1 are true)
        # = NOT (all false OR exactly one true)
        # Clause form: for every pair (i,j): NOT(all-except-i-and-j are false) -- too complex
        # 
        # Practical compromise: use the "pair" encoding:
        # at-least-2(x1..xk) = AND over i of (x_i => exists j!=i: x_j)
        #                     = AND over i of (¬x_i OR OR_{j!=i} x_j)
        # This is k clauses of size k-1 each. Works well.
        for i, ei in enumerate(nbr_edges):
            rest = [nbr_edges[j] for j in range(len(nbr_edges)) if j != i]
            clauses.append([-ei] + rest)  # if ei selected, at least one other must be

        # At most 2: for every triple, at least one is false
        for i in range(len(nbr_edges)):
            for j in range(i + 1, len(nbr_edges)):
                for k in range(j + 1, len(nbr_edges)):
                    clauses.append([-nbr_edges[i], -nbr_edges[j], -nbr_edges[k]])

    # --- Successor consistency: e[u,v]=1 <=> exactly one of s[u,v] or s[v,u] is 1 ---
    for u, v in edges:
        euv = edge_var[(u, v)]
        suv = succ_var[(u, v)]
        svu = succ_var[(v, u)]
        # e[u,v] => s[u,v] XOR s[v,u]
        clauses.append([-euv, suv, svu])       # e => s[u,v] ∨ s[v,u]
        clauses.append([-euv, -suv, -svu])     # e => ¬(both)
        # s[u,v] => e[u,v]
        clauses.append([-suv, euv])
        clauses.append([-svu, euv])

    # --- Each vertex has exactly one successor ---
    for u in nodes:
        out_arcs = [succ_var[(u, v)] for v in neighbors[u]]
        if not out_arcs:
            clauses.append([])
            return vc.count, clauses
        # ALO
        clauses.append(out_arcs[:])
        # AMO (ladder)
        clauses.extend(amo_ladder(out_arcs, vc))

    # --- Each vertex has exactly one predecessor ---
    for v in nodes:
        in_arcs = [succ_var[(u, v)] for u in neighbors[v]]
        if not in_arcs:
            clauses.append([])
            return vc.count, clauses
        clauses.append(in_arcs[:])
        clauses.extend(amo_ladder(in_arcs, vc))

    # --- Subtour elimination via reachability from vertex 0 ---
    # r[v][k] = vertex v is reachable from 0 in exactly k steps (k=1..n-1)
    # Constraints:
    #   r[v][1] <=> s[0][v]   (v is reachable in 1 step iff it's successor of 0)
    #   r[v][k] <=> OR_{u: (u,v) in G} (r[u][k-1] AND s[u][v])
    # At-least-one coverage: for each v != 0, OR_k r[v][k] must be true
    #
    # To keep variable count manageable, we use a more compact encoding:
    # Ordering variables ord[v] in {1..n-1} for v != 0, with ord[0]=0 implicit.
    # s[u][v]=1 => ord[v] = ord[u] + 1   (for u != root incoming to v)
    # This is encoded as difference constraints via auxiliary bit variables.
    #
    # Compact SAT encoding using log2(n) bits per ordering variable:
    # For each v != 0: bits b[v][0..B-1]  representing ord[v] in binary
    # s[u][v]=1 => ord[v] = ord[u] + 1 mod n
    # This is complex to encode cleanly. A practical middle ground:
    #
    # We use the "distance labeling" approach:
    # For each v != 0 and each k in 1..n-1:
    #   r[v][k]: v is at distance k from vertex 0
    # s[0][v]=1 => r[v][1]
    # r[u][k] AND s[u][v] => r[v][k+1]   for k < n-1
    # For v != 0: OR_{k=1}^{n-1} r[v][k]   (v must be reachable)
    # Also: at most one r[v][k] per v (each vertex at exactly one distance)

    # --- Subtour elimination: reachability from vertex 0 via successor arcs ---
    #
    # THE BUG IN THE PREVIOUS VERSION:
    #   All implications were one-directional (forward only):
    #     s[0][v] => r[v][1]
    #     r[u][k] ∧ s[u][v] => r[v][k+1]
    #   This lets the solver freely set r[v][k]=True to satisfy the coverage
    #   clause OR_k r[v][k], without any actual path from 0 existing.
    #   e.g. on the Petersen graph: assign two 5-cycles, set all r[v][k]=True → SAT.
    #
    # THE FIX: add backward implications (biconditional reachability).
    #   r[v][1]   <=>  s[0][v]
    #   r[v][k]   =>   OR_{u in N(v), u!=0} t[u,v,k]     (backward, via Tseitin aux)
    #   t[u,v,k]  =>   r[u][k-1]  ∧  s[u][v]
    #
    # The forward direction (r[u][k-1] ∧ s[u][v] => r[v][k]) is still needed too.
    # Together these make r[v][k] true IFF there is an actual k-step path 0→...→v.

    reach = {}  # reach[(v,k)] = variable r[v][k]
    for v in nodes:
        if v == 0:
            continue
        for k in range(1, n):
            reach[(v, k)] = vc.fresh()

    # --- Base case: r[v][1] <=> s[0][v] ---
    for v in nodes:
        if v == 0:
            continue
        if v in neighbors[0]:
            s0v = succ_var[(0, v)]
            rv1 = reach[(v, 1)]
            clauses.append([-s0v, rv1])   # s[0][v] => r[v][1]  (forward)
            clauses.append([-rv1, s0v])   # r[v][1] => s[0][v]  (backward — THE FIX)
        else:
            # v is not reachable in 1 step from 0 (not even a neighbor)
            clauses.append([-reach[(v, 1)]])  # r[v][1] = False

    # --- Step case: both forward and backward ---
    for k in range(2, n):
        for v in nodes:
            if v == 0:
                continue
            rvk = reach[(v, k)]
            # valid predecessors: neighbors of v that are not vertex 0
            valid_preds = [u for u in neighbors[v] if u != 0]

            if not valid_preds:
                # can never be reached at step k >= 2 (all predecessors would be 0,
                # but 0 is only a valid predecessor at k=1)
                clauses.append([-rvk])
                continue

            # Forward: for each predecessor u, r[u][k-1] ∧ s[u][v] => r[v][k]
            for u in valid_preds:
                clauses.append([-reach[(u, k - 1)], -succ_var[(u, v)], rvk])

            # Backward (THE FIX): r[v][k] => OR_{u} t[u,v,k]
            # where t[u,v,k] is a Tseitin aux meaning "r[u][k-1] AND s[u][v]"
            aux_lits = []
            for u in valid_preds:
                t = vc.fresh()
                aux_lits.append(t)
                clauses.append([-t, reach[(u, k - 1)]])   # t => r[u][k-1]
                clauses.append([-t, succ_var[(u, v)]])     # t => s[u][v]
                # Note: we don't need (r[u][k-1] ∧ s[u][v] => t) for correctness,
                # only for tightness. The forward clause above suffices for that direction.
            clauses.append([-rvk] + aux_lits)  # r[v][k] => OR_u t[u,v,k]

    # --- Coverage: each non-root vertex must be reachable at some distance ---
    for v in nodes:
        if v == 0:
            continue
        clauses.append([reach[(v, k)] for k in range(1, n)])

    # --- AMO on reach distances per vertex (each vertex at exactly one depth) ---
    for v in nodes:
        if v == 0:
            continue
        reach_lits = [reach[(v, k)] for k in range(1, n)]
        clauses.extend(amo_ladder(reach_lits, vc))

    return vc.count, clauses


# ---------------------------------------------------------------------------
# g6 reader
# ---------------------------------------------------------------------------
def graphs_from_g6_lines(lines):
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith(">>"):
            continue
        try:
            G = nx.from_graph6_bytes(s.encode())
        except Exception as e:
            raise RuntimeError(f"Failed to parse graph6 line {i}: {e}")
        yield G


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    g6file = args.g6file

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
        n = G.number_of_nodes()
        current_nodes_sorted = sorted(G.nodes())
        if current_nodes_sorted != list(range(n)):
            mapping = {old: new for new, old in enumerate(current_nodes_sorted)}
            G = nx.relabel_nodes(G, mapping, copy=True)

        if args.mode == "cycle":
            num_vars, clauses = ham_cycle_positional(G)
        elif args.mode == "path":
            num_vars, clauses = ham_path_positional(G)
        else:  # edge
            num_vars, clauses = ham_cycle_edge(G)

        print_dimacs(max(1, num_vars), clauses, idx, n)


if __name__ == "__main__":
    main()