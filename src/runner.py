import subprocess
import time
import os
import psutil
from threading import Thread
from pathlib import Path
import csv
from typing import List, Dict, Optional, Tuple, Union, Final, Any
from typing_extensions import Literal
from dataclasses import dataclass, field, asdict
import shutil

from parser_strategy import *
from custom_types import *



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
        TODO
        """

        assert self._cmd is not None, f"Path to solver is None: {self._cmd}"
        assert self._name is not None, f"Name of solver is None: {self._name}"

        input_path: Path = Path(input_file.path)
        assert Path(input_path).exists(), f"Input_path {input_file.path} doesnt exist"
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")
        
        assert output_path is not None, f"Output_path is None"
        if output_path is None:  # shouldnt happen
            output_path = input_path.with_suffix(f"{input_path.suffix}.{self._name}.out")
            print(f"No output path specified. Using default: {self._output_param}")
       
        cmd: List[str] = [str(self._cmd)] + self._options + [str(input_path)]
        
        out_destination = subprocess.PIPE
        file_handle = None

        # Special case for ">", because it cant be in the cmd
        if self._output_param == ">":
            file_handle = open(output_path, "w")
            out_destination = file_handle
        elif self._output_param:
            cmd += [self._output_param, str(output_path)]
        elif self._output_param == "":
            cmd += [str(output_path)]
        elif self._output_param is None:
            # output_param == None -> pipes to stdout
            pass
        else:
            raise RuntimeError(f"unexpected output_param")


        start_time: float = time.time()
        metrics: Dict[str, Any] = {
            "peak_memory": 0,
            "cpu_usage": [],
            "cpu_time": 0

        }
        stdout, stderr = "", ""

        result: Result = Result(solver=self._name, problem=input_file.name)
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
                try:
                    parent = psutil.Process(process.pid)
                    while process.poll() is None:
                        try:
                            with parent.oneshot():
                                mem: int = parent.memory_info().rss
                                cpu: float = parent.cpu_percent()
                                t = parent.cpu_times()
                                total_time: float = t.user + t.system
                                
                                children = parent.children(recursive=True)
                                for child in children:
                                    try:
                                        with child.oneshot():
                                            mem += child.memory_info().rss
                                            cpu += child.cpu_percent()
                                            t_child = child.cpu_times()
                                            total_time += (t_child.user + t_child.system)
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        continue
                                
                                metrics["peak_memory"] = max(metrics["peak_memory"], mem / (1024 * 1024))
                                metrics["cpu_usage"].append(cpu)
                                metrics["cpu_time"] = total_time
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                                break
                        time.sleep(0.1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
            monitor_thread = Thread(target=monitor, daemon=True)
            monitor_thread.start()

            try:
                stdout, stderr = process.communicate(timeout=timeout)
                result.exit_code = process.returncode

                if result.exit_code < 0:
                    sig_name:str = f"SIGNAL {abs(result.exit_code)}"
                    result.status = STATUS_EXIT_ERROR
                    result.error = (result.error + f"\nProcess terminated by {sig_name}").strip()
                
                if result.exit_code == 0 and self._output_param is not None and not output_path.exists():
                    result.status = STATUS_MISSING_OUTPUT
                    result.error += "\nProcess finished but output file was not found."


            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                result.status = STATUS_TIMEOUT
                result.exit_code = -1

            
            monitor_thread.join(timeout=1.0) 

        
        except KeyboardInterrupt:
            print("\n[!] User interrupted execution. Cleaning up...")
            if process and process.poll() is None:
                process.kill()
            raise

        except Exception as e:
            if process and process.poll() is None: 
                process.kill()
            result.error = f"Execution error: {str(e)}"
            result.status = STATUS_ERROR
            return result

        finally:
            if file_handle:
                file_handle.close()
               # if output_path.exists():
                  #  stdout = output_path.read_text()
                  #  if output_path not in input_file.generated_files:
                    #    input_file.generated_files.append(output_path)

            usage_logs: List[float] = metrics["cpu_usage"]
            result.cpu_usage_avg = sum(usage_logs) / len(usage_logs) if usage_logs else 0
            result.cpu_usage_max = max(usage_logs, default=0)

            result.memory_peak_mb = metrics["peak_memory"]

            result.time = time.time() - start_time
            result.cpu_time = metrics["cpu_time"]

            new_stderr = stderr.strip() if stderr else ""
            if result.stderr:
                result.stderr = f"{result.stderr}\n{new_stderr}".strip()
            else:
                result.stderr = new_stderr

            result.stdout = stdout.strip() if stdout else ""

            if self._strategy:
                p_path: Optional[Path] = None
                if output_path and output_path.exists():
                    p_path = output_path
                try:
                    result = self._strategy.parse(result=result, output_path=p_path)
                except Exception as e:
                    result.status = STATUS_PARSER_ERROR
                    result.error += f"\nParser failed: {e}"
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
