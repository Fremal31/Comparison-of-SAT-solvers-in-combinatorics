import subprocess
import time
import psutil
from threading import Thread
from dataclasses import dataclass
from typing import List, Optional, Any, IO
from contextlib import ExitStack

@dataclass
class RawResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    time: float = 0.0
    cpu_time: float = 0.0
    memory_peak_mb: float = 0.0
    cpu_avg: float = 0.0
    cpu_max: float = 0.0
    timed_out: bool = False
    error: Optional[str] = None

class GenericExecutor:
    def execute(self, cmd: List[str], timeout: Optional[float], 
                stdin_path: Optional[str] = None, 
                stdout_path: Optional[str] = None) -> RawResult:
        
        res = RawResult()
        metrics = {"mem": 0.0, "cpu_sum": 0.0, "cpu_count": 0, "cpu_max": 0.0, "cpu_time": 0.0}
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
                                    
                                    metrics["mem"] = max(metrics["mem"], mem / (1024 * 1024))
                                    metrics["cpu_sum"] += cpu
                                    metrics["cpu_count"] += 1
                                    metrics["cpu_max"] = max(metrics["cpu_max"], cpu)
                                    metrics["cpu_time"] = c_time
                            except (psutil.NoSuchProcess, psutil.AccessDenied): break
                            time.sleep(0.1)
                    except Exception: pass

                thread = Thread(target=monitor, daemon=True)
                thread.start()

                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    res.exit_code = process.returncode
                    res.stdout, res.stderr = stdout or "", stderr or ""
                except subprocess.TimeoutExpired:
                    res.timed_out = True
                    self._kill_process(process.pid)
                    stdout, stderr = process.communicate()
                    res.stdout, res.stderr = stdout or "", stderr or ""
                
                
            except KeyboardInterrupt:
                if process:
                    self._kill_process(process.pid)
                raise 
            
            except Exception as e:
                if process:
                    self._kill_process(process.pid)
                res.error = f"Internal Executor Error: {str(e)}"
            
            if thread:
                thread.join(timeout=0.5)

        res.time = time.perf_counter() - start_time
        res.memory_peak_mb = metrics["mem"]
        res.cpu_time = metrics["cpu_time"]
        res.cpu_max = metrics["cpu_max"]
        res.cpu_avg = metrics["cpu_sum"] / metrics["cpu_count"] if metrics["cpu_count"] > 0 else 0.0

        return res

    def _kill_process(self, pid: int) -> None:
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