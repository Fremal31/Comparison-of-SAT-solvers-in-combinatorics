import subprocess
import time
import os
import psutil
from threading import Thread
from pathlib import Path
import csv

class SolverRunner:
    """
    Class to execute a SAT solver on a CNF file, monitor its performance,
    and collect statistics such as CPU usage, memory usage, and execution time.
    """

    result_template = {
        "exit_code": -1,
        "cpu_usage_avg": 0,
        "cpu_usage_max": 0,
        "memory_peak_mb": 0,
        "time": 0,
        "cpu_time": 0,
        "stderr": "",
        "status": "ERROR",
        "ans": ""
    
    }

    def __init__(self, solver_path):
        """
        Initializes the SolverRunner with a given solver binary path.

        Args:
            solver_path (str): Path to the SAT solver executable.

        Raises:
            FileNotFoundError: If the solver path does not exist.
        """
        if not os.path.exists(solver_path):
            raise FileNotFoundError(f"Solver path not found: {solver_path}")
        self.solver_path = solver_path

    def run_solver(self, cnf_path, timeout: int):
        """
        Executes the SAT solver on the specified CNF file with a time limit.

        Monitors the solver's CPU and memory usage in a background thread,
        and returns performance metrics and solver result.

        Args:
            cnf_path (str): Path to the CNF input file.
            timeout (int): Timeout in seconds after which the solver is forcefully stopped.

        Returns:
            dict: A dictionary with statistics and solver result. Keys include:
                - 'exit_code': Exit code of the solver process.
                - 'cpu_usage_avg': Average CPU usage (%).
                - 'cpu_usage_max': Maximum CPU usage (%).
                - 'memory_peak_mb': Peak memory usage in MB.
                - 'time': Wall-clock time taken by the solver.
                - 'process_time': CPU time used by the solver.
                - 'stderr': Any error output from the solver.
                - 'status': Result status ("SAT", "UNSAT", "TIMEOUT", or "UNKNOWN").
                - 'ans': Solver's standard output (raw).

        Raises:
            FileNotFoundError: If the CNF input file does not exist.
        """
        if not os.path.exists(cnf_path):
            raise FileNotFoundError(f"CNF file not found: {cnf_path}")

        start_time = time.time()
        peak_memory = 0
        cpu_usage = []
        main_cpu_time = 0.0

        result = self.result_template.copy()

        try:
            process = subprocess.Popen(
                [self.solver_path, cnf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            ps_process = psutil.Process(process.pid)

            def monitor():
                """
                Monitors the resource usage of the solver process.
                Tracks CPU usage, CPU time and peak memory consumption.
                Runs on separate thread.
                """
                nonlocal peak_memory, cpu_usage, main_cpu_time
                try:
                    while process.poll() is None:
                        times = ps_process.cpu_times()
                        main_cpu_time = times.user + times.system

                        mem_info = ps_process.memory_info()
                        cpu = ps_process.cpu_percent(interval=0.1)

                        peak_memory = max(peak_memory, mem_info.rss / (1024 * 1024))  # in MB
                        cpu_usage.append(cpu)
                        time.sleep(0.1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            monitor_thread = Thread(target=monitor)
            monitor_thread.start()

            try:
                stdout, stderr = process.communicate(timeout=timeout)
                monitor_thread.join()
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                monitor_thread.join()
                result.update({
                    "exit_code": -1,
                    "cpu_usage_avg": sum(cpu_usage)/len(cpu_usage) if cpu_usage else 0,
                    "cpu_usage_max": max(cpu_usage, default=0),
                    "memory_peak_mb": peak_memory,
                    "time": timeout,
                    "cpu_time": main_cpu_time,
                    "stderr": "Timeout reached",
                    "status": "TIMEOUT"
                })
                return result

            elapsed_time = time.time() - start_time
            cpu_without0 = [x for x in cpu_usage if x > 0]
            avg_cpu = sum(cpu_without0)/len(cpu_without0) if cpu_without0 else 0

            if process.returncode == 10:
                status = "SAT"
            elif process.returncode == 20:
                status = "UNSAT"
            else:
                status = "UNKNOWN"

            result.update({
                "exit_code": process.returncode,
                "cpu_usage_avg": avg_cpu,
                "cpu_usage_max": max(cpu_usage, default=0),
                "memory_peak_mb": peak_memory,
                "time": elapsed_time,
                "cpu_time": main_cpu_time,
                "stderr": stderr.strip(),
                "status": status,
                "ans": stdout.strip()
            })
            return result

        except Exception as e:
            if process and process.poll() is None:
                process.kill()
            result.update({
                "stderr": f"Execution error: {str(e)}",
                "memory_peak_mb": peak_memory,
                "time": time.time() - start_time
            })
            return result

    def log_results(self, results, output_path:Path="results.csv"):
        """
        Logs the results of one or more solver runs to a CSV file.

        Args:
            results (dict or list of dict): A result dictionary or list of results
                as returned by `run_solver`.
            output_path (str): Path to the output CSV file (default: "results.csv").

        Notes:
            If the file does not exist, a header row will be created automatically.
        """

        with open(output_path, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=results[0].keys() if isinstance(results, list) else results.keys())
            if not output_path.exists() or os.stat(output_path).st_size == 0:
                writer.writeheader()
            if isinstance(results, list):
                writer.writerows(results)
            else:
                writer.writerow(results)
