import subprocess
import time
import psutil
from threading import Thread
from dataclasses import dataclass
from typing import List, Optional
from contextlib import ExitStack

from custom_types import RawResult

@dataclass
class _Metrics:
    mem: float = 0.0
    cpu_sum: float = 0.0
    cpu_count: int = 0
    cpu_max: float = 0.0
    cpu_time: float = 0.0

class GenericExecutor:
    """Low-level subprocess executor with resource monitoring.

    Runs a command, tracks CPU/memory usage via a background thread,
    and returns a RawResult with no domain-specific interpretation.

    No input validation is performed beyond checking that *cmd* is non-empty.
    Callers are responsible for verifying paths, timeouts, and permissions.
    """

    def execute(self, cmd: List[str], timeout: Optional[float], 
                stdin_path: Optional[str] = None, 
                stdout_path: Optional[str] = None) -> RawResult:
        """Executes *cmd* as a subprocess and returns a RawResult.

        If *stdin_path* is set, the file is fed to the process via stdin.
        If *stdout_path* is set, stdout is redirected to that file;
        otherwise it is captured via subprocess.PIPE into RawResult.stdout.
        """
        if not cmd:
            raise ValueError("cmd must be a non-empty list.")

        res = RawResult()
        metrics = _Metrics()
        process: Optional[subprocess.Popen] = None
        thread: Optional[Thread] = None

        start_time = time.perf_counter()
 
        with ExitStack() as stack:
            try:
                in_f = stack.enter_context(open(stdin_path, "r")) if stdin_path else None
                out_f = stack.enter_context(open(stdout_path, "w")) if stdout_path else subprocess.PIPE

                process = subprocess.Popen(
                    cmd, stdin=in_f, stdout=out_f, stderr=subprocess.PIPE, text=True
                )

                def monitor() -> None:
                    try:
                        p = psutil.Process(process.pid)
                        p.cpu_percent()
                        while process.poll() is None:
                            try:
                                with p.oneshot():
                                    mem = p.memory_info().rss
                                    cpu = p.cpu_percent()
                                    t = p.cpu_times()
                                    c_time = t.user + t.system
                                    for child in p.children(recursive=True):
                                        try:
                                            with child.oneshot():
                                                mem += child.memory_info().rss
                                                cpu += child.cpu_percent()
                                                ct = child.cpu_times()
                                                c_time += (ct.user + ct.system)
                                        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
                                    
                                    metrics.mem = max(metrics.mem, mem / (1024 * 1024))
                                    metrics.cpu_sum += cpu
                                    metrics.cpu_count += 1
                                    metrics.cpu_max = max(metrics.cpu_max, cpu)
                                    metrics.cpu_time = c_time
                            except (psutil.NoSuchProcess, psutil.AccessDenied): break
                            time.sleep(0.1)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                thread = Thread(target=monitor, daemon=True)
                thread.start()

                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    res.exit_code = process.returncode
                    res.stdout, res.stderr = stdout or "", stderr or ""
                except subprocess.TimeoutExpired:
                    res.timed_out = True
                    GenericExecutor._kill_process(process.pid)
                    stdout, stderr = process.communicate()
                    res.stdout, res.stderr = stdout or "", stderr or ""
                
                
            except KeyboardInterrupt:
                if process:
                    GenericExecutor._kill_process(process.pid)
                raise 
            
            except Exception as e:
                if process:
                    GenericExecutor._kill_process(process.pid)
                res.launch_failed = process is None
                res.error = f"Internal Executor Error: {str(e)}"
            finally:
                if thread:
                    thread.join(timeout=0.5)

        res.time = time.perf_counter() - start_time
        res.memory_peak_mb = metrics.mem
        res.cpu_time = metrics.cpu_time
        res.cpu_max = metrics.cpu_max
        res.cpu_avg = metrics.cpu_sum / metrics.cpu_count if metrics.cpu_count > 0 else 0.0

        return res

    @staticmethod
    def _kill_process(pid: int) -> None:
        """Kills the process tree starting from pid using Terminate-Wait-Kill sequence."""
        try:
            parent = psutil.Process(pid)
            procs = parent.children(recursive=True) + [parent]
            for p in procs:
                try: p.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            
            gone, alive = psutil.wait_procs(procs, timeout=0.2)
            for p in alive:
                try: p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            
            psutil.wait_procs(alive, timeout=0.1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass