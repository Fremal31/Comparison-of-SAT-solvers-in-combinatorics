import subprocess
import time
import psutil
import logging
import threading
import os
from dataclasses import dataclass
from typing import List, Optional, Callable, Tuple, Dict, NoReturn, TYPE_CHECKING
from contextlib import ExitStack
import shutil
import ctypes
import signal

from custom_types import RawResult, EXIT_CODE_TIMEOUT
if TYPE_CHECKING:
    from typing_extensions import Self

logger = logging.getLogger(__name__)

PR_SET_PDEATHSIG = 1

try:
    _libc: Optional[ctypes.CDLL] = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None

@dataclass
class _Metrics:
    mem: float = 0.0
    cpu_time: float = 0.0

class GlobalMonitor:
    _instance: Optional['GlobalMonitor'] = None
    _lock: threading.Lock = threading.Lock()
    active_procs: Dict[int, Tuple[psutil.Process, _Metrics]]
    thread: threading.Thread
    _stop_event: threading.Event
    _killing: bool

    def __new__(cls) -> 'GlobalMonitor':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.active_procs = {} # {pid: (psutil.Process, _Metrics)}
                cls._instance._killing = False
                cls._instance._stop_event = threading.Event()
                cls._instance.thread = threading.Thread(target=cls._instance._run, daemon=True)
                cls._instance.thread.start()
            return cls._instance

    def stop(self) -> None:
        self._stop_event.set()

    def kill_all(self) -> None:
        """Kills all registered processes and sets the killing flag so any
        process registered after this call is also killed immediately."""
        with self._lock:
            self._killing = True
            pids = list(self.active_procs.keys())
        for pid in pids:
            GenericExecutor._kill_process(pid)

    def register(self, pid: int, p_obj: psutil.Process, metrics: '_Metrics') -> None:
        with self._lock:
            self.active_procs[pid] = (p_obj, metrics)
            kill_immediately = self._killing
        if kill_immediately:
            GenericExecutor._kill_process(pid)

    def unregister(self, pid: int) -> None:
        with self._lock:
            self.active_procs.pop(pid, None)

    def _run(self) -> None:
        """The single thread that monitors cpu_time, peak memory for EVERYTHING."""
        while not self._stop_event.is_set():
            with self._lock:
                items: List[Tuple[int, Tuple[psutil.Process, _Metrics]]] = list(self.active_procs.items())
            logger.debug("Monitor Heartbeat - Still Running...")

            if items:
                children_map: Dict[int, List[psutil.Process]] = {}
                for pid, (p, _) in items:
                    try:
                        children_map[pid] = p.children(recursive=True)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        children_map[pid] = []

                for pid, (p, metrics) in items:
                    try:
                        with p.oneshot():
                            mem_bytes = p.memory_info().rss
                            t = p.cpu_times()
                            cpu_time = t.user + t.system
                        for child in children_map.get(pid, []):
                            try:
                                with child.oneshot():
                                    mem_bytes += child.memory_info().rss
                                    ct = child.cpu_times()
                                    cpu_time += ct.user + ct.system
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        metrics.cpu_time = cpu_time
                        mem_mb = mem_bytes / (1024 * 1024)
                        metrics.mem = max(metrics.mem, mem_mb)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            time.sleep(0.5)

class GenericExecutor:
    """Low-level subprocess executor with resource monitoring.

    Runs a command, tracks CPU/memory usage via a background thread,
    and returns a RawResult with no domain-specific interpretation.

    No input validation is performed beyond checking that *cmd* is non-empty.
    Callers are responsible for verifying paths, timeouts, and permissions.
    """
    def __init__(self, cleanup_on_crash: bool = False) -> None:
        self.cleanup_on_crash: bool = cleanup_on_crash

    @staticmethod
    def _linux_internal_cleanup() -> None:
        """Runs in child after fork, before exec."""
        if _libc is not None:
            try:
                _libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
            except Exception:
                pass


    def _apply_system_wrappers(self, cmd: List[str], core_ids: Optional[List[int]]) -> List[str]:
        """
        Wraps the command with OS-level utilities (e.g., taskset for affinity).
        Returns the modified command list.
        """
        if not core_ids:
            return cmd

        taskset_bin: Optional[str] = shutil.which("taskset")
        if not taskset_bin:
            raise RuntimeError(
                f"Affinity requested for cores {core_ids}, but 'taskset' was not found. "
                f"Please install 'util-linux' on your Linux system or set 'allowed cores' to null in config."
            )

        core_str: str = ",".join(map(str, core_ids))
        return [taskset_bin, "-c", core_str] + cmd
    
    def execute(self, cmd: List[str], timeout: Optional[float], 
                stdin_path: Optional[str] = None, 
                stdout_path: Optional[str] = None, core_ids: Optional[List[int]] = None) -> RawResult:
        """Executes *cmd* as a subprocess and returns a RawResult.

        If *stdin_path* is set, the file is fed to the process via stdin.
        If *stdout_path* is set, stdout is redirected to that file;
        otherwise it is captured via subprocess.PIPE into RawResult.stdout.
        """
        if not cmd:
            raise ValueError("cmd must be a non-empty list.")

        res = RawResult()
        metrics = _Metrics()
        process: Optional[subprocess.Popen[str]] = None
        thread: Optional[threading.Thread] = None

        start_time: float = time.perf_counter()
 
        final_cmd: List[str] = self._apply_system_wrappers(cmd=cmd, core_ids=core_ids)

        with ExitStack() as stack:
            try:
                in_f = stack.enter_context(open(stdin_path, "r")) if stdin_path else None
                out_f = stack.enter_context(open(stdout_path, "w")) if stdout_path else subprocess.PIPE

                process = subprocess.Popen(
                    final_cmd, stdin=in_f, stdout=out_f, stderr=subprocess.PIPE, text=True,
                    start_new_session=True,
                    preexec_fn=self._linux_internal_cleanup if self.cleanup_on_crash else None,
                )

                p = None
                try:
                    p = psutil.Process(process.pid)
                    GlobalMonitor().register(pid=process.pid, p_obj=p, metrics=metrics)
                except psutil.NoSuchProcess:
                    pass

                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    res.exit_code = process.returncode
                    res.stdout, res.stderr = stdout or "", stderr or ""
                except subprocess.TimeoutExpired:
                    res.timed_out = True
                    res.exit_code = EXIT_CODE_TIMEOUT
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
                if process:
                    GlobalMonitor().unregister(process.pid)

        res.time = time.perf_counter() - start_time
        res.memory_peak_mb = metrics.mem
        res.cpu_time = metrics.cpu_time
        res.cores_used = core_ids
        if res.time > 0:
            res.cpu_avg = (res.cpu_time / res.time) * 100.0
        else:
            res.cpu_avg = 0.0

        return res

    @staticmethod
    def _kill_process(pid: int) -> None:
        """Sends SIGTERM then SIGKILL to the process group of *pid*.

        start_new_session=True guarantees PGID == PID, so pid is used directly.
        Polls for up to 0.2s after SIGTERM and returns early if the group dies,
        avoiding an unconditional sleep on fast-exiting processes.
        """
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return

        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            try:
                os.killpg(pid, 0)
            except (ProcessLookupError, OSError):
                return
            time.sleep(0.02)

        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass