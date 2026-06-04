# Formulators (problem encoders)

Two kinds of encoders live here.

## Pure-Python encoders (no extra dependencies)

These run with only the Python packages in `../requirements.txt`:

- `hamilton_SAT.py`, `hamilton_SAT_v2.py`, `hamilton_log_SAT.py` — Hamiltonian-cycle CNF encodings
- `hamilton_ILP.py`, `circular_ILP.py` — ILP (LP) encodings
- `g6_splitter.py` — graph6 splitting helper

## C++ wrappers around the ba-graph library (build required)

The subdirectories

- `hamilton_baSAT/`, `hamilton_direct/`
- `circular_SAT/`, `circular_SAT_s6/`
- `circular_CPSAT/`, `circular_CPSAT_s6/`

are thin wrappers (each is a `main.cpp` plus a `Makefile`) around **ba-graph**,
a C++20 header-only graph-theory library. **ba-graph is a private research
library; it is not included in this archive and the compiled wrapper binaries
are not redistributed.** Only the wrapper source is provided. The ba-graph
library is available from its authors on request.

To build a wrapper, obtain the ba-graph library and point the Makefile at it
(it defaults to a sibling `../../ba-graph` checkout, overridable with
`BA_GRAPH_ROOT`):

```bash
cd circular_SAT
make BA_GRAPH_ROOT=/path/to/ba-graph
```

The resulting binary is what the experiment configurations in
`../experiments/` invoke (e.g. `../formulator/circular_SAT/circular_SAT`).
