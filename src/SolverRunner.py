import subprocess
import time
import os
from pathlib import Path

class SolverRunner:
    def __init__(self, solver_path):
        if not os.path.exists(solver_path):
            raise FileNotFoundError(f"Solver path not found: {solver_path}")
        self.solver_path = solver_path

    def run_solver(self, cnf_path, timeout=300):
        if not os.path.exists(cnf_path):
            raise FileNotFoundError(f"CNF file not found: {cnf_path}")
        
        start_time = time.time()
        
        try:
            process = subprocess.run(
                [self.solver_path, cnf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True
            )
            elapsed_time = time.time() - start_time
            
            result = {
                "exit_code": process.returncode,
                #"stdout": process.stdout,
                "stderr": process.stderr,
                "time": elapsed_time
            }
            
            metrics = self.parse_output(process.stdout)
            result.update(metrics)
            
        except subprocess.TimeoutExpired:
            result = {
                "exit_code": -1,
                #"stdout": "",
                "stderr": "Solver timed out",
                "time": timeout
            }
        
        return result

    def parse_output(self, output):
        metrics = {}
        lines = output.splitlines()
        for line in lines:
            if "conflicts" in line and ":" in line:
                try:
                    parts = line.split(":")
                    metrics["conflicts"] = int(parts[1].split()[0])
                except (IndexError, ValueError):
                    continue

            elif "decisions" in line and ":" in line:
                try:
                    parts = line.split(":")
                    metrics["decisions"] = int(parts[1].split()[0])
                except (IndexError, ValueError):
                    continue

            elif "propagations" in line and ":" in line:
                try:
                    parts = line.split(":")
                    metrics["propagations"] = int(parts[1].split()[0])
                except (IndexError, ValueError):
                    continue

            elif "CPU time" in line:
                try:
                    metrics["cpu_time"] = float(line.split()[-2])
                except ValueError:
                    continue
            elif line.startswith("s "):
                metrics["status"] = line[2:].strip()
        return metrics

    def log_results(self, results, output_path="results.csv"):
        import csv
        output_file = Path(output_path)
        write_header = not output_file.exists()

        with open(output_file, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=results.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(results)