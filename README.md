# Comparison of SAT Solvers in Combinatorics

A Python benchmarking framework for running multiple SAT and ILP solvers on combinatorial problems in parallel, with optional symmetry breaking, configurable metrics collection, CSV/JSON result export, and visualization.

> **Platform**: Linux only

---

## Table of Contents

1. [Features](#1-features)
2. [Quick Start](#2-quick-start)
3. [Architecture](#3-architecture)
4. [Project Structure](#4-project-structure)
5. [Configuration Guide](#5-configuration-guide)
   - [Global Settings](#51-global-settings)
   - [Metrics Measured](#52-metrics-measured)
   - [Files](#53-files)
   - [Formulators](#54-formulators)
   - [Breakers](#55-breakers)
   - [Solvers](#56-solvers)
   - [Without Converter](#57-without-converter)
   - [Visualization](#58-visualization)
   - [Triplets & Execution Modes](#59-triplets--execution-modes)
6. [Component Parameter Reference](#6-component-parameter-reference)
7. [Adding a New Solver](#7-adding-a-new-solver)
8. [Adding a New Formulator](#8-adding-a-new-formulator)
9. [Adding a New Format Type](#9-adding-a-new-format-type)
10. [Hamiltonian Cycle Formulator](#10-hamiltonian-cycle-formulator)
11. [Output & Results](#11-output--results)
12. [Post-Run Plotting](#12-post-run-plotting)
13. [Module Reference](#13-module-reference)
14. [Testing](#14-testing)
15. [Troubleshooting](#15-troubleshooting)
16. [Dependencies](#16-dependencies)

---

## 1. Features

- Run multiple SAT/ILP solvers on combinatorial problems simultaneously
- Modular **Problem → Formulator → Breaker → Solver** pipeline
- Two execution modes: full cross-product (batch) or explicit triplet combinations
- Optional symmetry breaking via BreakID (or any compatible binary)
- Parallel execution with configurable thread count via `ProcessPoolExecutor`
- Per-process resource monitoring: CPU time, CPU usage, peak memory (via `psutil`)
- Regex-based solver output parsing using the Strategy design pattern
- Configurable metric selection — only enabled metrics appear in the output
- Support for pre-encoded files (`.cnf`, `.lp`) that bypass the formulator step
- Results exported to both CSV and structured JSON (nested by problem → formulator → solver → breaker)
- Optional visualization: per-problem time bar charts, status stacked bar, CPU time box plot
- Included Hamiltonian cycle/path encoder for graph6 (`.g6`) files

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
Edit `src/config.json` to enable the solvers, problems, and metrics you need. See [Configuration Guide](#5-configuration-guide) for full details.

### 2.4 Run
```bash
# Using default config (src/config.json)
python3 src/main.py

# Using a custom config file
python3 src/main.py --config ./my_experiment.json
python3 src/main.py -c /tmp/quick_test.json
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

**Phase 1 — Conversion**: Each unique (problem, formulator) pair is converted exactly once using `ProcessPoolExecutor`. Results are cached so that multiple solvers reuse the same converted file.

**Phase 2 — Solving**: All solver tasks (including optional symmetry breaking) run in parallel. Each task is independent and produces a `Result` object.

### 3.3 Execution Modes

| Mode | `triplet_mode` | Behavior |
|:---|:---|:---|
| **Batch** | `false` | Generates a full cross-product of all enabled files × formulators × solvers × breakers. Compatible types are matched automatically. |
| **Triplet** | `true` | Runs only the explicit combinations defined in the `triplets` array. If `solver` is omitted from a triplet, it is expanded to all compatible enabled solvers. |

### 3.4 Module Interaction Diagram

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full module interaction diagram and data flow summary.

---

## 4. Project Structure

```
.
├── src/
│   ├── main.py               # Entry point — CLI argument parsing, experiment launch
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

## 5. Configuration Guide

All experiment parameters are managed via `src/config.json`. You can specify a different config file via the `--config` / `-c` CLI flag (see [Quick Start](#24-run)).

### 5.1 Global Settings

| Key | Type | Default | Description |
|:---|:---|:---|:---|
| `timeout` | int | `5` | Maximum execution time per solver run in seconds |
| `max_threads` | int | `1` | Number of parallel experiments. Capped at `max(1, CPU_count - 1)` |
| `working_dir` | string | `/tmp/solver_comparison` | Temporary directory for generated formulas and logs |
| `delete_working_dir` | bool | `false` | If `true`, deletes `working_dir` at the start of each run. If `false` and the directory is non-empty, raises an error |
| `results_csv` | string | `./results/results.csv` | Path to the output CSV file |
| `results_json` | string | `./results/results.json` | Path to the output JSON file |
| `triplet_mode` | bool | `false` | `true` = explicit triplets only; `false` = full cross-product |

### 5.2 Metrics Measured

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
| **Solver Performance** | `time` | Solver wall-clock time in seconds (includes symmetry breaking time) |
| | `cpu_time` | Total CPU seconds consumed by the solver |
| | `cpu_usage_avg` | Average CPU usage percentage |
| | `cpu_usage_max` | Peak CPU usage percentage |
| | `memory_peak_mb` | Peak memory usage in MB |
| | `total_time` | Sum of conversion + breaking + solving time (computed property) |
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

### 5.3 Files

Problem files to be converted by a formulator before solving.

```json
"files": {
    "hamilton_1": {"path": "./examples/hamilton_small.g6"},
    "hamilton_2": {"path": "./examples/graph1.g6", "enabled": false}
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `path` | string | Yes | Path to the problem file |
| `enabled` | bool | No | Default: `true` |

### 5.4 Formulators

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
| `output_mode` | string | No | How the formulator outputs results. Default: `stdout` |
| `options` | array | No | Additional command-line flags. Supports `{input}` and `{output}` tokens (see [options tokens](#options-tokens)) |

### 5.5 Breakers

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

### 5.6 Solvers

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

### 5.7 Without Converter

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

### 5.8 Visualization

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

### 5.9 Triplets & Execution Modes

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

## 6. Component Parameter Reference

| Parameter | Solvers | Formulators | Breakers | Files | Without Converter |
|:---|:---:|:---:|:---:|:---:|:---:|
| `cmd` | ✅ Required | ✅ Required | ✅ Required | — | — |
| `type` | ✅ Required | ✅ Required | ✅ Required | — | Optional |
| `path` | — | — | — | ✅ Required | ✅ Required |
| `enabled` | Optional | Optional | Optional | Optional | Optional |
| `options` | Optional | Optional | Optional | — | — |
| `output_mode` | — | Optional | — | — | — |
| `parser` | Optional | — | — | — | — |

**Default behaviors when optional fields are omitted**:
- `enabled`: `false` for solvers/formulators/breakers; `true` for files/without_converter
- `options`: empty list `[]`
- `output_mode`: `"stdout"`
- `parser`: auto-selected based on `type` field

---

## 7. Adding a New Solver

### 7.1 SAT Solver

1. Place the binary in `solver_exec/` or install system-wide
2. Add to `config.json`:
```json
"minisat": {
    "type": "SAT",
    "cmd": "./solver_exec/minisat",
    "enabled": true,
    "options": ["{input}", ">"],
    "parser": "SAT"
}
```

### 7.2 ILP Solver

```json
"scip": {
    "type": "ILP",
    "cmd": "scip",
    "enabled": true,
    "options": ["-f", "{input}"],
    "parser": "ILP"
}
```

### 7.3 Custom Parser Strategy

If a solver has a unique output format, define a custom parser in `src/parser_strategy.py`.

#### 1. Define the Parser Class

The simplest approach is to subclass `GenericParser` and define `STATUS_MAP` and `METRIC_PATTERNS`:

```python
class MyCustomParser(GenericParser):
    STATUS_MAP = {
        "s SATISFIABLE": "SAT",
        "s UNSATISFIABLE": "UNSAT",
    }
    METRIC_PATTERNS = {
        "conflicts": [r"Conflicts:\s+(\d+)"],
        "my_metric": [r"CustomValue\s*=\s*([\d\.]+)"]
    }
```

**`STATUS_MAP`** — maps a substring to a status string. The parser scans stdout (and the output file if status remains UNKNOWN) for each key in order. The first match wins.

> **Note**: If one key is a substring of another (e.g. `"feasible"` inside `"unfeasible"`), the more specific key must appear first in the dict to avoid false matches.

| Key | Value |
|:---|:---|
| Any substring present in solver output | `"SAT"`, `"UNSAT"`, `"TIMEOUT"`, or `"UNKNOWN"` |

**`METRIC_PATTERNS`** — maps a metric name to a list of regex patterns tried in order. The first pattern that matches extracts capture group 1 as the metric value. Multiple patterns allow the same metric to be parsed from different solver output formats.

```python
METRIC_PATTERNS = {
    "conflicts": [
        r"^\s*c?\s*nb\s+conflicts\s*:\s*(\d+)",  # Glucose style
        r"^\s*c?\s*conflicts\s*:\s*(\d+)",        # Kissat / CaDiCaL style
    ],
    "decisions": [
        r"^\s*c?\s*decisions\s*:\s*(\d+)",
    ]
}
```

Metric names must match keys in `metrics_measured` in `config.json` to appear in the CSV output.

#### 2. Override `parse()` for Full Control

If the solver output requires more complex logic — multi-line parsing, conditional status, computed metrics — override `parse()` directly:

```python
class MyCustomParser(ResultParser):
    def parse(self, result: Result, output_path: Optional[Path] = None) -> Result:
        content = result.stdout
        if output_path and output_path.exists():
            content = output_path.read_text()

        # UNSATISFIABLE must be checked first — it contains SATISFIABLE as a substring
        if "UNSATISFIABLE" in content:
            result.status = "UNSAT"
        elif "SATISFIABLE" in content:
            result.status = "SAT"

        match = re.search(r"conflicts\s*=\s*(\d+)", content)
        if match:
            result.metrics["conflicts"] = int(match.group(1))

        return result
```

#### 3. Register the Parser

```python
PARSER_REGISTRY = {
    "MY_CUSTOM_KEY": MyCustomParser(),
    ...
}
```

#### 4. Use it in `config.json`

```json
"MySpecialSolver": {
    "cmd": "./solvers/my_solver",
    "type": "SAT",
    "parser": "MY_CUSTOM_KEY",
    "enabled": true
}
```

> **Parser resolution**: If `parser` is omitted, the framework resolves it in `factory.py` — first checking the explicit key, then falling back to the type-based default from `metadata_registry.py`.

---

## 8. Adding a New Formulator

1. Create a script that reads a problem file and outputs the formula to stdout
2. The script must accept the problem file path as a command-line argument
3. Add to `config.json`:

```json
"my_formulator": {
    "type": "SAT",
    "cmd": "./my_scripts/my_formulator.py",
    "enabled": true,
    "output_mode": "stdout",
    "options": ["{input}"]
}
```

4. Make the script executable: `chmod +x my_scripts/my_formulator.py`

---

## 9. Adding a New Format Type

The format registry in `metadata_registry.py` maps type strings (e.g. `SAT`, `ILP`) to their file suffix, converter class, and default parser. To add a new format type:

### 1. Create a parser (if needed)

If the new format has a unique output style, add a parser in `parser_strategy.py` (see [Adding a New Solver — Custom Parser](#83-custom-parser-strategy)). Otherwise, reuse an existing one or `GenericParser`.

### 2. Register the format type

Add an entry to `FORMAT_REGISTRY` in `src/metadata_registry.py`:

```python
from parser_strategy import MyNewParser

FORMAT_REGISTRY: Dict[str, FormatMetadata] = {
    "SAT": FormatMetadata(format_type="SAT", suffix=".cnf", converter_class=Converter, parser_class=SATparser()),
    "ILP": FormatMetadata(format_type="ILP", suffix=".lp",  converter_class=Converter, parser_class=ILPparser()),
    "SMT": FormatMetadata(format_type="SMT", suffix=".smt2", converter_class=Converter, parser_class=SMTparser()),
    # Add your new type here:
    "MAXSAT": FormatMetadata(format_type="MAXSAT", suffix=".wcnf", converter_class=Converter, parser_class=MyNewParser()),
    ...
}
```

Each entry defines:

| Field | Description |
|:---|:---|
| `format_type` | Canonical type string — must match the key and the `type` field used in config |
| `suffix` | File extension for converted formula files (must be unique across all types) |
| `converter_class` | Converter class used to produce files of this type (usually `Converter`) |
| `parser_class` | Default parser instance used when no explicit `parser` key is set on a solver |

### 3. Use it in config

Reference the new type in formulators, solvers, and breakers:

```json
"my_formulator": {
    "type": "MAXSAT",
    "cmd": "./formulator/maxsat_encoder.py",
    "enabled": true
},
"my_solver": {
    "type": "MAXSAT",
    "cmd": "./solver_exec/maxsat_solver",
    "enabled": true
}
```

Pre-encoded files with the registered suffix (`.wcnf`) are auto-detected:

```json
"my_problem": {"path": "./examples/problem.wcnf"}
```

For unrecognized extensions, specify `type` explicitly:

```json
"my_problem": {"path": "./examples/problem.txt", "type": "MAXSAT"}
```

### 4. Tests pick it up automatically

`TestFormatRegistryContract` in `tests/unit/test_metadata_registry.py` automatically validates every entry in `FORMAT_REGISTRY` — no test changes needed.

> **Note**: Each suffix must be unique across all format types. If two types share the same suffix, only the last one in the dict will be used for auto-detection from file extensions.

---

## 10. Hamiltonian Cycle Formulator

The included formulator (`formulator/formulator.py`) encodes the Hamiltonian cycle/path decision problem from graph6 (`.g6`) files into DIMACS CNF format.

```bash
python3 formulator/formulator.py <input.g6> [--all] [--mode cycle|path]
```

| Flag | Description |
|:---|:---|
| `<input.g6>` | Input graph6 file (or `-` for stdin) |
| `--all` | Process all graphs in the file (default: first only) |
| `--mode` | `cycle` (default) or `path` |

---

## 11. Output & Results

### 11.1 CSV Output

Results are written to `results_csv`. Only metrics with `true` in `metrics_measured` appear as columns.

```csv
problem,formulator,solver,breaker,status,cpu_time,conflicts
hamilton_1,SAT_hamilton,kissat_cmd,breakid,SAT,0.42,1523
hamilton_1,SAT_hamilton,cadical_cmd,None,SAT,0.38,1401
```

### 11.2 JSON Output

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

### 11.3 Plots

When `visualization.enabled` is `true`, PNG plots are saved to `visualization.output_dir`:

| File | Description |
|:---|:---|
| `time_<problem>.png` | One per problem — stacked bar of mean wall-clock time (solve + break + conversion) per configuration |
| `status_counts.png` | Stacked bar of result status counts per `formulator / solver / breaker` configuration |
| `cpu_time_distribution.png` | Box plot of CPU time distribution per solver across all problems |

### 11.4 Working Directory

All intermediate files are saved in `working_dir`:

```
/tmp/sat/
├── hamilton_1/
│   └── SAT_hamilton/
│       ├── hamilton_1.cnf
│       └── logs/
│           ├── hamilton_1.kissat_cmd_breakid.out
│           └── hamilton_1.cadical_cmd_.out
└── hamilton_wc/
    └── logs/
        └── hamilton_wc.Glucose_.out
```

### 11.5 Status Values

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

## 12. Post-Run Plotting

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

## 13. Module Reference

| Module | Responsibility |
|:---|:---|
| `main.py` | CLI argument parsing (`--config`), entry point |
| `config_loader.py` | Config loading, validation, and parsing from JSON into typed objects |
| `solver_manager.py` | Experiment orchestration — triplet generation, parallel conversion + solving |
| `generic_executor.py` | Low-level subprocess execution with resource monitoring via `psutil` |
| `runner.py` | Solver execution — delegates to `GenericExecutor`, maps `RawResult` → `Result`, applies parser |
| `converter.py` | Runs formulator scripts to convert problems into solver-ready formats via `GenericExecutor` |
| `factory.py` | `get_converter()`, `get_runner()`; resolves parser from explicit key or type-based fallback |
| `cmd_builder.py` | `build_cmd()` — resolves `{input}`, `{output}`, `<`, `>` tokens into a subprocess command |
| `parser_strategy.py` | `SATparser`, `ILPparser`, `HiGHSParser`, `GenericParser`, `PARSER_REGISTRY` |
| `metadata_registry.py` | Maps format types (SAT/ILP/SMT) to suffixes, converters, and default parsers |
| `format_types.py` | Shared NamedTuples: `FormatMetadata`, `ExperimentContext`, `ConversionTask`, `SolvingTask` |
| `custom_types.py` | All dataclasses: `Config`, `Result`, `RawResult`, `ExecConfig`, `FormulatorConfig`, `TestCase`, etc. |
| `graph.py` | `log_results_to_csv`, `log_results_to_json`, `generate_plots`, `read_results_from_csv` |
| `plot_metric.py` | Standalone post-run plotter — bar charts and box plots for any numeric CSV column |

---

## 14. Testing

The test suite is split into unit tests (fast, no subprocess) and integration tests (require Linux solver binaries).

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

### Adding tests for a new parser

Subclass `ParserContractBase` in `tests/unit/test_parser_strategy.py`:

```python
class TestMyParserContract(ParserContractBase):
    parser = MyParser()
    sat_output = "MY SAT OUTPUT"
    unsat_output = "MY UNSAT OUTPUT"
```

### Adding tests for a new format type

Add the type to `FORMAT_REGISTRY` in `metadata_registry.py` — `TestFormatRegistryContract` in `tests/unit/test_metadata_registry.py` will automatically pick it up and validate it.

---

## 15. Troubleshooting

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

## 16. Dependencies

| Package | Version | Purpose |
|:---|:---|:---|
| `networkx` | 3.6 | Graph manipulation and graph6 parsing |
| `matplotlib` | 3.10.7 | Result visualization |
| `pandas` | latest | DataFrame construction for plots |
| `psutil` | latest | CPU and memory monitoring |
| `mypy` | 1.19.0 | Static type checking (development only) |

```bash
pip install -r requirements.txt
```

