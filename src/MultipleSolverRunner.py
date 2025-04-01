import json
from pathlib import Path
from SolverRunner import SolverRunner

class MultiSolverManager:
    def __init__(self, config_path, cnf_files):
        self.solvers = self.load_config(config_path)
        self.cnf_files = cnf_files

    def load_config(self, config_path):
        with open(config_path, "r") as file:
            return json.load(file)

    def run_all(self, timeout):
        all_results = []

        for solver in self.solvers:
            solver_path = solver["path"]
            solver_args = solver.get("args", [])
            solver_runner = SolverRunner(solver_path)

            for cnf_file in self.cnf_files:
                #print(f"Running {solver['name']} on {cnf_file}...")
                try:
                    results = solver_runner.run_solver(cnf_path=cnf_file, timeout=timeout)
                    results.update({
                        "solver": solver["name"],
                        "cnf_file": Path(cnf_file).name
                    })
                    all_results.append(results)
                except Exception as e:
                    all_results.append({
                        "solver": solver["name"],
                        "cnf_file": Path(cnf_file).name,
                        "error": str(e)
                    })

        return all_results

    def log_results(self, results, output_path="multi_solver_results.csv"):
        import csv
        output_file = Path(output_path)
        write_header = not output_file.exists()

        with open(output_file, mode="w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=results[0].keys())
            #if write_header:
                #writer.writeheader()
            writer.writeheader()
            writer.writerows(results)