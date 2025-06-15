
# Comparison-of-SAT-solvers-in-combinatorics

**Comparison-of-SAT-solvers-in-combinatorics** is a Python framework designed to execute multiple SAT solvers on CNF files simultaneously, with optional symmetry breaking support via [BreakID](https://github.com/bjornshe/BreakID). It enables multiprocessing and tracks results for analysis.

## Features

- Concurrent execution of multiple SAT solvers on CNF inputs  
- Optional integration with BreakID for symmetry breaking  
- Configurable through a JSON settings file  
- Outputs results in CSV format for further evaluation  

## Requirements

- Python 3.7 or higher 
- `psutil`, `pandas`
- Install dependencies using:  
```bash
pip install -r requirements.txt
```

## How to use:

1. **Define solver paths and configuration:**

   Example `src/solverPaths.json`:  
```json
[
    {
        "name": "Kissat",
        "path": "./solver_exec/kissat",
        "args": [],
        "env": {}
    },
    {
        "name": "Glucose_static",
        "path": "./solver_exec/glucose_static",
        "args": [],
        "env": {}
    },
]
```

2. **Run the manager with the config file:**  
```bash
python ./src/main.py
```

3. **Check the results:**  
   - Results are saved in `results/multi_solver_results.csv`  
   - To load and view results:  
```python
import graph
df = graph.read_results_from_csv("results/multi_solver_results.csv")
print(df)
```

## Configuration File Example (`config.json`)
```json
{
  "cnf_files": ["./examples/vertexColoring"],
  "timeout": 5,
  "maxthreads": 1,
  "symmetry_breaking": {
    "enabled": true,
    "symmetry_breaker_path": "./breakid/breakid",
    "use_temp_files": true
  },
  "results_csv": "results/multi_solver_results.csv"
}
```
## Config Arguments
- `cnf_files`: takes individual files as well as directories. In case of directories, it iterates over all files in this directory
- `timeout`: time in seconds after which each instance is terminated
- `maxthreads`: how many individual threads can be used. WARNING: output will be scrambled due to multiple threads
- `symmetry_breaking` has 3 attributes:
    - `enabled`: whether to use symmetry_breaker
    - `symmetry_breaker_path`: path to symmetry breaker. By default uses [BreakID](https://github.com/bjornshe/BreakID). Might require modification of access priviliges.
    - `use_temp_files`: whether to create only temporary files for modified symmetry broken CNFs. If `False`, then will by default create file in the same directory as the original CNF with `_sb.cnf` suffix. Example: `original_CNF_name_sb.cnf`.
- `results_csv`: specify the path where the `.csv` file should be located.

## Sample CNF Format (DIMACS)
```plain
p cnf 3 2
1 -3 0
2 3 -1 0
```

