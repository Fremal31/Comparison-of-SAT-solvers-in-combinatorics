import subprocess
import time
import os
import psutil
from threading import Thread
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union, Final, Any, IO, cast
import shutil

from parser_strategy import ResultParser
from custom_types import (
    ExecConfig, TestCase, Result, RunnerError,
    STATUS_EXIT_ERROR, STATUS_TIMEOUT, STATUS_PARSER_ERROR
)
from cmd_builder import build_cmd



TIMEOUT: Final = -1


class Runner:
    """
    Executes a solver subprocess, monitors resource usage via a background thread,
    and parses the output into a Result using the configured parser strategy.
    """

    def __init__(self, config: ExecConfig, strategy: ResultParser) -> None:
        """
        Raises FileNotFoundError if *config.cmd* is not found on PATH or filesystem.
        """
        self._cmd = config.cmd
        if not shutil.which(self._cmd):
            raise FileNotFoundError(f"Solver command or path not found: {self._cmd}")
        self._name: str = config.name
        self._options: List[str] = config.options
        self._type: str = config.solver_type
        self._strategy: ResultParser = strategy

    @property
    def strategy(self) -> ResultParser:
        return self._strategy
    
    @strategy.setter
    def strategy(self, strategy: ResultParser) -> None:
        self._strategy = strategy

    def run(self, input_file: TestCase, timeout: Optional[float], output_path: Optional[Path] = None) -> Result:
        """
        Runs the solver on *input_file* and returns a populated Result.

        Spawns a background monitor thread that samples CPU and memory every 100ms.
        If *timeout* is exceeded the process is killed and the result status is set
        to TIMEOUT. Output is parsed by the configured strategy after the process exits.

        Raises ValueError if *output_path* is None, FileNotFoundError if the input
        file does not exist, and RunnerError on unexpected subprocess failures.
        """
        if output_path is None:
            raise ValueError(f"output_path must be provided for solver '{self._name}'")
        if not Path(input_file.path).exists():
            raise FileNotFoundError(f"Input file not found: {input_file.path}")
        
        input_path: Path = Path(input_file.path)
        result_cmd = build_cmd(self._cmd, self._options, input_file.path, output_path)
        cmd, use_stdin, pipe_to_file = result_cmd.cmd, result_cmd.use_stdin, result_cmd.use_stdout_pipe

        in_f: Optional[IO[str]] = None
        out_f: Union[IO[str], int] = subprocess.PIPE

        start_time: float = time.time()
        metrics: Dict[str, Any] = {
            "peak_memory": 0.0,
            "cpu_usage": cast(List[float], []),
            "cpu_time": 0.0
        }
        stdout, stderr = "", ""
        
        result: Result = Result(solver=self._name, problem=input_file.name)

        #print(f"Running {self._name} on {input_file.name}.")
        process: Optional[subprocess.Popen[str]] = None
        try:
            if use_stdin:
                in_f = open(input_path, "r")

            out_f = open(output_path, "w") if pipe_to_file else subprocess.PIPE
            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=in_f,
                    stdout=out_f,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True
                )
            except (OSError, ValueError) as e:
                raise RunnerError(f"Failed to start process '{self._cmd}': {e}")

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
                

            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), 9)
                stdout, stderr = process.communicate()
                result.status = STATUS_TIMEOUT
                result.exit_code = TIMEOUT
                result.error = (result.error + "\nProcess killed due to timeout.").strip()

            
            monitor_thread.join(timeout=1.0) 

        except RunnerError:
            raise

        except KeyboardInterrupt:
            print("\n[!] User interrupted execution. Cleaning up...")
            if process and process.poll() is None:
                os.killpg(os.getpgid(process.pid), 9)
            raise

        except Exception as e:
            if process and process.poll() is None:
                os.killpg(os.getpgid(process.pid), 9)
            raise RunnerError(f"Internal Runner failure: {e}")

        finally:
            if in_f:
                in_f.close()
            if hasattr(out_f, 'close'):
                out_f.close()

        usage_logs: List[float] = metrics["cpu_usage"]
        result.cpu_usage_avg = sum(usage_logs) / len(usage_logs) if usage_logs else 0
        result.cpu_usage_max = max(usage_logs, default=0)
        result.memory_peak_mb = metrics["peak_memory"]
        result.time = time.time() - start_time
        result.cpu_time = metrics["cpu_time"]

        new_stderr = stderr.strip() if stderr else ""
        result.stderr = f"{result.stderr}\n{new_stderr}".strip() if result.stderr else new_stderr
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
