import subprocess
import time
import os
import psutil
from threading import Thread
from pathlib import Path
import csv
from typing import List, Dict, Optional, Tuple, Union, Final
from typing_extensions import Literal
from dataclasses import dataclass, field, asdict
from .parser import *





@dataclass
class TestCase:
    name: Optional[str]
    path: Union[str, Path]


@dataclass
class SolverConfig:
    name: str
    path: Path
    options: List[str] = field(default_factory=list)
    enabled: bool = True


TIMEOUT: Final = -1

class SolverRunner:
    """
    Class to execute a SAT solver on a CNF file, monitor its performance,
    and collect statistics such as CPU usage, memory usage, and execution time.
    """

    def __init__(self, solver_config: SolverConfig, strategy: ResultParser = SATparser()) -> None:
        """
        Initializes the SolverRunner with a given solver binary path.

        Args:
            solver_path (str): Path to the SAT solver executable.

        Raises:
            FileNotFoundError: If the solver path does not exist.
        """
        self._strategy = strategy
        #solver_path: Path = solver_config.path
        self.solver_path = solver_config.path
        if not os.path.exists(self.solver_path):
            raise FileNotFoundError(f"Solver path not found: {self.solver_path}")
        self.solver_name: str = solver_config.name
        self.solver_options: List[str] = solver_config.options
        
    @property
    def strategy(self) -> ResultParser:
        return self._strategy
    
    @strategy.setter
    def strategy(self, strategy: ResultParser) -> None:
        self._strategy = strategy

    def run_solver(self, cnf_file: TestCase, timeout: Optional[float]) -> SolverResult:
        """
        Executes the SAT solver on the specified CNF file with a time limit.

        Monitors the solver's CPU and memory usage in a background thread,
        and returns performance metrics and solver result.

        Args:
            cnf_path (str): Path to the CNF input file.
            timeout (int): Timeout in seconds after which the solver is forcefully stopped.

        Returns:
            !dict: A dictionary with statistics and solver result. Keys include:
                - 'exit_code': Exit code of the solver process.
                - 'cpu_usage_avg': Average CPU usage (%).
                - 'cpu_usage_max': Maximum CPU usage (%).
                - 'memory_peak_mb': Peak memory usage in MB.
                - 'time': Wall-clock time taken by the solver.
                - 'process_time': CPU time used by the solver.
                - 'stderr': Any error output from the solver.
                #- 'status': Result status ("SAT", "UNSAT", "TIMEOUT", or "UNKNOWN").
                - 'stdout': Solver's standard output (raw).

        Raises:
            FileNotFoundError: If the CNF input file does not exist.
        """
        cnf_path: Path = Path(cnf_file.path)
        if not os.path.exists(cnf_path):
            raise FileNotFoundError(f"CNF file not found: {cnf_path}")

        start_time: float = time.time()
        peak_memory: float = 0
        cpu_usage: List[float] = []
        main_cpu_time: float = 0.0

        result: SolverResult = SolverResult(
            solver=self.solver_path.name,
            original_cnf=cnf_file.name
        )
        cmd: List[Union[str, Path]] = [(self.solver_path)] + self.solver_options + [(cnf_path)]

        try:
            process = subprocess.Popen(
                cmd,
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
                result.status = "TIMEOUT"
                result.stderr = "Timeout reached"
                result.exit_code = -1
                result.cpu_usage_avg = (sum(cpu_usage) / len(cpu_usage)) if cpu_usage else 0
                result.cpu_usage_max = max(cpu_usage, default=0)
                result.memory_peak_mb = peak_memory
                result.time = timeout if timeout is not None else time.time() - start_time
                result.cpu_time = main_cpu_time
                return result

            elapsed_time = time.time() - start_time
            cpu_without0 = [x for x in cpu_usage]
            avg_cpu = sum(cpu_without0)/len(cpu_without0) if cpu_without0 else 0

           # if process.returncode == 10:
           #     result.status = "SAT"
           # elif process.returncode == 20:
           #     result.status = "UNSAT"
           # else:
           #     result.status = "UNKNOWN"

            result.exit_code = process.returncode
            result.cpu_usage_avg = avg_cpu
            result.cpu_usage_max = max(cpu_usage, default=0)
            result.memory_peak_mb = peak_memory
            result.time = elapsed_time
            result.cpu_time = main_cpu_time
            result.stderr = stderr.strip() if stderr else ""
            #result.status = status
            result.stdout = stdout.strip() if stdout else ""
            result.status = self._strategy.parse(result)
            return result

        except Exception as e:
            if process and process.poll() is None:
                process.kill()
            
            result.stderr = f"Execution error: {str(e)}"
            result.memory_peak_mb = peak_memory
            result.time = time.time() - start_time
            return result

    def log_results(self, results, output_path:Path=Path("results.csv")) -> None:
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
                for res in results:
                    res_dict = asdict(res) if isinstance(res, SolverResult) else res
                    writer.writerow(res_dict)
            else:
                res_dict = asdict(results) if isinstance(results, SolverResult) else results
                writer.writerow(res_dict)
