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
import shutil

from parser_strategy import *
from custom_types import ExecConfig



TIMEOUT: Final = -1

class Runner:
    """
    Class to execute a SAT solver on a CNF file, monitor its performance,
    and collect statistics such as CPU usage, memory usage, and execution time.
    """

    def __init__(self, strategy: ResultParser = GenericParser()) -> None:
        """
        Initializes the Runner with a given solver binary path.

        Args:
            _cmd (str): Path to the SAT solver executable.

        Raises:
            FileNotFoundError: If the solver path does not exist.
        """
        self._strategy = strategy
        self._cmd: Optional[str] = None
        self._name: Optional[str] = None
        self._options: List[str] = []
        self._type: Optional[str] = None
        self._output_param: Optional[str] = None

    def setConfig(self, config: ExecConfig):
        #_cmd: Path = _config.path
        self._cmd = config.cmd
        if not shutil.which(self._cmd):
            raise FileNotFoundError(f"Solver command or path not found: {self._cmd}")
        self._name: str = config.name
        self._options: List[str] = config.options
        self._type: str = config.solver_type
        self._output_param: Optional[str] = config.output_param
        self._strategy = config.parser

    @property
    def strategy(self) -> ResultParser:
        return self._strategy
    
    @strategy.setter
    def strategy(self, strategy: ResultParser) -> None:
        self._strategy = strategy

    def run(self, input_file: TestCase, timeout: Optional[float], output_path: Path = None) -> Result:
        """
        Executes the SAT solver on the specified CNF file with a time limit.

        Monitors the solver's CPU and memory usage in a background thread,
        and returns performance metrics and solver result.

        Args:
            cnf_cmd (str): Path to the CNF input file.
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
        if self._cmd is None or self._name is None:
            raise RuntimeError("Config of the thing to run not set.")
        
        input_path: Path = Path(input_file.path)
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")
        
        if output_path is None:
            output_path = input_path.with_suffix(f"{input_path.suffix}.{self._name}.out")
            print(f"No output path specified. Using default: {output_path}")

        start_time: float = time.time()
        peak_memory: float = 0
        cpu_usage: List[float] = []
        main_cpu_time: float = 0.0

        result: Result = Result(solver=self._name, problem=input_file.name)
       
        cmd: List[str] = [str(self._cmd)] + self._options + [str(input_path)]
        
        out_destination = subprocess.PIPE
        file_handle = None

        # Special case for ">", because it cant be in the cmd
        if self._output_param == ">":
            file_handle = open(output_path, "w")
            out_destination = file_handle
        elif self._output_param:
            cmd += [self._output_param, str(output_path)]
        else:
            pass

        #print(f"Running {self._name} on {input_file.name}.")
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=out_destination,
                stderr=subprocess.PIPE,
                text=True
            )

            def monitor():
                nonlocal peak_memory, cpu_usage, main_cpu_time
                try:
                    parent = psutil.Process(process.pid)
                    while process.poll() is None:
                        all_processes = [parent] + parent.children(recursive=True)
                        current_mem, current_cpu, total_cpu_time = 0.0, 0.0, 0.0

                        for p in all_processes:
                            try:
                                with p.oneshot():
                                    current_mem += p.memory_info().rss / (1024 * 1024)
                                    current_cpu += p.cpu_percent()
                                    t = p.cpu_times()
                                    total_cpu_time += (t.user + t.system)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue

                        peak_memory = max(peak_memory, current_mem)
                        cpu_usage.append(current_cpu)
                        main_cpu_time = total_cpu_time
                        time.sleep(0.1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            monitor_thread = Thread(target=monitor, daemon=True)
            monitor_thread.start()

            try:
                stdout, stderr = process.communicate(timeout=timeout)
                result.exit_code = process.returncode

            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                result.status = "TIMEOUT"
                result.exit_code = -1
            
            monitor_thread.join(timeout=1.0) 

            if file_handle:
                file_handle.close()
               # if output_path.exists():
                  #  stdout = output_path.read_text()
                  #  if output_path not in input_file.generated_files:
                    #    input_file.generated_files.append(output_path)

            result.cpu_usage_avg = sum(cpu_usage) / len(cpu_usage) if cpu_usage else 0
            result.cpu_usage_max = max(cpu_usage, default=0)
            result.memory_peak_mb = peak_memory
            result.time = time.time() - start_time
            result.cpu_time = main_cpu_time
            result.stderr = stderr.strip() if stderr else ""
            result.stdout = stdout.strip() if stdout else ""

            if self._strategy:
                result = self._strategy.parse(result=result, output_path=output_path if self._output_param == ">" else None)
            
            return result

        except Exception as e:
            if process and process.poll() is None: 
                process.kill()
            if file_handle:
                file_handle.close()
            result.stderr = f"Execution error: {str(e)}"
            result.status = "ERROR"
            return result


    def log_results(self, results, output_cmd:Path=Path("results.csv")) -> None:
        """
        Logs the results of one or more solver runs to a CSV file.

        Args:
            results (dict or list of dict): A result dictionary or list of results
                as returned by `run`.
            output_cmd (str): Path to the output CSV file (default: "results.csv").

        Notes:
            If the file does not exist, a header row will be created automatically.
        """

        with open(output_cmd, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=results[0].keys() if isinstance(results, list) else results.keys())
            if not output_cmd.exists() or os.stat(output_cmd).st_size == 0:
                writer.writeheader()
            if isinstance(results, list):
                for res in results:
                    res_dict = asdict(res) if isinstance(res, Result) else res
                    writer.writerow(res_dict)
            else:
                res_dict = asdict(results) if isinstance(results, Result) else results
                writer.writerow(res_dict)
