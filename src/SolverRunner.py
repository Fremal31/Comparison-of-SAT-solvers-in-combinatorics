import subprocess
import time
import os
from pathlib import Path
import psutil

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
            process = subprocess.Popen(
                [self.solver_path, cnf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                #timeout=timeout,
                text=True
            )
            ps_process = psutil.Process(process.pid)

            peak_memory = 0
            cpu_usage = []

            start_time = time.time()

            try:
                while process.poll() is None:
                    mem_info = ps_process.memory_info()
                    cpu_percent = ps_process.cpu_percent(interval=0.01)

                    peak_memory = max(peak_memory, mem_info.rss / (1024 * 1024))
                    cpu_usage.append(cpu_percent)

                    time.sleep(0.01)

                elapsed_time = time.time() - start_time

                stdout, stderr = process.communicate()
                avg_cpu = sum(cpu_usage) / len(cpu_usage) if cpu_usage else 0

                result = {
                    "exit_code": process.returncode,
                    "cpu_usage_avg": avg_cpu,
                    "cpu_usage_max": max(cpu_usage, default=0),
                    "memory_peak_mb": peak_memory,
                    "time": elapsed_time,
                    #"stdout": stdout,
                    "stderr": stderr
                }    
            
            except Exception as e:
                process.kill()
            
            
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                #"stdout": "",
                "stderr": "Solver timed out",
                "time": timeout
            } 
        metrics = self.parse_output(stdout)
        result.update(metrics)  

        return result
        
    def parse_output(self, output):
        metrics = {"ans" : ""}
        '''metrics = {"conflicts": "nodata",
                   "decisions": "nodata",
                   "propagations": "nodata",
                   "cpu_time": "nodata"}
        lines = output.splitlines()
        for line in lines:
            for key in metrics:
                if key in line:
                    try:
                        parts = line.strip().split(":")
                        print(parts)
                        #metrics[value] = int(parts[1].split()[0])
                        metrics[key] = parts[3].strip()
                
                    except (IndexError, ValueError):
                        continue
'''
        lines = output.splitlines()
        string = ""
        for line in lines:
            if line.startswith("s "):
                metrics["status"] = line[2:].strip()
            if line.startswith("v "):
                string = string + line[2:].strip()
                
        metrics["ans"] = string
        return metrics

    def log_results(self, results, output_path="results.csv"):
        import csv
        output_file = Path(output_path)
        write_header = not output_file.exists()

        with open(output_file, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=results[0].keys())
            if write_header:
                writer.writeheader()
            writer.writerow(results)