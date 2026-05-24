# Comparison of SAT Solvers in Combinatorics

A Python benchmarking framework for running multiple SAT, ILP, SMT, and CP-SAT solvers on combinatorial problems in parallel, with optional symmetry breaking, parameter sweeps, configurable metrics collection, CSV/JSONL/JSON/HTML result export, and visualization.

> **Platform**: Linux only &nbsp;|&nbsp; **Python**: 3.9+ (CI-tested on 3.9 and 3.12; tooling targets 3.9)

---

## Table of Contents

1. [Features](#1-features)
2. [Quick Start](#2-quick-start)
3. [Project Structure](#3-architecture)
4. [Configuration Guide](#4-configuration-guide)
   - [Global Settings](#41-global-settings)
   - [Metrics Measured](#42-metrics-measured)
   - [Files](#43-files)
   - [Formulators](#44-formulators)
   - [Breakers](#45-breakers)
   - [Solvers](#46-solvers)
   - [Without Converter](#47-without-converter)
   - [Visualization](#48-visualization)
   - [Threading & Core Configuration](#49-thread--core-configuration)
   - [Triplets & Execution Modes](#410-triplets--execution-modes)
   - [Parameter Sweeps](#411-parameter-sweeps)
5. [Component Parameter Reference](#5-component-parameter-reference)
6. [Output & Results](#6-output--results)
7. [Post-Run Plotting](#7-post-run-plotting)
8. [Testing](#8-testing)
9. [Troubleshooting](#9-troubleshooting)
10. [Dependencies](#10-dependencies)

---

## 1. Features

- Run multiple **SAT, ILP, SMT, and CP-SAT** solvers on combinatorial problems simultaneously
- Modular **Problem → Formulator → Breaker → Solver** pipeline
- Two execution modes: full cross-product (batch) or explicit triplet combinations
- **Parameter sweeps** — turn one problem file into many instances by substituting `{key}` tokens into formulator command lines (e.g. circular colouring `p`, `q`)
- Optional symmetry breaking via BreakID (or any compatible binary)
- Parallel execution with a configurable thread pool, optional **CPU pinning** (`taskset`) and per-solver thread budgets
- Per-process resource monitoring: CPU time, CPU usage, peak memory (single-thread `psutil` monitor over the whole process tree)
- Regex-based solver output parsing using the Strategy design pattern
- Metrics extracted from both stdout and output file — no data lost when sources differ
- Configurable metric selection — only enabled metrics appear in the output
- Support for pre-encoded files (`.cnf`, `.lp`) that bypass the formulator step
- Results exported four ways: streaming **CSV** + **JSONL** (crash-safe, written as each run finishes), a structured **JSON** tree, and a self-contained **HTML report**
- A run summary with SAT/UNSAT **verdict per instance**, automatic **conflict detection** (solvers disagreeing), and a **PAR-2 leaderboard**
- Optional visualization: per-instance time-breakdown bars, status stacked bar, CPU-time box plot, and a cactus/survival plot
- Included Hamiltonian and circular-colouring encoders for graph6 (`.g6`) files
- Structured logging with `--verbose` flag for debug output

---

## 2. Quick Start

### 2.1 Clone the Repository
```bash
git clone https://github.com/Fremal31/Comparison-of-SAT-solvers-in-combinatorics.git
cd Comparison-of-SAT-solvers-in-combinatorics
```

### 2.2 Setup Environment

**Requires Python ≥ 3.9.** Check your interpreter first:
```bash
python3 --version    # must be 3.9 or newer
```
Then create and populate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2.3 Configure
Edit `src/config.json` to enable the solvers, problems, and metrics you need. See [Configuration Guide](#4-configuration-guide) for full details.

> **Note**: All relative paths in the config file (e.g. `./formulator/hamilton_SAT.py`, `./results/results.csv`) are resolved relative to the **config file's parent directory**, not the current working directory. When using `-c` to point to a config in a different location, make sure the paths inside it are correct relative to that location.

### 2.4 Run
```bash
# Using default config (src/config.json)
python3 src/main.py

# Using a custom config file
python3 src/main.py --config ./my_experiment.json
python3 src/main.py -c /tmp/quick_test.json

# Enable verbose (DEBUG) logging
python3 src/main.py -v
python3 src/main.py -c ./my_experiment.json --verbose
```

### 2.5 View Results
```bash
cat results/multi_solver_results.csv
cat results/multi_solver_results.json

# The HTML report is the easiest to read — open it in a browser
xdg-open results/multi_solver_results.html
```
The run also prints a summary table (per-instance verdicts + PAR-2 leaderboard) to the console at the end.

> **Warning**: The `working_dir` directory is **deleted** at the start of each run if `delete_working_dir` is set to `true`. Use a temporary path like `/tmp/sat` and never point it at an important directory.

---

## 3. Architecture

### 3.1 Pipeline Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Problem   │────▶│  Formulator │────▶│   Breaker   │────▶│    Solver   │
│  (.g6 file) │     │  (→ .cnf)   │     │  (optional) │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                                                             ┌──────────────────────┐
                                                             │        Result        │
                                                             │ (.csv/.jsonl/.json/   │
                                                             │   .html + summary)    │
                                                             └──────────────────────┘
```

Alternatively, pre-encoded files can skip the formulator step entirely:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Pre-encoded │────▶│   Breaker   │────▶│    Solver   │
│ (.cnf / .lp)│     │  (optional) │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 3.2 Two-Phase Execution

**Formulation Phase — Conversion**: Each unique (problem, formulator) pair is converted exactly once using `ThreadPoolExecutor`. Results are cached so that multiple solvers reuse the same converted file. Conversions respect the global timeout.

**Solving Phase**: All solver tasks (including optional symmetry breaking) run in parallel. Each task is independent and produces a `Result` object.

### 3.3 Execution Modes

| Mode | `triplet_mode` | Behavior |
|:---|:---|:---|
| **Batch** | `false` | Generates a full cross-product of all enabled files × formulators × solvers × breakers. Compatible types are matched automatically. |
| **Triplet** | `true` | Runs only the explicit combinations defined in the `triplets` array. If `solver` is omitted from a triplet, it is expanded to all compatible enabled solvers. |

### 3.4 Module Interaction Diagram

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full module interaction diagram and data flow summary.

---

### 3.5 Project Structure

```
.
├── src/
│   ├── main.py               # Entry point — CLI parsing (--config, --verbose), logging, output writers, run orchestration
│   ├── config_loader.py      # Config loading, validation, parsing, path resolution
│   ├── solver_manager.py     # Orchestrates the two-phase pipeline + working-directory setup
│   ├── triplet_generator.py  # Builds execution triplets (batch cross-product or explicit triplet mode)
│   ├── conversion_phase.py   # Formulation Phase — parallel (problem, formulator, parameters) conversion
│   ├── solving_phase.py      # Solving Phase — parallel solver execution (+ optional breaking)
│   ├── breaker.py            # SymmetryBreaker — runs a breaker binary before the solver
│   ├── core_allocator.py     # Thread-safe pool that hands out CPU cores for pinning
│   ├── converter.py          # Problem → formula conversion (stdout / stdout_multi / directory modes)
│   ├── runner.py             # Solver execution — delegates to GenericExecutor, maps Result, applies parser
│   ├── generic_executor.py   # Low-level subprocess execution + GlobalMonitor (CPU/memory)
│   ├── cmd_builder.py        # build_cmd() — token resolution ({input}/{output}/{key}/</>) for options arrays
│   ├── factory.py            # get_converter(), get_runner(); parser resolution
│   ├── parser_strategy.py    # Strategy pattern — SAT/ILP/HiGHS/SMT/CP-SAT/MiniSat parsers + registry
│   ├── metadata_registry.py  # Format type registry (SAT → .cnf, ILP → .lp, CPSAT → .cpsat, …)
│   ├── format_types.py       # Shared NamedTuples: FormatMetadata, ExperimentContext, ConversionTask, SolvingTask
│   ├── custom_types.py       # Dataclasses + enums: Config, Result, RawResult, Status, ExecConfig, …
│   ├── results_io.py         # Flattening + streaming CSV/JSONL writers + structured JSON dump
│   ├── run_summary.py        # Per-instance verdicts, conflict detection, PAR-2 leaderboard
│   ├── html_report.py        # Self-contained sortable/filterable HTML report
│   ├── plots.py              # Matplotlib plot generation (time breakdown, status, CPU box, cactus)
│   ├── utils.py              # Shared helpers (error Results, parameter-tag formatting)
│   └── config.json           # Default experiment configuration
├── formulator/               # Problem encoders (Hamiltonian, circular colouring, …) → DIMACS/LP/CP-SAT
├── breakid/                  # BreakID symmetry breaker binary (Linux)
├── solver_exec/              # Pre-compiled solver binaries / wrapper scripts (Linux)
├── examples/                 # Sample problem files (.g6, .cnf, .lp)
├── results/                  # Benchmark output files
│   ├── multi_solver_results.csv
│   ├── multi_solver_results.jsonl
│   ├── multi_solver_results.json
│   ├── multi_solver_results.html
│   └── plots/                # Generated SVG plots (if visualization enabled)
├── tests/
│   ├── fixtures/             # Static test input files (.cnf, .lp, .g6)
│   ├── unit/                 # Unit tests (no subprocess, no filesystem)
│   ├── integration/          # Integration tests (require Linux solver binaries)
│   └── conftest.py           # Shared pytest fixtures
├── plot_metric.py            # Standalone post-run plotter for any numeric CSV column
├── conftest.py               # Root pytest config — adds src/ to sys.path
├── pyproject.toml            # pytest / mypy / ruff configuration
├── requirements.txt
└── README.md
```

---

## 4. Configuration Guide

All experiment parameters are managed via `src/config.json`. You can specify a different config file via the `--config` / `-c` CLI flag (see [Quick Start](#24-run)).

### 4.1 Global Settings

| Key | Type | Default | Description |
|:---|:---|:---|:---|
| `timeout` | int | `5` | Maximum execution time per solver run in seconds |
| `working_dir` | string | `/tmp/solver_comparison` | Temporary directory for generated formulas and logs |
| `delete_working_dir` | bool | `false` | If `true`, deletes `working_dir` at the start of each run. If `false` and the directory is non-empty, raises an error |
| `use_hardlink` | bool | `false` | If `true`, uses hardlinks instead of copies to prepare solver tasks. Falls back to copying if hardlinking fails |
| `results_csv` | string | **required** | Path to the streaming CSV output file |
| `results_jsonl` | string | **required** | Path to the streaming JSONL output file (one result per line, crash-safe) |
| `results_json` | string | **required** | Path to the structured (nested) JSON output file |
| `results_html` | string | **required** | Path to the self-contained HTML report |
| `triplet_mode` | bool | `false` | `true` = explicit triplets only; `false` = full cross-product |

> All four `results_*` paths are **required** — there are no defaults, so a misconfigured run cannot silently dump results in an unexpected place. Parallel-execution settings live in the [`threading`](#49-thread--core-configuration) block (see §4.9), **not** at the top level — there is no top-level `max_threads`.

### 4.2 Metrics Measured

Boolean flags that control which metrics are extracted and reported. A metric flagged `false` is **skipped during parsing entirely** — its regex never runs, and it does not appear in the CSV or the incremental JSONL. The structured `results.json` always contains the full result for completeness.

The block accepts either a flat dict or a flat dict with one-level-deep groups. Groups are flattened on load, so they exist purely for readability — the names below stay unique. Both forms work:

```jsonc
"metrics_measured": {
    "status": true,
    "cpu_time": true,
    "conversion": {
        "conversion_time": true,
        "conversion_cpu_time": true,
        "conversion_memory_mb": true
    },
    "sat":  { "conflicts": true, "restarts": true, "decisions": true, "propagations": true },
    "ilp":  { "nodes": true, "iterations": true, "objective": true }
}
```

The `conversion` and `breaking` group names do not collide with the top-level metadata keys `breaker` (the breaker name) — pick group names that don't shadow flat metric names.

| Category | Metric | Description |
|:---|:---|:---|
| **Metadata** | `problem` | Name of the problem file (test case) |
| | `formulator` | Name of the formulator used (`None` for without_converter) |
| | `breaker` | Name of the symmetry breaker (`None` if not used) |
| | `solver` | Name of the solver |
| | `parent_problem` | Original problem name before conversion |
| | `parameters` | Instance parameter tag for parameter sweeps, e.g. `p=9,q=2` (empty if none) |
| **Status** | `status` | Result: `SAT`, `UNSAT`, `TIMEOUT`, `ERROR`, `UNKNOWN` |
| | `error` | Error message if execution failed |
| | `exit_code` | Process exit code |
| | `stderr` | Standard error output |
| **Solver Performance** | `time` | Solver wall-clock time in seconds |
| | `cpu_time` | Total CPU seconds consumed by the solver |
| | `cpu_usage_avg` | Average CPU usage percentage |
| | `cpu_usage_max` | Peak CPU usage percentage |
| | `memory_peak_mb` | Peak memory usage in MB |
| | `total_time` | Sum of conversion + breaking + solving time (computed property) |
| | `cores_used` | Which CPU cores the run was pinned to (only populated when `allowed_cores` is set; see [§4.9](#49-thread--core-configuration)) |
| **Conversion** | `conversion_time` | Wall-clock time spent on formulator conversion |
| | `conversion_cpu_time` | CPU time spent on formulator conversion |
| | `conversion_memory_mb` | Peak memory usage during conversion in MB |
| **Breaker** | `break_time` | Wall-clock time spent on symmetry breaking |
| | `break_cpu_time` | CPU time spent on symmetry breaking |
| | `break_memory_mb` | Peak memory usage during symmetry breaking in MB |
| **SAT Internals** | `restarts` | Number of solver restarts |
| | `conflicts` | Number of conflicts encountered |
| | `decisions` | Number of decisions made |
| | `propagations` | Number of propagations performed |
| | `clauses` | Number of clauses |
| | `learned` | Number of learned clauses |
| **CP-SAT Internals** | `branches` | Number of search branches (OR-Tools CP-SAT) |
| | `wall_time` | CP-SAT-reported wall time |
| **ILP Internals** | `nodes` | Number of branch-and-bound nodes |
| | `iterations` | Number of LP iterations |
| | `objective` | Objective value |

> Which internal metrics are actually populated depends on the solver's `parser` (see [§4.6](#46-solvers)). Names must match the keys the parser emits; a metric flagged `true` whose parser never produces it simply stays empty.

### 4.3 Files

Problem files to be converted by a formulator before solving. The `path` can point to a single file or a directory — if it points to a directory, all files in it are expanded into individual problem entries automatically.

```json
"files": {
    "hamilton_1": {"path": "./examples/hamilton_small.g6"},
    "hamilton_2": {"path": "./examples/graph1.g6", "enabled": false},
    "all_graphs": {"path": "./examples/graphs/"}
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `path` | string | Yes | Path to a problem file or a directory of problem files |
| `enabled` | bool | No | Default: `true` |
| `parameters` | array of objects | No | Parameter sweep — each object turns the file into one independent instance. See [Parameter Sweeps](#411-parameter-sweeps). Default: a single instance with no parameters |

**Directory expansion**: When `path` points to a directory, each file in it becomes a separate problem entry named `{config_name}_{file_stem}`. For example, if `"all_graphs"` points to a directory containing `small.g6` and `large.g6`, two entries are created: `all_graphs_small` and `all_graphs_large`. Subdirectories are ignored. The `enabled` flag is propagated to all expanded entries.

### 4.4 Formulators

Scripts that convert raw problem files into solver-ready formats.

```json
"formulators": {
    "SAT_hamilton": {
        "type": "SAT",
        "cmd": "./formulator/formulator.py",
        "enabled": true,
        "options": ["-", "<", "{input}"],
        "output_mode": "stdout"
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `type` | string | Yes | Output format: `SAT`, `ILP`, `SMT`, `CPSAT`, or `G6` |
| `cmd` | string | Yes | Path to the formulator script or system command |
| `enabled` | bool | No | Default: `false` |
| `output_mode` | string | No | How the formulator outputs results. Default: `stdout`. See [Output Modes](#output-modes) |
| `options` | array | No | Additional command-line flags. Supports `{input}`, `{output}`, and `{key}` parameter tokens (see [options tokens](#options-tokens) and [Parameter Sweeps](#411-parameter-sweeps)) |

#### Output Modes

The `output_mode` field controls how the formulator delivers its output:

| Mode | Behavior |
|:---|:---|
| `stdout` | **(default)** The formulator prints a single formula to stdout. The framework captures it and writes it to one output file. Produces one TestCase per problem. |
| `stdout_multi` | The formulator prints multiple formulas to stdout, separated by blank lines. Each formula is split into a separate file and becomes its own TestCase. Output files are named `{problem}_{index}{suffix}`. |
| `directory` | The formulator writes output files directly to a directory. The `{output}` token in `options` is resolved to the output directory path. Each file with the correct suffix (e.g. `.cnf`) in the directory becomes a TestCase. |

**Examples:**

```json
// Single formula to stdout (default)
"SAT_hamilton": {
    "type": "SAT",
    "cmd": "./formulator/hamilton_SAT.py",
    "output_mode": "stdout",
    "options": ["{input}"]
}

// Multiple formulas from stdout (e.g. --all flag produces one CNF per graph)
"SAT_hamilton_all": {
    "type": "SAT",
    "cmd": "./formulator/hamilton_SAT.py",
    "output_mode": "stdout_multi",
    "options": ["{input}", "--all"]
}

// Formulator writes files to a directory
"my_encoder": {
    "type": "SAT",
    "cmd": "./formulator/batch_encoder.py",
    "output_mode": "directory",
    "options": ["{input}", "-o", "{output}"]
}
```

### 4.5 Breakers

Symmetry breaking tools applied to the formula before solving.

```json
"breakers": {
    "breakid": {
        "type": "SAT",
        "cmd": "./breakid/breakid",
        "enabled": false,
        "options": []
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `type` | string | Yes | Must match the solver type (e.g., `SAT`) |
| `cmd` | string | Yes | Path to the breaker binary |
| `enabled` | bool | No | Default: `false` |
| `options` | array | No | Additional flags. Supports `{input}` and `{output}` tokens (see [options tokens](#options-tokens)) |
| `threads` | int | No | Default: `1`, The number of threads a breaker can use | 

### 4.6 Solvers

```json
"solvers": {
    "kissat_cmd": {
        "type": "SAT",
        "cmd": "kissat",
        "enabled": true,
        "options": ["-n", "{input}"],
        "parser": "Kissat"
    },
    "highs_cmd": {
        "type": "ILP",
        "cmd": "highs",
        "enabled": true,
        "parser": "Highs"
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `type` | string | Yes | Logic format: `SAT`, `ILP`, `SMT`, `CPSAT`, or `G6` |
| `cmd` | string | Yes | System command or path to solver binary |
| `enabled` | bool | No | Default: `false` |
| `options` | array | No | Command-line flags. Supports `{input}` and `{output}` tokens (see [options tokens](#options-tokens)) |
| `parser` | string | No | Parser key for metric extraction (case-insensitive). Falls back to the type-based default if omitted |
| `threads` | int | No | Default: `1`. Number of threads/cores this solver may use. Validated against the core pool (see [§4.9](#49-thread--core-configuration)) |

**Available `parser` keys**: `SAT`, `ILP`, `SMT`, `CPSAT`, `Kissat`, `Cadical`, `Glucose`, `Lingeling`, `MiniSat`, `Highs`, `Default`. The first four match a format type; the solver-named keys map to the right output dialect (e.g. `Kissat`/`Cadical`/`Glucose` all use the DIMACS SAT parser, `MiniSat` reads a bare `SAT`/`UNSAT` line). `Default` extracts no status or metrics. To add your own, see [ARCHITECTURE.md §10.1](ARCHITECTURE.md#10-extending-the-framework).

#### Options Tokens

The `options` array for solvers, breakers, and formulators supports special tokens and control characters that control how the input file is passed and where output is captured.

**Input tokens**

| Token / Value | Behavior |
|:---|:---|
| `{input}` | Replaced with the absolute path to the input file as a command-line argument |
| `<` | Opens the input file and feeds it to the process via stdin. Any `{input}` token in `options` is suppressed from the argument list — stdin handles the input instead |

> **Note**: If neither `{input}` nor `<` appears anywhere in `options`, `{input}` is automatically appended to the end of the argument list. The position of `<` relative to `{input}` does not matter.

**Output tokens**

| Token / Value | Behavior |
|:---|:---|
| `{output}` | Replaced with the absolute path to the output log file as a command-line argument (e.g. `-o {output}`). The solver writes to the file directly via its own flag |
| `>` | The framework redirects process stdout to the output file via a pipe |

> **Note**: If neither `{output}` nor `>` appears in `options`, the framework **redirects the solver's stdout to the per-run output file by default** (it does *not* keep it only in memory). This guarantees every run leaves a log on disk and keeps large solver output from being buffered in RAM. The parser then reads that file. This is the default and works for most solvers.

> **When both `>` and `{output}` are present**: `{output}` takes priority — the solver writes to the file itself via its flag, and `>` is ignored.

**Parameter tokens** — any `{key}` token (other than `{input}`/`{output}`) is substituted from the instance's parameter dict; see [Parameter Sweeps](#411-parameter-sweeps). An unresolved `{key}` left after substitution raises a configuration error rather than being passed to the solver verbatim.

**Examples**

```json
// Solver reads input as a path argument, output captured from stdout
"options": ["-n", "{input}"]

// Solver reads input from stdin (e.g. formulator piping CNF)
"options": ["-", "<"]

// Solver writes output to a file via its own flag
"options": ["-o", "{output}"]

// Framework redirects stdout to the output file
"options": [">"]

// Solver reads from stdin and framework redirects stdout to file
"options": ["<", "{input}", ">"]

// No options — input appended automatically, stdout redirected to the output file
"options": []
```

### 4.7 Without Converter

Pre-encoded files that skip the formulator step entirely.

```json
"without_converter": {
    "hamilton_wc": {
        "path": "./examples/hamilton/hamilton_biggood2.txt",
        "type": "SAT",
        "enabled": true
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `path` | string | Yes | Path to the pre-encoded file |
| `type` | string | No | Format type (`SAT`, `ILP`). Auto-detected from file extension (`.cnf` → `SAT`, `.lp` → `ILP`). Required for unrecognized extensions (e.g. `.txt`) |
| `enabled` | bool | No | Default: `true` |

### 4.8 Visualization

Optional plot generation after each run. Plots are written as **SVG** and referenced from the HTML report.

```json
"visualization": {
    "enabled": false,
    "output_dir": "./results/plots",
    "per_problem": true,
    "comparison": true
}
```

| Parameter | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | bool | `false` | Whether to generate plots after the run |
| `output_dir` | string | `./results/plots` | Directory where SVG plots are saved |
| `per_problem` | bool | `true` | Emit one per-instance time-breakdown chart (embedded as expandable rows in the HTML verdict table) |
| `comparison` | bool | `true` | Emit the cross-solver charts (status counts, CPU-time box plot, cactus plot) |

Plots generated (SVG):
- **`time_<instance>.svg`** — one per instance `(parent_problem, parameters)`: horizontal stacked bar of wall-clock time per `formulator / solver / breaker`, stacking solve time (blue), break time (red), and conversion time (gold); a dashed line marks the timeout. *(per_problem)*
- **`status_counts.svg`** — stacked bar of result-status counts per configuration. *(comparison)*
- **`cpu_time_distribution.svg`** — box plot of CPU-time distribution per solver, over solved runs. *(comparison)*
- **`cactus.svg`** — cactus / survival plot: instances solved (x) vs solve time (y) per configuration — the SAT-competition comparison view. *(comparison)*

### 4.9 Thread & Core Configuration

Parallel-execution and monitoring settings live under the top-level **`threading`** key (note: the key is `threading`, not `thread_config`):

```json
"threading": {
    "max_threads": 12,
    "allowed_cores": [0, 1, 2, 3, 4, 5, 6, 7],
    "ensure_cleanup_on_crash": false,
    "monitor_poll_interval": 0.5
}
```

| Parameter | Type | Default | Description |
|:---|:---|:---|:---|
| `max_threads` | int | `0` | Worker threads (one subprocess each) run in parallel. `0`/omitted falls back to `max(1, CPU_count - 1)`. See the resolution rules below. |
| `allowed_cores` | list[int] | `null` | CPU core IDs to pin workers to via `taskset`. When set, `max_threads` is capped at `len(allowed_cores)` and each running solver is pinned to one (or `threads`) of these cores. `null` disables pinning. **Requires `util-linux`** — see [Dependencies](#10-dependencies). |
| `ensure_cleanup_on_crash` | bool | `false` | If `true`, sets `PR_SET_PDEATHSIG` on spawned solvers so the kernel kills them if the framework dies before reaping them. |
| `monitor_poll_interval` | float | `0.5` | Seconds between resource-monitor sampling cycles (CPU time / peak memory). Smaller = finer memory-spike resolution but higher `/proc` overhead; larger = the opposite. Must be `> 0`. |

**How `max_threads` is resolved:**
- `allowed_cores` **set** → `max_threads` is capped at `len(allowed_cores)` (one worker per pinned core). `0`/omitted means "use all allowed cores".
- `allowed_cores` is **`null`** → `max_threads` is used as configured. `0` or less → `max(1, CPU_count - 1)`. A value above the logical CPU count is allowed but logs an "oversubscribed" warning.

**Per-solver/breaker `threads`:** a solver or breaker with `threads: N` reserves `N` cores from the pool for the duration of its run (via the core allocator). The loader rejects any enabled component whose `threads` exceeds the core pool. Without `allowed_cores`, `threads` is informational (no pinning).

> **Note**: the optional `preexec_fn` (used to set `PR_SET_PDEATHSIG` when `ensure_cleanup_on_crash` is enabled) can in rare cases deadlock. See [ARCHITECTURE.md](ARCHITECTURE.md) for the subprocess-lifecycle details.

### 4.10 Triplets & Execution Modes

#### Batch Mode (`triplet_mode: false`)

Full cross-product of all enabled components, matched by type compatibility.

#### Triplet Mode (`triplet_mode: true`)

Only explicitly defined combinations run. The `solver` field is optional — if omitted, the triplet is automatically expanded to all enabled solvers whose type matches the formulator or pre-encoded file type:

```json
"triplets": [
    {
        "problem": "hamilton_1",
        "formulator": "SAT_hamilton",
        "breaker": "breakid",
        "solver": "kissat_cmd"
    },
    {
        "without_converter": "hamilton_wc",
        "solver": "Glucose"
    }
]
```

The `breaker` and `solver` fields are optional. Use either `problem` + `formulator`, or `without_converter` — not both.

**Solver expansion examples:**

```json
// Explicit — runs only kissat_cmd
{"problem": "hamilton_1", "formulator": "SAT_hamilton", "solver": "kissat_cmd"}

// All compatible enabled solvers, no breaker
{"problem": "hamilton_1", "formulator": "SAT_hamilton"}

// All compatible enabled solvers, each with breakid
{"problem": "hamilton_1", "formulator": "SAT_hamilton", "breaker": "breakid"}

// Pre-encoded file, all compatible enabled solvers
{"without_converter": "hamilton_wc"}
```

> **Note**: All component names must be unique across the entire config (files, formulators, solvers, breakers, without_converter). Duplicate names will cause a validation error at startup.

---

### 4.11 Parameter Sweeps

A single problem file can be expanded into several independent **instances** by attaching a `parameters` array to its `files` entry. Each object in the array is one instance; its key/value pairs are substituted into the formulator's `options` wherever a matching `{key}` token appears.

```json
"files": {
    "petersen": {
        "path": "./examples/petersen.g6",
        "parameters": [
            {"p": 5, "q": 2},
            {"p": 7, "q": 2},
            {"p": 9, "q": 4}
        ]
    }
},
"formulators": {
    "circular_SAT": {
        "type": "SAT",
        "cmd": "./formulator/circular_SAT.py",
        "enabled": true,
        "options": ["{input}", "--p", "{p}", "--q", "{q}"]
    }
}
```

This runs the `circular_SAT` formulator three times on `petersen.g6` — once per `(p, q)` pair — producing three independent instances that are solved and reported separately.

**Behavior:**
- A file with no `parameters` (or an empty list) is a single instance with no parameters — exactly the legacy behavior.
- Each instance gets its own working-directory subtree (e.g. `petersen@p=5,q=2/...`) so generated files never collide.
- The parameter tag (`p=5,q=2`, keys sorted alphabetically) appears in the `parameters` column of every output and is the key the [run summary](#62-run-summary) groups by — so different encodings of the *same* `(problem, parameters)` instance are compared against each other.
- Any `{key}` token left unresolved after substitution (a typo, or a parameter the caller forgot to declare) raises a configuration error rather than being passed through to the solver.
- Parameters are available to both formulator and solver `options`, though solvers usually don't reference them.

---

## 5. Component Parameter Reference

| Parameter | Solvers | Formulators | Breakers | Files | Without Converter |
|:---|:---:|:---:|:---:|:---:|:---:|
| `cmd` | ✅ Required | ✅ Required | ✅ Required | — | — |
| `type` | ✅ Required | ✅ Required | ✅ Required | — | Optional |
| `path` | — | — | — | ✅ Required | ✅ Required |
| `enabled` | Optional | Optional | Optional | Optional | Optional |
| `options` | Optional | Optional | Optional | — | — |
| `output_mode` | — | Optional | — | — | — |
| `parser` | Optional | — | Optional | — | — |
| `threads` | Optional | — | Optional | — | — |
| `parameters` | — | — | — | Optional | — |

**Default behaviors when optional fields are omitted**:
- `enabled`: `false` for solvers/formulators/breakers; `true` for files/without_converter
- `options`: empty list `[]`
- `output_mode`: `"stdout"`
- `parser`: auto-selected based on `type` field
- `threads`: `1`
- `parameters`: none — a single instance with no parameters

---

## 6. Output & Results

Every run writes four artifacts (all four paths are required config keys). **CSV and JSONL are streamed** — each result is written and flushed the moment it finishes, so a crash or `Ctrl-C` still leaves partial results on disk. The structured JSON and the HTML report are written once at the end, and a summary is printed to the console.

### 6.1 CSV Output

Streamed to `results_csv`. Only metrics with `true` in `metrics_measured` appear as columns.

```csv
problem,formulator,solver,breaker,status,cpu_time,conflicts
hamilton_1,SAT_hamilton,kissat_cmd,breakid,SAT,0.42,1523
hamilton_1,SAT_hamilton,cadical_cmd,None,SAT,0.38,1401
```

### 6.2 Run Summary

At the end of every run the framework aggregates all results by instance `(parent_problem, parameters)` and prints a summary to the console (also rendered at the top of the HTML report):

- **Verdict per instance** — `SAT`, `UNSAT`, `CONFLICT`, or `UNKNOWN`, derived from what the solvers concluded. Grouping by `parent_problem` means different *encodings* of the same instance (e.g. a SAT CNF and a CP-SAT model) are compared against each other.
- **Conflict detection** — if one solver/encoding reports SAT and another reports UNSAT for the same instance, it is flagged as a `CONFLICT` (a correctness alarm): the process logs an error and the HTML banner turns red.
- **PAR-2 leaderboard** — per method (`solver [formulator] +breaker`), the SAT-Competition PAR-2 metric: the mean over all runs of `total_time` if solved, else `2 × timeout`. Lower is better. `total_time = conversion + symmetry breaking + solve`.

### 6.3 JSONL Output

Streamed to `results_jsonl`, one JSON object per line, mirroring the CSV's column filter (only enabled metrics). Ideal for `jq`/pandas post-processing and for recovering partial results from an interrupted run.

### 6.4 JSON Output

Written to `results_json` as a hierarchical tree nested by problem → formulator → solver → breaker → **parameters**. When formulator or breaker is not set, `"None"` is used as the key; the parameters level uses `"none"` for instances with no parameters. Each leaf holds the full result record (always complete, regardless of `metrics_measured`).

```json
{
  "hamilton_1": {
    "SAT_hamilton": {
      "kissat_cmd": {
        "breakid": {
          "none": {
            "problem": "hamilton_1",
            "parent_problem": "hamilton_1",
            "formulator": "SAT_hamilton",
            "solver": "kissat_cmd",
            "breaker": "breakid",
            "parameters": "",
            "status": "SAT",
            "cpu_time": 0.42,
            "time": 0.51,
            "break_time": 0.09,
            "conflicts": 1523,
            "exit_code": 10,
            "error": "",
            "stderr": ""
          }
        }
      }
    }
  }
}
```

### 6.5 HTML Report

Written to `results_html`: a single self-contained file (no external assets) with:

- the **run summary** (verdict table, conflict banner, PAR-2 leaderboard, how the run ended, total wall-clock time);
- a **sortable, filterable results table** that loads sorted by status (failures first), with a free-text filter and per-status filter chips;
- the comparison **plots**, plus per-instance time-breakdown charts embedded as expandable rows in the verdict table.

It respects the browser's light/dark color scheme. This is usually the easiest artifact to read — open it in a browser.

### 6.6 Plots

When `visualization.enabled` is `true`, SVG plots are saved to `visualization.output_dir`:

| File | Description | Class |
|:---|:---|:---|
| `time_<instance>.svg` | One per instance `(parent_problem, parameters)` — stacked bar of wall-clock time (solve + break + conversion) per configuration | per_problem |
| `status_counts.svg` | Stacked bar of result status counts per `formulator / solver / breaker` configuration | comparison |
| `cpu_time_distribution.svg` | Box plot of CPU-time distribution per solver, over solved runs | comparison |
| `cactus.svg` | Cactus / survival plot: instances solved vs solve time per configuration | comparison |

### 6.7 Working Directory

All intermediate files are saved under `working_dir`. Each `(problem, parameters)` instance gets its own subtree; parameter-free instances keep the plain `problem/` layout, while a sweep adds a `@`-tagged directory:

```
/tmp/sat/
├── hamilton_1/                         ← no parameters
│   └── SAT_hamilton/
│       ├── hamilton_1.cnf
│       └── logs/
│           ├── hamilton_1.kissat_cmd_breakid.out
│           └── hamilton_1.cadical_cmd.out
├── petersen@p=5,q=2/                    ← one parameter-sweep instance
│   └── circular_SAT/
│       ├── petersen.cnf
│       └── logs/
│           └── petersen.kissat_cmd.out
└── hamilton_wc/
    └── NULL_FORMULATOR/
        └── logs/
            └── hamilton_wc.Glucose.out
```

### 6.8 Status Values

| Status | Meaning |
|:---|:---|
| `SAT` | Satisfiable solution found |
| `UNSAT` | Proven unsatisfiable |
| `TIMEOUT` | Solver exceeded the configured timeout |
| `ERROR` | Solver crashed or execution failed |
| `EXIT_ERROR` | Solver was terminated by a signal |
| `MISSING_OUTPUT` | Expected output file was not produced |
| `PARSER_ERROR` | Solver finished but the output parser crashed |
| `BREAKER_ERROR` | Symmetry breaker failed |
| `OK` | Run completed (used for components with no SAT/UNSAT verdict) |
| `UNKNOWN` | Solver finished but status could not be determined |

---

## 7. Post-Run Plotting

The `plot_metric.py` script generates bar charts or box plots for any numeric column from the results CSV. By default it generates one plot per problem.

```bash
# Bar chart of memory per config (one per problem)
python3 plot_metric.py results/multi_solver_results.csv memory_peak_mb

# Box plot of CPU time per solver (combined across problems)
python3 plot_metric.py results/multi_solver_results.csv cpu_time --plot box --group-by solver --no-per-problem

# Multiple metrics side by side
python3 plot_metric.py results/multi_solver_results.csv conversion_time break_time time

# Compare memory across all pipeline phases
python3 plot_metric.py results/multi_solver_results.csv conversion_memory_mb break_memory_mb memory_peak_mb --group-by solver

# Custom title and output directory
python3 plot_metric.py results/multi_solver_results.csv conflicts --title "Conflicts" --output ./my_plots
```

| Flag | Default | Description |
|:---|:---|:---|
| `csv` | — | Path to results CSV (required) |
| `metrics` | — | One or more numeric column names to plot (required) |
| `--plot` | `bar` | Plot type: `bar` (mean per group) or `box` (distribution) |
| `--group-by` | `config` | Column to group by: `solver`, `config`, `formulator`, or any CSV column. `config` is a synthetic `formulator / solver / breaker` column |
| `--per-problem` | on | Generate one plot per problem (default) |
| `--no-per-problem` | — | Generate a single combined plot across all problems |
| `--output` | `./plots` | Output directory or file path |
| `--format` | `svg` | Output file format: `svg`, `png`, or `pdf` |
| `--title` | auto | Custom plot title |

---

## 8. Testing

```bash
# Run all unit tests
python3 -m pytest tests/unit/ -v

# Run integration tests (Linux only, requires solver binaries)
python3 -m pytest tests/integration/ -v

# Run only unit tests (skip integration)
python3 -m pytest -m "not integration"

# Run a specific test file
python3 -m pytest tests/unit/test_cmd_builder.py -v
```

### CI

Unit tests run automatically on every push and pull request to `main`/`master` via GitHub Actions (`.github/workflows/tests.yml`). Integration tests are excluded from CI since they require solver binaries not available on the GitHub runner.

For details on adding tests for new parsers and format types, see [ARCHITECTURE.md](ARCHITECTURE.md#10-extending-the-framework).

---

## 9. Troubleshooting

### Solver binary not found
```
FileNotFoundError: Solver command or path not found: kissat
```
**Fix**: Install system-wide or use a relative path:
```json
"cmd": "./solver_exec/kissat"
```

### Permission denied on solver/formulator
```
PermissionError: ... is not executable
```
**Fix**:
```bash
chmod +x solver_exec/kissat
chmod +x formulator/formulator.py
```

### Working directory is not empty
```
ValueError: Working directory /tmp/sat is not empty. ...
```
**Fix**: Either use a fresh directory or set `delete_working_dir` to `true`:
```json
"delete_working_dir": true
```

### max_threads exceeds CPU count
```
Requested max_threads 12 exceeds logical CPU count 8; running oversubscribed.
```
Informational — `max_threads` is honoured as configured (no cap) when `allowed_cores` is `null`. If `allowed_cores` is set, `max_threads` is instead capped at `len(allowed_cores)` and a "Capping" warning is logged.

### All metrics show empty in CSV/JSON
**Cause**: No `parser` specified and the default parser doesn't match the solver's output format.
**Fix**: Set the correct parser key:
```json
"parser": "Kissat"
```
Available parser keys (case-insensitive): `SAT`, `ILP`, `SMT`, `CPSAT`, `Kissat`, `Cadical`, `Glucose`, `Lingeling`, `MiniSat`, `Highs`, `Default`

### Solver returns UNKNOWN status
1. Verify the solver produces status lines (e.g., `s SATISFIABLE`)
2. Check that `options` correctly captures the output — use `>` to redirect stdout or `{output}` to write to a file
3. Create a custom parser if the solver uses non-standard output

### Pre-encoded file type not detected
```
ValueError: ... has an unknown type and no 'type' field specified.
```
**Fix**: Specify `type` explicitly when the file extension is not recognized (e.g. `.txt`):
```json
"hamilton_wc": {"path": "./my_file.txt", "type": "SAT"}
```
Files with standard extensions (`.cnf`, `.lp`) are detected automatically.

---

## 10. Dependencies

### 10.1 Python packages

| Package | Min Version | Purpose |
|:---|:---|:---|
| `networkx` | ≥ 2.5 | Graph manipulation and graph6 parsing (used by the bundled encoders) |
| `matplotlib` | ≥ 3.9 | Result visualization (3.9 is the last release supporting Python 3.9) |
| `pandas` | latest | DataFrame construction for plots |
| `seaborn` | latest | Additional plot styling |
| `psutil` | latest | CPU and memory monitoring |
| `pytest` | latest | Test runner (development only) |
| `mypy` | ≥ 0.900 | Static type checking (development only) |
| `pandas-stubs` | latest | Type stubs for pandas (development only) |
| `ruff` | latest | Linting (development only) |

> The core framework (running solvers, collecting metrics, CSV/JSONL/JSON/HTML output) needs only `psutil`. `matplotlib`/`pandas`/`seaborn` are imported lazily and only when `visualization.enabled` is `true` — a run without them still produces every output except the plots.

```bash
pip install -r requirements.txt
```

### 10.2 System Utilities
| Utility | Package | Purpose |
|:---|:---|:---|
| `taskset` | `util-linux` | Required for CPU pinning/affinity (`allowed_cores` in [Threading](#49-thread--core-configuration) |
| `libc.so.6` | `glibc` | Used via `ctypes` for `PR_SET_PDEATHSIG` cleanup logic. (`ensure_cleanup_on_crash` in [Threading](#49-thread--core-configuration) |

