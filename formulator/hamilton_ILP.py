#!/usr/bin/env python3
import sys
import argparse
import networkx as nx
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("g6file", type=Path, help="Input .g6 file or '-'")
    p.add_argument("--mode", choices=("cycle","path"), default="cycle")
    return p.parse_args()

def run():
    args = parse_args()
    content = sys.stdin.read().splitlines() if str(args.g6file) == "-" else args.g6file.read_text().splitlines()
    
    for idx, line in enumerate(content):
        line = line.strip()
        if not line or line.startswith(">>"): continue
        G = nx.from_graph6_bytes(line.encode())
        n = G.number_of_nodes()
        
        print(f"\\ Graph {idx} - Nodes: {n}")
        print("Minimize")
        first_var = f"x_{list(G.nodes())[0]}_{list(G.neighbors(list(G.nodes())[0]))[0]}"
        print("Minimize")
        print(f"obj: 0 {first_var}")
        print("Subject To")
        
        # 1. Degree Constraints
        for i in range(n):
            adj = list(G.neighbors(i))
            # Out-flow
            print(f"out_{i}: " + " + ".join([f"x_{i}_{j}" for j in adj]) + " = 1")
            # In-flow
            print(f"in_{i}: " + " + ".join([f"x_{j}_{i}" for j in adj]) + " = 1")
            
        # 2. Subtour Elimination (MTZ)
        # Prevents small loops. u_i is the "order" of node i.
        for i in range(1, n):
            for j in range(1, n):
                if i != j and G.has_edge(i, j):
                    print(f"  mtz_{i}_{j}: u_{i} - u_{j} + {n} x_{i}_{j} <= {n-1}")

        print("Bounds")
        for i in range(1, n):
            print(f"  1 <= u_{i} <= {n}")

        print("Binaries")
        for u, v in G.edges():
            print(f"  x_{u}_{v}\n  x_{v}_{u}")
        print("End")
        break # Only first graph by default

if __name__ == "__main__":
    run()