#!/usr/bin/env python3
import sys
import networkx as nx
from z3 import *
from pathlib import Path

def solve_g6_smt(g6_line, mode="cycle"):
    # 1. Parse Graph
    G = nx.from_graph6_bytes(g6_line.encode())
    n = G.number_of_nodes()
    if n == 0: return "EMPTY"
    
    # 2. Formulate (The "Formulator" part)
    s = Solver()
    
    # Path variables: p[0] is the 1st node visited, p[1] is the 2nd, etc.
    p = [Int(f'step_{i}') for i in range(n)]
    
    # Constraints: Each step must be a valid node index [0, n-1]
    for x in p:
        s.add(x >= 0, x < n)
    
    # Constraint: Must visit every node exactly once
    s.add(Distinct(p))
    
    # Constraints: Every adjacent pair in the path must have an edge in G
    for i in range(n - 1):
        u, v = p[i], p[i+1]
        # We create a big 'Or' of all valid edges
        edges = []
        for edge in G.edges():
            # Treat as undirected
            edges.append(And(u == edge[0], v == edge[1]))
            edges.append(And(u == edge[1], v == edge[0]))
        s.add(Or(edges))

    # If cycle, add edge from last node back to first
    if mode == "cycle":
        u, v = p[n-1], p[0]
        edges = [And(u == e[0], v == e[1]) for e in G.edges()] + \
                [And(u == e[1], v == e[0]) for e in G.edges()]
        s.add(Or(edges))

    # 3. Solve (The "Solver" part)
    if s.check() == sat:
        m = s.model()
        res = [m.evaluate(step).as_long() for step in p]
        return f"SAT: {res}"
    else:
        return "UNSAT"

def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <file.g6> [--path]")
        return
    
    file_path = Path(sys.argv[1])
    mode = "path" if "--path" in sys.argv else "cycle"
    
    lines = file_path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith(">>"): continue
        result = solve_g6_smt(line.strip(), mode)
        print(f"Graph {i}: {result}")

if __name__ == "__main__":
    main()