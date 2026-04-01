# Comparison of SAT Solvers in Combinatorics

A Python benchmarking framework for running multiple SAT and ILP solvers on combinatorial problems in parallel, with optional symmetry breaking, configurable metrics collection, and CSV result export.

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
   - [Triplets & Execution Modes](#58-triplets--execution-modes)
6. [Component Parameter Reference](#6-component-parameter-reference)
7. [Supported Solvers](#7-supported-solvers)
8. [Adding a New Solver](#8-adding-a-new-solver)
9. [Adding a New Formulator](#9-adding-a-new-formulator)
10. [Hamiltonian Cycle Formulator](#10-hamiltonian-cycle-formulator)
11. [Output & Results](#11-output--results)
12. [Module Reference](#12-module-reference)
13. [Testing](#13-testing)
14. [Troubleshooting](#14-troubleshooting)
15. [Dependencies](#15-dependencies)
16. [DIMACS CNF Format Reference](#16-dimacs-cnf-format-reference)

---

## 1. Features

- Run multiple SAT/ILP solvers on combinatorial problems simultaneously
- Modular **Problem → Formulator → Breaker → Solver** pipeline
- Two execution modes: full cross-product (batch) or explicit triplet combinations
- Optional symmetry breaking via BreakID (or any compatible binary)
- Parallel execution with configurable thread count via `ProcessPoolExecutor`
- Per-process resource monitoring: CPU time, CPU usage, peak memory (via `psutil`)
- Regex-based solver output parsing using the Strategy design pattern
- Configurable metric selection — only enabled metrics appear in the output CSV
- Support for pre-encoded files (`.cnf`, `.lp`) that bypass the formulator step
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
python3 src/main.py
```

### 2.5 View Results
```bash
cat results/multi_solver_results.csv
```

> **Warning**: The `working_dir` directory is **deleted** at the start of each run. Use a temporary path like `/tmp/sat`.

---

## 3. Architecture

### 3.1 Pipeline Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│  Problem     │────▶│  Formulator  │────▶│  Breaker    │────▶│  Solver  │
│  (.g6 file)  │     │  (→ .cnf)    │     │  (optional) │     │          │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────┘
                                                                   │
                                                              ┌────▼─────┐
                                                              │  Result  │
                                                              │  (.csv)  │
                                                              └──────────┘
```

Alternatively, pre-encoded files can skip the formulator step entirely:

```
┌──────────────────┐     ┌─────────────┐     ┌──────────┐
│  Pre-encoded     │────▶│  Breaker    │────▶│  Solver  │
│  (.cnf / .lp)    │     │  (optional) │     │          │
└──────────────────┘     └─────────────┘     └──────────┘
```

### 3.2 Two-Phase Execution

The framework executes experiments in two phases:

**Phase 1 — Conversion**: Each unique (problem, formulator) pair is converted exactly once using `ProcessPoolExecutor`. Results are cached so that multiple solvers reuse the same converted file.

**Phase 2 — Solving**: All solver tasks (including optional symmetry breaking) run in parallel. Each task is independent and produces a `Result` object.

### 3.3 Execution Modes

| Mode | `triplet_mode` | Behavior |
|:---|:---|:---|
| **Batch** | `false` | Generates a full cross-product of all enabled files × formulators × solvers × breakers. Compatible types are matched automatically (e.g., SAT solvers only run on SAT formulators). |
| **Triplet** | `true` | Runs only the explicit combinations defined in the `triplets` array. Gives full control over which experiments to run. |

### 3.4 Design Patterns

| Pattern | Where | Purpose |
|:---|:---|:---|
| **Strategy** | `parser_strategy.py` | Pluggable solver output parsers (SAT, ILP, HiGHS, Generic) |
| **Factory** | `factory.py` | Creates converters and runners from config objects |
| **Registry** | `metadata_registry.py` | Maps format types to file suffixes, converters, and parsers |
| **Dataclass** | `custom_types.py` | Strongly typed configuration and result objects |

---

## 4. Project Structure

```
.
├── src/
│   ├── main.py               # Entry point — config loading, validation, experiment launch
│   ├── solver_manager.py      # Orchestrates conversion + solving pipeline
│   ├── runner.py              # Subprocess execution, resource monitoring, timeout
│   ├── converter.py           # Problem → formula conversion (e.g., .g6 → .cnf)
│   ├── factory.py             # Factory functions for converters and runners
│   ├── parser_strategy.py     # Strategy pattern — regex-based solver output parsers
│   ├── metadata_registry.py   # Format type registry (SAT → .cnf, ILP → .lp, etc.)
│   ├── custom_types.py        # Dataclasses: Config, ExecConfig, Result, TestCase, etc.
│   ├── graph.py               # Result visualization helpers (work in progress)
│   └── config.json            # Default experiment configuration
├── formulator/
│   └── formulator.py          # Hamiltonian cycle/path CNF encoder (graph6 → DIMACS)
├── converters/
│   └── converter.py           # Legacy copy of formulator
├── breakid/
│   └── breakid                # BreakID symmetry breaker binary (Linux)
├── solver_exec/               # Pre-compiled SAT solver binaries (Linux)
│   ├── cadical
│   ├── glucose_static
│   ├── isasat
│   ├── kissat
│   └── yalsat
├── examples/                  # Sample problem files
│   ├── hamilton/              # Pre-encoded Hamiltonian cycle CNF files
│   │   ├── hamilton_bigbad.txt
│   │   └── hamilton_biggood2.txt
│   ├── vertexColoring/
│   │   └── good3_951.txt
│   ├── graph.g6               # Graph6 format graph files
│   ├── graph1.g6
│   ├── hamilton_small.g6
│   └── test.lp                # ILP example (for HiGHS)
├── results/                   # Benchmark output CSVs
│   ├── multi_solver_results.csv
│   ├── multi_solver_results_12threads.csv
│   └── multi_solver_results_no_symm_breaking.csv
├── tests/                     # Unit tests
│   ├── testSolverManager.py
│   ├── testSolverRunner.py
│   └── testCNFSymmetryBreaker.py
├── requirements.txt           # Python dependencies
├── .gitignore
├── README.md                  # This file
├── DOCUMENTATION.md           # Detailed module-level documentation
└── Report_za_obidva_semestre.pdf
```

---

## 5. Configuration Guide

All experiment parameters are managed via `src/config.json`. To change path to the config file change `DEFAULT_CONFIG_PATH` at the top of `main.py`.

### 5.1 Global Settings

| Key | Type | Default | Description |
|:---|:---|:---|:---|
| `timeout` | int | `5` | Maximum execution time per solver run in seconds |
| `max_threads` | int | `1` | Number of parallel experiments. Capped at `CPU_count - 1` |
| `working_dir` | string | `/tmp/solver_comparison` | Temporary directory that will be created for generated formulas and logs. **IMPORATNT: If directory exists, it will be deleted on each run** - do NOT put any important directory (e.g. `/`) |
| `results_csv` | string | `./results/results.csv` | Path to the output CSV file |
| `triplet_mode` | bool | `false` | `true` = explicit triplets only; `false` = full cross-product |

### 5.2 Metrics Measured

Boolean flags that control which columns appear in the output CSV.

| Category | Metric | Description |
|:---|:---|:---|
| **Metadata** | `problem` | Name of the problem file |
| | `formulator` | Name of the formulator used |
| | `breaker` | Name of the symmetry breaker (or "None") |
| | `solver` | Name of the solver |
| | `parent_problem` | Original problem name before conversion - matters only when multiple problems in one problem file |
| **Status** | `status` | Result: `SAT`, `UNSAT`, `TIMEOUT`, `ERROR`, `UNKNOWN` |
| | `error` | Error message if execution failed |
| | `exit_code` | Process exit code |
| | `stderr` | Standard error output |
| **Performance** | `cpu_time` | Total CPU seconds consumed by the solver |
| | `time` | Wall-clock time in seconds |
| | `break_time` | Time spent on symmetry breaking |
| | `cpu_usage_avg` | Average CPU usage percentage |
| | `cpu_usage_max` | Peak CPU usage percentage |
| | `memory_peak_mb` | Peak memory usage in MB |
| **Solver Internals** | `restarts` | Number of solver restarts |
| | `conflicts` | Number of conflicts encountered |
| | `decisions` | Number of decisions made |
| | `propagations` | Number of propagations performed |

Example — enable only essential metrics:
```json
"metrics_measured": {
    "problem": true,
    "solver": true,
    "status": true,
    "cpu_time": true,
    "conflicts": true,
    "decisions": true
}
```

### 5.3 Files

Problem files to be converted by a formulator before solving.

```json
"files": {
    "graph_tc": {"path": "./examples/hamilton_small.g6"},
    "hamilton_1": {"path": "./examples/graph1.g6", "enabled": false}
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `path` | string | Yes | Path to the problem file (relative to project root or absolute) |
| `enabled` | bool | No | Whether to include this file. Default: `true` |

### 5.4 Formulators

Scripts that convert raw problem files into solver-ready formats.

```json
"formulators": {
    "SAT_hamilton": {
        "type": "SAT",
        "cmd": "./formulator/formulator.py",
        "enabled": true,
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
| `options` | array | No | Additional command-line flags |
| `output_param` | string | No | Output redirection flag (if not using stdout) |

### 5.5 Breakers

Symmetry breaking tools applied to the formula before solving.

```json
"breakers": {
    "breakid": {
        "type": "SAT",
        "cmd": "./breakid/breakid",
        "enabled": false,
        "options": [],
        "output_param": ">"
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `type` | string | Yes | Must match the solver type (e.g., `SAT`) |
| `cmd` | string | Yes | Path to the breaker binary |
| `enabled` | bool | No | Default: `false` |
| `options` | array | No | Additional flags |
| `output_param` | string | No | Output redirection method |

### 5.6 Solvers

The core solving engines.

```json
"solvers": {
    "kissat_cmd": {
        "type": "SAT",
        "cmd": "kissat",
        "enabled": true,
        "options": ["-n"],
        "output_param": ">",
        "parser": "Kissat"
    },
    "highs_cmd": {
        "type": "ILP",
        "cmd": "highs",
        "enabled": true,
        "options": [],
        "output_param": ">",
        "parser": "Highs"
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `type` | string | Yes | Logic format: `SAT` or `ILP` |
| `cmd` | string | Yes | System command or path to solver binary |
| `enabled` | bool | No | Default: `false` |
| `options` | array | No | Command-line flags (e.g., `["-n"]` for Kissat quiet mode) |
| `output_param` | string | No | How solver output is captured (see table below) |
| `parser` | string | No | Parser class name for metric extraction. Falls back to type-based default |

**Output parameter modes**:

| Value | Behavior | Example solver |
|:---|:---|:---|
| `>` | Python opens a file handle and redirects stdout | Kissat, Glucose |
| `-o` | Appended to command as `-o <output_path>` | CaDiCaL |
| `null` / omitted | Solver output captured from stdout via `subprocess.PIPE` | Glucose |

### 5.7 Without Converter

Pre-encoded files that skip the formulator step entirely. Use this for existing `.cnf` or `.lp` files. 

Can also be used when running solvers within a formulator (e.g. formulator uses a C++ API solver inside), however then the formulator has to be defined as a solver in `config.json`. However this is not the intended use case and requires user discretion. Will most likely require a custom parser. See [Adding a custom Parser for a Solver](#83-custom-parser-strategy)

```json
"without_converter": {
    "hamilton_wc": {
        "path": "./examples/hamilton/hamilton_bigbad.txt",
        "type": "SAT",
        "enabled": true
    },
    "test_lp": {
        "path": "./examples/test.lp",
        "type": "ILP",
        "enabled": true
    }
}
```

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `path` | string | Yes | Path to the pre-encoded file |
| `type` | string | No | Format type. Auto-detected from file extension if omitted |
| `enabled` | bool | No | Default: `true` |

### 5.8 Triplets & Execution Modes

#### Batch Mode (`triplet_mode: false`)

The framework generates a full cross-product of all enabled components, matching by type compatibility:
- Each enabled **file** × each enabled **formulator** (where types match) × each enabled **solver** (where types match)
- Each enabled **without_converter** file × each enabled **solver** (where types match)
- For each combination, if an enabled **breaker** exists with a matching type, an additional experiment with the breaker is added

#### Triplet Mode (`triplet_mode: true`)

Only the explicitly defined combinations run:

```json
"triplets": [
    {
        "problem": "graph_tc",
        "formulator": "SAT_hamilton",
        "breaker": "breakid",
        "solver": "kissat_cmd"
    },
    {
        "problem": "graph_tc",
        "formulator": "SAT_hamilton",
        "solver": "cadical_cmd"
    },
    {
        "without_converter": "hamilton_wc",
        "solver": "Glucose"
    }
]
```

Each triplet references component names defined in the respective config blocks. The `breaker` field is optional.

---

## 6. Component Parameter Reference

Summary of all parameters across component types:

| Parameter | Solvers | Formulators | Breakers | Files | Without Converter |
|:---|:---:|:---:|:---:|:---:|:---:|
| `cmd` | ✅ Required | ✅ Required | ✅ Required | — | — |
| `type` | ✅ Required | ✅ Required | ✅ Required | — | Optional |
| `path` | — | — | — | ✅ Required | ✅ Required |
| `enabled` | Optional | Optional | Optional | Optional | Optional |
| `options` | Optional | Optional | Optional | — | — |
| `output_param` | Optional | Optional | Optional | — | — |
| `output_mode` | — | Optional | — | — | — |
| `parser` | Optional | — | — | — | — |

**Default behaviors when optional fields are omitted**:
- `enabled`: `false` for solvers/formulators/breakers; `true` for files/without_converter
- `options`: empty list `[]`
- `output_param`: `null` (solver prints to stdout)
- `output_mode`: `"stdout"`
- `parser`: auto-selected based on `type` field
- `type` (without_converter): auto-detected from file extension

---

## 7. Supported Solvers

SAT solvers already have a preprogrammed `SATParser` class in `parser_strategy.py`

Examples of some solver configs:

| Solver | Type | Binary Location | Output Mode | Parser |
|:---|:---|:---|:---|:---|
| Kissat | SAT | `solver_exec/kissat` | `>` (redirect) | `Kissat` (SATparser) |
| CaDiCaL | SAT | `cadical` (system PATH) | `-o` | `Cadical` (SATparser) |
| Glucose | SAT | `solver_exec/glucose_static` | stdout | `Glucose` (GenericParser) |
| ISASat | SAT | `solver_exec/isasat` | — | — |
| YalSAT | SAT | `solver_exec/yalsat` | — | — |
| HiGHS | ILP | `highs` (system PATH) | `>` | `Highs` (HiGHSParser) |

---

## 8. Adding a New Solver

### 8.1 SAT Solver (e.g., MiniSat)

1. Place the binary in `solver_exec/` or install system-wide
2. Add to `config.json`:
```json
"minisat": {
    "type": "SAT",
    "cmd": "./solver_exec/minisat",
    "enabled": true,
    "options": [],
    "output_param": ">",
    "parser": "SAT"
}
```

### 8.2 ILP Solver (e.g., SCIP)

```json
"scip": {
    "type": "ILP",
    "cmd": "scip",
    "enabled": true,
    "options": ["-f"],
    "output_param": ">",
    "parser": "ILP"
}
```

### 8.3 Custom Parser Strategy

If a solver or breaker has a unique output format, you can define a custom parsing strategy in `src/parser_strategy.py`. This allows the framework to correctly identify the result status (SAT/UNSAT) and extract specific metrics (conflicts, nodes, etc.) from the solver's standard output.

#### 1. Define the Parser Class
Create a new class inheriting from `GenericParser`. You only need to define two dictionaries:

* **`STATUS_MAP`**: Mapping of strings found in the output to internal status constants (`SAT`, `UNSAT`, `UNKNOWN`, `TIMEOUT`).
* **`METRIC_PATTERNS`**: A dictionary where keys are metric names and values are lists of Regular Expressions (Regex) used to extract numerical values.

```python
class MyCustomParser(GenericParser):
    STATUS_MAP = {
        "s SATISFIABLE": "SAT",
        "s UNSATISFIABLE": "UNSAT",
        "Search Limit Reached": "TIMEOUT"
    }
    METRIC_PATTERNS = {
        "conflicts": [r"Conflicts:\s+(\d+)", r"c\s+nb\s+conflicts\s*:\s*(\d+)"],
        "decisions": [r"Decisions:\s+(\d+)"],
        "my_metric": [r"CustomValue\s*=\s*([\d\.]+)"]
    }
```

#### 2. Register the Strategy
Add an instance of your parser to the `PARSER_REGISTRY` dictionary at the bottom of `src/parser_strategy.py`. **Note:** The registry key should be uppercase for consistency.

```python
PARSER_REGISTRY = {
    "MY_CUSTOM_KEY": MyCustomParser(),
    "SAT": sat_p,
    "ILP": ilp_p,
    "DEFAULT": gen_p
}
```

#### 3. Use it in `config.json`
Reference your parser by its registry key in the solver or breaker configuration:

```json
"solvers": {
    "MySpecialSolver": {
        "cmd": "./solvers/my_solver",
        "type": "SAT",
        "parser": "MY_CUSTOM_KEY",
        "enabled": true
    }
}
```

---

> **Note on Automatic Selection:** If the `parser` field is omitted in the config, the framework automatically selects a parser based on the `type` field (e.g., `type: "SAT"` will default to the standard `SATparser`). Use a custom parser only when the standard ones fail to identify the status or extract the required metrics.

#### How Metrics Extraction Works:
* The parser uses `re.search` with `MULTILINE` and `IGNORECASE` flags.
* If the regex contains a capture group `(\d+)`, only that value is stored. If not, the entire match is stored.
* After parsing, `result.stdout` is cleared to save memory during large-scale experiments (the original output remains available in the `.out` file in your log directory).


## 9. Adding a New Formulator

1. Create a script that reads a problem file and outputs the formula to stdout (or a file)
2. The script must accept the problem file path as a command-line argument
3. Add to `config.json`:

```json
"my_formulator": {
    "type": "SAT",
    "cmd": "./my_scripts/my_formulator.py",
    "enabled": true,
    "output_mode": "stdout"
}
```

4. Make sure the script is executable: `chmod +x my_scripts/my_formulator.py`

---

## 10. Hamiltonian Cycle Formulator

The included formulator (`formulator/formulator.py`) encodes the Hamiltonian cycle or path decision problem from graph6 (`.g6`) files into DIMACS CNF format.

### Usage
```bash
python3 formulator/formulator.py <input.g6> [--all] [--mode cycle|path]
```

| Flag | Description |
|:---|:---|
| `<input.g6>` | Input graph6 file (or `-` for stdin) |
| `--all` | Process all graphs in the file (default: first only) |
| `--mode` | `cycle` (default) or `path` |

### Encoding

For a graph with `n` vertices, creates `n²` boolean variables:
- Variable `v × n + p + 1` means "vertex `v` is at position `p`"

Clauses enforce:
1. Each position has exactly one vertex
2. Each vertex appears at exactly one position
3. Non-adjacent vertices cannot occupy consecutive positions (with wrap-around for cycles)

---

## 11. Output & Results

### 11.1 CSV Output

Results are written to the path specified by `results_csv`. Only metrics with `true` in `metrics_measured` appear as columns.

Example output:
```csv
problem,solver,status,cpu_time,conflicts,decisions,propagations
graph_tc,kissat_cmd,SAT,0.42,1523,4201,89432
graph_tc,cadical_cmd,SAT,0.38,1401,3892,82104
hamilton_wc,Glucose,UNSAT,12.7,98234,201432,4523891
```

### 11.2 Working Directory

All intermediate files (converted formulas, solver logs, symmetry-broken files) are saved in `working_dir`, organized as:

```
/tmp/sat/
├── graph_tc/
│   └── SAT_hamilton/
│       ├── graph_tc.cnf              # Converted formula
│       └── logs/
│           ├── graph_tc.kissat_cmd_None.out
│           └── graph_tc.cadical_cmd_None.out
└── hamilton_wc/         # without_converter files: formulator dir is ommited
    └── logs/
            └── hamilton_wc.Glucose_None.out
```

### 11.3 Status Values

| Status | Meaning |
|:---|:---|
| `SAT` | Satisfiable solution found |
| `UNSAT` | Proven unsatisfiable |
| `TIMEOUT` | Solver exceeded the configured timeout |
| `ERROR` | Solver crashed or execution failed |
| `BREAKER_ERROR` | Symmetry breaker failed |
| `UNKNOWN` | Solver finished but status could not be determined |

---

## 12. Module Reference

| Module | Responsibility |
|:---|:---|
| `main.py` | Config loading, validation, entry point |
| `solver_manager.py` | Experiment orchestration — triplet generation, parallel conversion + solving |
| `runner.py` | Single process execution with timeout, resource monitoring via `psutil` |
| `converter.py` | Runs formulator scripts to convert problems into solver-ready formats |
| `factory.py` | Factory functions: `get_converter()`, `get_runner()` |
| `parser_strategy.py` | Strategy pattern — `SATparser`, `ILPparser`, `HiGHSParser`, `GenericParser` |
| `metadata_registry.py` | Maps format types (SAT/ILP/SMT) to suffixes, converters, and parsers |
| `custom_types.py` | All dataclasses: `Config`, `ExecConfig`, `FormulatorConfig`, `FileConfig`, `TestCase`, `ExecutionTriplet`, `SolvingTask`, `Result` |
| `graph.py` | CSV reading and visualization helpers (work in progress) |

For detailed API documentation of each module, see [DOCUMENTATION.md](DOCUMENTATION.md).

---

## 13. Testing

```bash
# Run all tests
python3 -m pytest tests/

# Run a specific test file
python3 -m pytest tests/testSolverRunner.py -v
```

| Test File | Coverage |
|:---|:---|
| `testSolverRunner.py` | Runner execution, SAT/UNSAT detection, timeout handling, memory monitoring, CSV logging |
| `testSolverManager.py` | Manager initialization, directory expansion, parallel execution, symmetry breaking integration |
| `testCNFSymmetryBreaker.py` | BreakID execution, timeout handling, output parsing, error cleanup |

> **Note**: Some tests reference older class names and may need updating to match the current module structure.

---

## 14. Troubleshooting

### Solver binary not found
```
FileNotFoundError: Solver command or path not found: kissat
```
**Fix**: Either install the solver system-wide (`sudo apt install kissat`) or use a relative/absolute path to the binary in `solver_exec/`:
```json
"cmd": "./solver_exec/kissat"
```

### Permission denied on solver/formulator
```
PermissionError: ... is not executable
```
**Fix**: Make the file executable:
```bash
chmod +x solver_exec/kissat
chmod +x formulator/formulator.py
```

### Working directory deleted unexpectedly
The framework **deletes the entire `working_dir`** at startup. Use a dedicated temporary path:
```json
"working_dir": "/tmp/sat_experiments"
```
Never point `working_dir` to a directory containing important files.

### max_threads exceeds CPU count
```
Warning: Configured max_threads 12 exceeds logical CPU count 8. Using 7 instead.
```
This is automatic — the framework caps threads at `CPU_count - 1`. No action needed.

### All metrics show 0 in CSV
**Cause**: No `parser` specified and the default parser doesn't match the solver's output format.
**Fix**: Set the correct parser in the solver config:
```json
"parser": "Kissat"
```
Available parsers: `SAT`, `ILP`, `Kissat`, `Cadical`, `Glucose`, `Highs`

### Solver returns UNKNOWN status
**Cause**: The parser couldn't find a status keyword in the solver output.
**Possible fixes**:
1. Check that `output_param` is set correctly — the parser needs access to the solver's output
2. Verify the solver actually produces status lines (e.g., `s SATISFIABLE`)
3. Create a custom parser if the solver uses non-standard output format

### Timeout too short
If most experiments show `TIMEOUT` status, increase the global timeout:
```json
"timeout": 7200
```
Note: symmetry breaking time is subtracted from the solver timeout. If breaking takes 30s and timeout is 60s, the solver only gets 30s.

### Config validation errors
```
ValueError: Config 'my_solver' is missing required 'cmd' field.
ValueError: Config 'my_solver' has unrecognized 'type' field value 'XYZ'.
```
**Fix**: Ensure all required fields are present and `type` is one of: `SAT`, `ILP`, `SMT`.

### Pre-encoded file type not detected
```
ValueError: ... has an unknown type and no 'type' field specified.
```
**Fix**: Explicitly set the `type` field in the `without_converter` block:
```json
"hamilton_wc": {"path": "./my_file.txt", "type": "SAT", "enabled": true}
```

---

## 15. Dependencies

| Package | Version | Purpose |
|:---|:---|:---|
| `networkx` | 3.6 | Graph manipulation and graph6 parsing |
| `matplotlib` | 3.10.7 | Result visualization (work in progress) |
| `psutil` | latest | CPU and memory monitoring during solver execution |
| `mypy` | 1.19.0 | Static type checking (development only) |

Install all dependencies:
```bash
pip install -r requirements.txt
```

---

## 16. DIMACS CNF Format Reference

The standard input format for SAT solvers:

```
c This is a comment
p cnf <num_variables> <num_clauses>
1 -3 0
2 3 -1 0
```

- Lines starting with `c` are comments
- The `p cnf` line declares the number of variables and clauses
- Each subsequent line is a clause: a space-separated list of literals terminated by `0`
- Positive integer = variable is true; negative integer = variable is false

Example — 3 variables, 2 clauses:
```
p cnf 3 2
1 -3 0
2 3 -1 0
```
This encodes: `(x₁ ∨ ¬x₃) ∧ (x₂ ∨ x₃ ∨ ¬x₁)`
