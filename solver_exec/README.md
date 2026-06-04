# Solver binaries

The SAT/ILP solver binaries are **not** committed to this repository. Only the
small Python wrappers live here:

- `hamilton_cpsat.py` — OR-Tools CP-SAT Hamiltonicity solver
- `hamilton_Z3_from_raw.py` — Z3 SMT wrapper

Everything else is built from upstream. The default `src/config.json` expects the
following binaries in this directory (or on your `PATH`):

| config name | binary | upstream | license |
|:---|:---|:---|:---|
| `Glucose` | `solver_exec/glucose_static` | https://github.com/audemard/glucose | MIT-style |
| `isasat` | `solver_exec/isasat` | https://github.com/IsaFoL/IsaFoL | MIT |
| `yalsat` | `solver_exec/yalsat` | https://github.com/arminbiere/yalsat | MIT |
| `cadical_cmd` | `cadical` (PATH) | https://github.com/arminbiere/cadical | MIT |
| `kissat_cmd` | `kissat` (PATH) | https://github.com/arminbiere/kissat | MIT |
| `highs_cmd` | `highs` (PATH) | https://github.com/ERGO-Code/HiGHS | MIT |

## Obtaining the binaries

Build each solver from its upstream source (links above) and drop the resulting
binary in this directory under the name in the table, or install it on your
`PATH`.

The experiment configurations use a helper that automates this for the
competition builds — see `experiments/solver_exec/fetch_solvers.sh` (in the
[BP_solver_experiments](https://github.com/Fremal31/BP_solver_experiments)
submodule), which fetches and builds the solvers from their official sources.
