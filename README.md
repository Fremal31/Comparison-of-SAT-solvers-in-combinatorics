"""
# Comparison of solvers in combinatorics
---

A Python framework designed to execute multiple solvers on combinatoric CNF files simultaneously, with optional symmetry breaking support for SAT solver. It enables multiprocessing and tracks results for analysis.

---
### **IMPORTANT**: Only works on linux

## Table of Contents: #TODO

## How to use:


### 1. Clone the Repository
```bash
    git clone https://github.com/Fremal31/Comparison-of-SAT-solvers-in-combinatorics.git
    cd Comparison-of-SAT-solvers-in-combinatorics
```

### 2. Setup Environment
We recommend using a virtual environment to avoid dependency conflicts:
```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
```
### 3. Configure Parameters
By default the configuration path is set to `src/config.json`. Feel free to modify it to your needs. See the [Configuration Guide](#-configuration-guide-(`config.json`)) for more details.
Example config:
```json
{
"metrics_measured": {
    "problem": true,
    "formulator": true,
    "breaker": false,
    "solver": true,
    "parent_problem": false,
    
    "status": true,

    "cpu_usage_avg": false,
    "cpu_usage_max": false,
    "memory_peak_mb": false,
    "break_time": false,
    "cpu_time": true,
    "time": false,
    "exit_code": false,

    "restarts": true,
    "conflicts": true,
    "decisions": true,
    "propagations": true,
    
    "error": true,
    "stderr": true

},
"files": {
    "graph_tc": {"path": "./examples/hamilton_small.g6"}
},
"formulators": {
    "SAT_hamilton": {"type": "SAT", "cmd": "/home/fremks31/Comparison-of-SAT-solvers-in-combinatorics/  formulator/formulator.py", "enabled": true, "output_mode": "stdout"}
},
"breakers": {
    "breakid": {"type": "SAT", "cmd": "./breakid/breakid", "enabled": false, "options": [], "output_param": ">"}
},
"solvers": {
    "kissat_cmd": {"type": "SAT", "cmd": "kissat", "enabled": true, "options": ["-n"], "output_param": ">", "parser": "Kissat"}
},
"without_converter": {
    "hamilton_wc": {"type": "SAT", "path": "./examples/hamilton/hamilton_bigbad.txt", "enabled": true}
},
"triplets": [
    {
        "problem": "graph_tc",
        "formulator": "SAT_hamilton",
        "breaker": "breakid",
        "solver": "kissat_cmd"
    },
    {
        "without_converter": "hamilton_wc",
        "solver": "kissat_cmd"
    }
],
"triplet_mode": false,
"timeout": 10,
"max_threads": 6,
"working_dir": "/tmp/sat",
"results_csv": "./results/multi_solver_results.csv"
}
```

### 4. Run Framework
Run the comparison suite directly from the project root `Comparison-of-SAT-solvers-in-combinatorics`:
    `python3 src/main.py`

### 5. See Results
All enabled metrics will be written to a `.csv` as specified in the `config.json`: 
```json
"results_csv": "path/to/your/results.csv"
```

All of the output files created in the process will be saved in the `working dir` directory specified in the `config.json`:
```json
"working_dir": "path/to/your/working_dir"
```
We recommend placing it somewhere in the `/tmp/` directory. e.g. `/tmp/results`.
**Warning:** When running the script all files in the `working_dir` will be deleted. 


---
# Configuration Guide (`config.json`)

The engine uses a modular **Problem-Formulator-Solver** pipeline. All execution parameters, metrics, and experimental setups are managed via `src/config.json`.

---

## Metrics Measured (`metrics_measured`)
These boolean flags toggle which data points are collected and saved to your final results CSV.

| Category | Parameter | Description |
| :--- | :--- | :--- |
| **Metadata** | `problem`, `formulator`, `solver` | Tracks which specific tools and files were used. |
| **Results** | `status` | Captures SAT/UNSAT/OPTIMAL status and execution errors. |
| **Performance**| `cpu_time` | Total CPU seconds consumed by the solver process. |
| **SAT/ILP** | `conflicts`, `decisions`, `restarts`, `propagations` | Internal heuristic counters extracted from solver logs. |
| **Debug** | `stderr` | Captures the standard error output for troubleshooting crashes. |

---

### Component Parameters

Each block (Solvers, Formulators, Breakers) uses the following parameter logic:

| Parameter | Type | Status | Description |
| :--- | :--- | :--- | :--- |
| **`cmd`** | String | **Required** | The command to run (e.g., `kissat` or `./path/to/bin`). |
| **`enabled`** | Boolean | **Optional** | Whether to include this component in the current run. |
| **`type`** | String | **Required** | Logic format (e.g., `SAT`, `ILP`). Defaults to `SAT`. |
| **`options`** | Array | **Optional** | List of flags to pass to the command (e.g., `["-n", "-v"]`). |
| **`output_param`**| String | **Optional** | The flag used for log redirection (e.g., `>`, `-o`, `--log_file`). |
| **`parser`** | String | **Optional** | The name of the Python class used to extract metrics. |
| **`path`** | String | **Required*** | Only required for `files` and `without_converter` blocks. |

---

### Understanding Parameter Behavior

* **Required**: If these are missing, the engine will raise a `KeyError` or `FileNotFoundError` and stop execution.
* **Optional**: 
    * If `options` is missing, the engine runs the command with no extra flags.
    * If `output_param` is missing or `null`, the engine assumes the solver prints directly to `stdout`.
    * If `parser` is missing, the engine will still run the solver but will record `0` for all metrics like conflicts/decisions.
* **Default Values**: 
    * `timeout`: Defaults to `3600` if not specified in global settings.
    * `max_threads`: Defaults to `1` (sequential execution) if missing.

## Experiment Logic (`triplets`)
The `triplets` array defines specific benchmark chains (File → Formulator → Breaker → Solver) or (Without Converter → Breaker → Solver).

* **`triplet_mode: true`**: The engine **only** runs the specific combinations defined in the `triplets` list.
* **`triplet_mode: false`**: The engine runs a **full cross-product** (Batch Mode) of all enabled files, formulators, and solvers.

---

## Component Blocks

### 🔹 Solvers
The core engines (SAT or ILP) used to find solutions.
* **`cmd`**: The system command (e.g., `kissat`) or local/absolute path (e.g., `./solver_exec/kissat`).
* **`type`**: The logic format (`SAT` or `ILP`).
* **`output_param`**: How the solver handles log output:
    * `>`: Standard shell redirection.
    * `-o`: Cadical-specific output flag.
    * `--log_file`: HiGHS-specific log flag.
* **`parser`**: The Regex class used to extract metrics from that solver's specific output style.

### 🔹 Formulators
Scripts that translate raw problem files (like `.g6` graphs) into logic formats (like `.cnf`).
* **`output_mode`**: Set to `stdout` if the script prints the formula directly to the console.

### Without Converter
Used for **Direct Solving**. This allows you to run solvers on pre-existing SAT (`.cnf`) or ILP (`.lp`) files, bypassing the formulator step.

---

## Project Structure
    .
    ├── src/
    │   ├── main.py            # Entry point
    │   ├── solver_manager.py  # Orchestrates solver execution
    │   ├── runner.py          # Process handling & resource monitoring
    │   └── config.json        # Solver paths and experiment settings
    ├── solver_exec/           # Binaries for SAT solvers (Kissat, etc.)
    ├── examples/              # Sample graph files
    ├── tests/                 # Unit tests for core logic
    ├── requirements.txt       # Project dependencies
    └── .gitignore             

---
## Global Execution Settings
* **`timeout`**: Maximum execution time per solver run in seconds (Default: `7200` / 2 hours).
* **`max_threads`**: Number of experiments to run in parallel (Current: `6`).
* **`working_dir`**: Temporary directory for generated formulas and logs (Default: `/tmp/sat`).
* **`results_csv`**: Path to the final benchmark data file.


---

## Example: Adding HiGHS (ILP)
To add a system-wide ILP solver like HiGHS, ensure your `solvers` block looks like this:
```json
"highs_cmd": {
  "type": "ILP",
  "cmd": "highs",
  "enabled": true,
  "output_param": "--log_file",
  "parser": "Highs"
}
```

## Dependencies
* **NetworkX:** Graph structure manipulation.
* **Matplotlib:** Result visualization.
* **psutil:** System-level resource monitoring.
* **aiohttp:** Asynchronous metadata handling.
"""
```

## Sample CNF Format (DIMACS)
```plain
p cnf 3 2
1 -3 0
2 3 -1 0
```

