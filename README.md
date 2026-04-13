# Comparison of SAT Solvers in Combinatorics

A Python benchmarking framework for running multiple SAT and ILP solvers on combinatorial problems in parallel, with optional symmetry breaking, configurable metrics collection, CSV/JSON result export, and visualization.

> **Platform**: Linux only | **Python**: 3.9+

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
   - [Threading](#49-thread--core-configuration)
   - [Triplets & Execution Modes](#410-triplets--execution-modes)
5. [Component Parameter Reference](#5-component-parameter-reference)
6. [Output & Results](#6-output--results)
7. [Post-Run Plotting](#7-post-run-plotting)
8. [Testing](#8-testing)
9. [Troubleshooting](#9-troubleshooting)
10. [Dependencies](#10-dependencies)

---

## 1. Features

- Run multiple SAT/ILP solvers on combinatorial problems simultaneously
- Modular **Problem → Formulator → Breaker → Solver** pipeline
- Two execution modes: full cross-product (batch) or explicit triplet combinations
- Optional symmetry breaking via BreakID (or any compatible binary)
- Parallel execution with configurable thread count via `ThreadPoolExecutor`
- Per-process resource monitoring: CPU time, CPU usage, peak memory (via `psutil`)
- Regex-based solver output parsing using the Strategy design pattern
- Metrics extracted from both stdout and output file — no data lost when sources differ
- Configurable metric selection — only enabled metrics appear in the output
- Support for pre-encoded files (`.cnf`, `.lp`) that bypass the formulator step
- Results exported to both CSV and structured JSON (nested by problem → formulator → solver → breaker)
- Optional visualization: per-problem time bar charts, status stacked bar, CPU time box plot
- Included Hamiltonian cycle/path encoder for graph6 (`.g6`) files
- Structured logging with `--verbose` flag for debug output

---

## 2. Quick Start

### 2.1 Clone the Repository
```bash
git clone https://github.com/Fremal31/Comparison-of-SAT-solvers-in-combinatorics.git
cd Comparison-of-SAT-solvers-in-combinatorics
```

### 2.2 Setup Environment
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
```

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
                                                             ┌──────▼──────┐
                                                             │    Result   │
                                                             │ (.csv/.json)│
                                                             └─────────────┘
```

Alternatively, pre-encoded files can skip the formulator step entirely:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Pre-encoded │────▶│   Breaker   │────▶│    Solver   │
│ (.cnf / .lp)│     │  (optional) │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 3.2 Two-Phase Execution

**Phase 1 — Conversion**: Each unique (problem, formulator) pair is converted exactly once using `ThreadPoolExecutor`. Results are cached so that multiple solvers reuse the same converted file. Conversions respect the global timeout.

**Phase 2 — Solving**: All solver tasks (including optional symmetry breaking) run in parallel. Each task is independent and produces a `Result` object.

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
│   ├── main.py               # Entry point — CLI argument parsing (--config, --verbose), logging setup, experiment launch
│   ├── config_loader.py      # Config loading, validation, and parsing
│   ├── solver_manager.py     # Orchestrates conversion + solving pipeline
│   ├── generic_executor.py   # Low-level subprocess execution with resource monitoring
│   ├── runner.py             # Solver execution — delegates to GenericExecutor, maps Result, applies parser
│   ├── converter.py          # Problem → formula conversion (e.g., .g6 → .cnf)
│   ├── factory.py            # get_converter(), get_runner(); parser resolution
│   ├── cmd_builder.py        # build_cmd() — shared token resolution for options arrays
│   ├── parser_strategy.py    # Strategy pattern — SATparser, ILPparser, HiGHSParser, GenericParser
│   ├── metadata_registry.py  # Format type registry (SAT → .cnf, ILP → .lp, etc.)
│   ├── format_types.py       # Shared NamedTuples: FormatMetadata, ExperimentContext, ConversionTask, SolvingTask
│   ├── custom_types.py       # Dataclasses: Config, Result, RawResult, ExecConfig, FormulatorConfig, etc.
│   ├── graph.py              # log_results_to_csv, log_results_to_json, generate_plots, read_results_from_csv
│   └── config.json           # Default experiment configuration
├── formulator/               # Hamiltonian cycle/path CNF encoder (graph6 → DIMACS)
├── breakid/                  # BreakID symmetry breaker binary (Linux)
├── solver_exec/              # Pre-compiled SAT solver binaries (Linux)
├── examples/                 # Sample problem files (.g6, .cnf, .lp)
├── results/                  # Benchmark output files
│   ├── multi_solver_results.csv
│   ├── multi_solver_results.json
│   └── plots/                # Generated PNG plots (if visualization enabled)
├── tests/
│   ├── fixtures/             # Static test input files (.cnf, .lp, .g6)
│   ├── unit/                 # Unit tests (no subprocess, no filesystem)
│   ├── integration/          # Integration tests (require Linux solver binaries)
│   └── conftest.py           # Shared pytest fixtures
├── plot_metric.py            # Standalone post-run plotter for any numeric CSV column
├── conftest.py               # Root pytest config — adds src/ to sys.path
├── pytest.ini
├── requirements.txt
├── example_config.json
└── README.md
```

---

## 4. Configuration Guide

All experiment parameters are managed via `src/config.json`. You can specify a different config file via the `--config` / `-c` CLI flag (see [Quick Start](#24-run)).

### 4.1 Global Settings

| Key | Type | Default | Description |
|:---|:---|:---|:---|
| `timeout` | int | `5` | Maximum execution time per solver run in seconds |
| `max_threads` | int | `1` | Number of parallel experiments. Capped at `max(1, CPU_count - 1)` |
| `working_dir` | string | `/tmp/solver_comparison` | Temporary directory for generated formulas and logs |
| `delete_working_dir` | bool | `false` | If `true`, deletes `working_dir` at the start of each run. If `false` and the directory is non-empty, raises an error |
| `use_hardlink` | bool | `false` | If `true`, uses hardlinks instead of copies to prepare solver tasks. Falls back to copying if hardlinking fails. |
| `results_csv` | string | `./results/results.csv` | Path to the output CSV file |
| `results_json` | string | `./results/results.json` | Path to the output JSON file |
| `triplet_mode` | bool | `false` | `true` = explicit triplets only; `false` = full cross-product |

### 4.2 Metrics Measured

Boolean flags that control which columns appear in the output CSV. The JSON always contains all fields regardless of these settings.

| Category | Metric | Description |
|:---|:---|:---|
| **Metadata** | `problem` | Name of the problem file |
| | `formulator` | Name of the formulator used (`None` for without_converter) |
| | `breaker` | Name of the symmetry breaker (`None` if not used) |
| | `solver` | Name of the solver |
| | `parent_problem` | Original problem name before conversion |
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
| | `cores_used` | Which cores of the cpu were used (only if enabled in `thread_config`) |
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
| **ILP Internals** | `nodes` | Number of branch-and-bound nodes |
| | `iterations` | Number of LP iterations |
| | `objective` | Objective value |

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
| `type` | string | Yes | Output format: `SAT`, `ILP`, `SMT` |
| `cmd` | string | Yes | Path to the formulator script or system command |
| `enabled` | bool | No | Default: `false` |
| `output_mode` | string | No | How the formulator outputs results. Default: `stdout`. See [Output Modes](#output-modes) |
| `options` | array | No | Additional command-line flags. Supports `{input}` and `{output}` tokens (see [options tokens](#options-tokens)) |

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
| `type` | string | Yes | Logic format: `SAT` or `ILP` |
| `cmd` | string | Yes | System command or path to solver binary |
| `enabled` | bool | No | Default: `false` |
| `options` | array | No | Command-line flags. Supports `{input}` and `{output}` tokens (see [options tokens](#options-tokens)) |
| `parser` | string | No | Parser key for metric extraction. Falls back to type-based default if omitted |
| `threads` | int | No | Default: `1`, The number of threads a solver can use | 

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

> **Note**: If neither `{output}` nor `>` appears in `options`, stdout is captured via `subprocess.PIPE` and stored in `result.stdout`. This is the default and works for most solvers.

> **When both `>` and `{output}` are present**: `{output}` takes priority — the solver writes to the file itself via its flag, and `>` is ignored.

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

// No options — input appended automatically, stdout captured via PIPE
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

Optional plot generation after each run.

```json
"visualization": {
    "enabled": false,
    "output_dir": "./results/plots"
}
```

| Parameter | Type | Default | Description |
|:---|:---|:---|:---|
| `enabled` | bool | `false` | Whether to generate plots after the run |
| `output_dir` | string | `./results/plots` | Directory where PNG plots are saved |

Three plots are generated:
- **`time_<problem>.png`** — one per problem, stacked bar chart of mean wall-clock time per `formulator / solver / breaker` configuration. Shows solve time (blue), break time (red), and conversion time (gold) as separate stacked segments
- **`status_counts.png`** — stacked bar of SAT/UNSAT/TIMEOUT/ERROR counts per `formulator / solver / breaker` configuration
- **`cpu_time_distribution.png`** — box plot of CPU time distribution per solver

### 4.9 Thread & Core Configuration

```json
"thread_config": {
    "max_threads": 12,
    "allowed_cores": [0, 1, 2, 3, 4, 5, 6, 7],
    "ensure_cleanup_on_crash": true,  
}
```

| Parameter | Type | Default | Description |
|:---|:---|:---|:---|
| `max_threads` | int | `1` | How many threads to run in parallel |
| `allowed_cores` | List[int] | `null` | A list of CPU core IDs. Each parallel solver will be pinned to one of these cores using `taskset`. If threads > cores, IDs are recycled. If `null` won't use CPU pinning. **Important:** requires `util-linux` package [Dependencies](#10-dependencies) |
| `ensure_cleanup_on_crash` | bool | `false` | If `true`, uses `PR_SET_PDEATHSIG` and manual process tree termination to ensure no solver "zombies" remain if the manager crashes. |
> **Note**: To terminate we use `preexec_fn` which can rarely cause deadlock

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

**Default behaviors when optional fields are omitted**:
- `enabled`: `false` for solvers/formulators/breakers; `true` for files/without_converter
- `options`: empty list `[]`
- `output_mode`: `"stdout"`
- `parser`: auto-selected based on `type` field
- `threads`: `1`

---

## 6. Output & Results

### 6.1 CSV Output

Results are written to `results_csv`. Only metrics with `true` in `metrics_measured` appear as columns.

```csv
problem,formulator,solver,breaker,status,cpu_time,conflicts
hamilton_1,SAT_hamilton,kissat_cmd,breakid,SAT,0.42,1523
hamilton_1,SAT_hamilton,cadical_cmd,None,SAT,0.38,1401
```

### 6.2 JSON Output

Results are written to `results_json` in a hierarchical structure nested by problem → formulator → solver → breaker. When formulator or breaker is not set, `"None"` is used as the key. Each leaf contains the full result record with all fields.

```json
{
  "hamilton_1": {
    "SAT_hamilton": {
      "kissat_cmd": {
        "breakid": {
          "problem": "hamilton_1",
          "formulator": "SAT_hamilton",
          "solver": "kissat_cmd",
          "breaker": "breakid",
          "status": "SAT",
          "cpu_time": 0.42,
          "time": 0.51,
          "break_time": 0.09,
          "conflicts": 1523,
          "restarts": 12,
          "decisions": 4821,
          "exit_code": 10,
          "error": "",
          "stderr": ""
        },
        "None": {
          "problem": "hamilton_1",
          "formulator": "SAT_hamilton",
          "solver": "kissat_cmd",
          "breaker": "None",
          "status": "SAT",
          "cpu_time": 0.51,
          "time": 0.63,
          "break_time": 0.0,
          "conflicts": 1821,
          "restarts": 15,
          "decisions": 5102,
          "exit_code": 10,
          "error": "",
          "stderr": ""
        }
      }
    }
  },
  "hamilton_wc": {
    "None": {
      "Glucose": {
        "None": {
          "problem": "hamilton_wc",
          "formulator": "None",
          "solver": "Glucose",
          "breaker": "None",
          "status": "UNSAT",
          "cpu_time": 12.7,
          "time": 13.1,
          "break_time": 0.0,
          "conflicts": 98234,
          "exit_code": 20,
          "error": "",
          "stderr": ""
        }
      }
    }
  }
}
```

### 6.3 Plots

When `visualization.enabled` is `true`, PNG plots are saved to `visualization.output_dir`:

| File | Description |
|:---|:---|
| `time_<problem>.png` | One per problem — stacked bar of mean wall-clock time (solve + break + conversion) per configuration |
| `status_counts.png` | Stacked bar of result status counts per `formulator / solver / breaker` configuration |
| `cpu_time_distribution.png` | Box plot of CPU time distribution per solver across all problems |

### 6.4 Working Directory

All intermediate files are saved in `working_dir`:

```
/tmp/sat/
├── hamilton_1/
│   └── SAT_hamilton/
│       ├── hamilton_1.cnf
│       └── logs/
│           ├── hamilton_1.kissat_cmd_breakid.out
│           └── hamilton_1.cadical_cmd.out
└── hamilton_wc/
    └── NULL_FORMULATOR/
        └── logs/
            └── hamilton_wc.Glucose.out
```

### 6.5 Status Values

| Status | Meaning |
|:---|:---|
| `SAT` | Satisfiable solution found |
| `UNSAT` | Proven unsatisfiable |
| `TIMEOUT` | Solver exceeded the configured timeout |
| `ERROR` | Solver crashed or execution failed |
| `EXIT_ERROR` | Solver was terminated by a signal |
| `PARSER_ERROR` | Solver finished but the output parser crashed |
| `BREAKER_ERROR` | Symmetry breaker failed |
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
| `--output` | `./plots` | Output directory or file path (`.png`) |
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
Warning: Configured max_threads 12 exceeds logical CPU count 8. Using 7 instead.
```
Automatic — no action needed.

### All metrics show empty in CSV/JSON
**Cause**: No `parser` specified and the default parser doesn't match the solver's output format.
**Fix**: Set the correct parser key:
```json
"parser": "Kissat"
```
Available parser keys: `SAT`, `ILP`, `Kissat`, `Cadical`, `Glucose`, `Highs`

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
| `networkx` | ≥ 2.5 | Graph manipulation and graph6 parsing |
| `matplotlib` | ≥ 3.3.4 | Result visualization |
| `pandas` | latest | DataFrame construction for plots |
| `seaborn` | latest | Additional plot styling |
| `psutil` | latest | CPU and memory monitoring |
| `mypy` | ≥ 0.900 | Static type checking (development only) |

```bash
pip install -r requirements.txt
```

### 10.2 System Utilities
| Utility | Package | Purpose |
|:---|:---|:---|
| `taskset` | `util-linux` | Required for CPU pinning/affinity (`allowed_cores` in [Threading](#49-thread--core-configuration) |
| `libc.so.6` | `glibc` | Used via `ctypes` for `PR_SET_PDEATHSIG` cleanup logic. (`ensure_cleanup_on_crash` in [Threading](#49-thread--core-configuration) |

