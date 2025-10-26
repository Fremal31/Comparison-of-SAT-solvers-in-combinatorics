import json
import sys
from SolverManager import MultiSolverManager
import graph
import pandas as pd
from pathlib import Path

def main():
    """Loads parameters from configuration file"""
    try:
        config_path = Path("./src/config.json")
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with config_path.open("r") as f:
            config = json.load(f)

        solver_config_path = Path("./src/solverPaths.json")
        if not solver_config_path.exists():
            raise FileNotFoundError(f"Solver configuration file not found: {solver_config_path}")

        cnf_files = config.get("cnf_files", [])
        if not cnf_files:
            raise ValueError("No CNF files specified in the config.")

        timeout = config.get("timeout", None)
        maxthreads = config.get("maxthreads", 1)
        symmetry_config = config.get("symmetry_breaking", {})
        output_path = config.get("results_csv", "results/multi_solver_results.csv")

        manager = MultiSolverManager(solver_config_path, cnf_files, timeout=timeout, maxthreads=maxthreads)

        if symmetry_config.get("enabled", False):
            manager.set_symmetry_breaker(
                break_symmetry=True,
                symmetry_breaker_path=symmetry_config.get("symmetry_breaker_path", ""),
                use_temp_files=symmetry_config.get("use_temp_files", False)
            )

        results = manager.run_all()
        manager.log_results(results, output_path=output_path)

        try:
            df = read_results_from_csv(output_path)
            print(df)
        except Exception as e:
            print(f"Error reading results CSV: {e}")

    except Exception as e:
        print(f"[FATAL] {e}")
        sys.exit(1)

def read_results_from_csv(csv_path):
    """
    Reads the results CSV file into a pandas DataFrame.
    Args:
        csv_path (str or Path): Path to the results CSV file.
    Returns:
        pd.DataFrame or None: Parsed results as a DataFrame, or None if reading fails.
    """
    try:
        df = pd.read_csv(csv_path)
        return df
    except FileNotFoundError:
        print(f"File {csv_path} not found.")
        return None
    except pd.errors.EmptyDataError:
        print(f"File {csv_path} is empty.")
        return None
    except pd.errors.ParserError:
        print(f"Could not parse the file {csv_path}.")
        return None
    
if __name__ == "__main__":
    main()
