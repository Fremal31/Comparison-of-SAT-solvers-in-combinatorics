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

    def run_solver(self, cnf_path, timeout):
        if not os.path.exists(cnf_path):
            raise FileNotFoundError(f"CNF file not found: {cnf_path}")

        result_template = {
            "exit_code": -1,
            "cpu_usage_avg": 0,
            "cpu_usage_max": 0,
            "memory_peak_mb": 0,
            "time": 0,
            "stderr": "",
            "status": "ERROR",
            "ans": ""
        }

        process = None
        start_time = time.time()
        peak_memory = 0
        cpu_usage = []

        try:
            process = subprocess.Popen(
                [self.solver_path, cnf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            with process:
                ps_process = psutil.Process(process.pid)
                
                while True:
                    try:
                        elapsed_time = time.time() - start_time
                        if elapsed_time > timeout:
                            parent = psutil.Process(process.pid)
                            for child in parent.children(recursive=True):
                                child.kill()
                            parent.kill()
                            result_template.update({
                                "exit_code": -1,
                                "time": timeout,
                                "stderr": "Timeout reached",
                                "status": "TIMEOUT"
                            })
                            return result_template

                        return_code = process.poll()
                        if return_code is not None:
                            break

                        mem_info = ps_process.memory_info()
                        cpu = ps_process.cpu_percent(interval=0.1)
                        
                        peak_memory = max(peak_memory, mem_info.rss / (1024 * 1024))
                        cpu_usage.append(cpu)

                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
                    
                    time.sleep(0.1)

                stdout, stderr = process.communicate()
                #elapsed_time = time.time() - start_time
                cpu_without0 = [x for x in cpu_usage if x > 0]
                avg_cpu = sum(cpu_without0)/len(cpu_without0) if cpu_without0 else 0
                
                parsed_output = self.parse_output(stdout)
                status = "INVALID"
                if return_code == 10:
                    status = "SAT"
                elif return_code == 20:
                    status = "UNSAT"
                else:
                    status = "UNKNOWN"

                result = {
                    "exit_code": process.returncode,
                    "cpu_usage_avg": avg_cpu,
                    "cpu_usage_max": max(cpu_usage, default=0),
                    "memory_peak_mb": peak_memory,
                    "time": elapsed_time,
                    "stderr": stderr.strip(),
                    "status": status,
                    "ans": parsed_output["ans"]
                }
                return result

        except Exception as e:
            if process and process.poll() is None:
                process.kill()
            cpu_usage
            error_result = result_template.copy()
            error_result.update({
                "stderr": f"Execution error: {str(e)}",
                "memory_peak_mb": peak_memory,
                "time": time.time() - start_time
            })
            return error_result
    def parse_output(self, output):
        metrics = {"status": "UNKNOWN", "ans": ""}
        if not output:
            return metrics
        lines = output.splitlines()
        solution = []
        
        for line in lines:
            if line.startswith("s "):
                metrics["status"] = line[2:].strip()
            if line.startswith("v "):
                solution.append(line[2:].strip())
        
        #metrics["ans"] = " ".join(solution)
        return metrics

    def log_results(self, results, output_path="results.csv"):
        import csv
        output_file = Path(output_path)

        with open(output_file, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=results[0].keys())
            if not output_file.exists():
                writer.writeheader()
            writer.writerow(results)
