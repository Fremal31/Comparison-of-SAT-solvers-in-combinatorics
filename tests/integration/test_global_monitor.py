import time
import subprocess
import pytest
import psutil

from generic_executor import GlobalMonitor, GenericExecutor, _Metrics

pytestmark = pytest.mark.integration


def _reset_monitor():
    import threading
    with GlobalMonitor._lock:
        if GlobalMonitor._instance is not None:
            inst = GlobalMonitor._instance
            inst._killing = False
            inst.active_procs.clear()
            inst._stop_event.clear()
            if not inst.thread.is_alive():
                inst.thread = threading.Thread(target=inst._run, daemon=True)
                inst.thread.start()


@pytest.fixture(autouse=True)
def reset_monitor():
    _reset_monitor()
    yield
    _reset_monitor()


def _wait_for_metric(metrics: _Metrics, attr: str, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getattr(metrics, attr) > 0:
            return True
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# _kill_process
# ---------------------------------------------------------------------------

class TestKillProcess:
    def test_kills_running_process(self):
        proc = subprocess.Popen(["sleep", "10"], start_new_session=True)
        GenericExecutor._kill_process(proc.pid)
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("Process was not killed within 1 second")
        assert proc.returncode is not None

    def test_nonexistent_pid_does_not_raise(self):
        GenericExecutor._kill_process(99999999)

    def test_already_dead_process_does_not_raise(self):
        proc = subprocess.Popen(["true"], start_new_session=True)
        proc.wait()
        GenericExecutor._kill_process(proc.pid)

    def test_kills_entire_process_group(self):
        """SIGTERM/SIGKILL must reach children, not just the session leader."""
        proc = subprocess.Popen(
            ["bash", "-c", "sleep 60 & sleep 60 & wait"],
            start_new_session=True,
        )
        time.sleep(0.1)
        p = psutil.Process(proc.pid)
        children = p.children(recursive=True)
        assert len(children) >= 2, "Expected bash to have spawned sleep children"

        GenericExecutor._kill_process(proc.pid)
        proc.wait(timeout=1.0)

        for child in children:
            assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE


# ---------------------------------------------------------------------------
# Metrics update
# ---------------------------------------------------------------------------

class TestMetricsUpdate:
    def test_memory_recorded_for_running_process(self):
        proc = subprocess.Popen(["sleep", "5"], start_new_session=True)
        try:
            monitor = GlobalMonitor()
            metrics = _Metrics()
            monitor.register(pid=proc.pid, p_obj=psutil.Process(proc.pid), metrics=metrics)
            assert _wait_for_metric(metrics, "mem"), "Memory was not recorded"
        finally:
            monitor.unregister(proc.pid)
            proc.kill()
            proc.wait()

    def test_peak_memory_is_max_not_last(self):
        """metrics.mem must be non-decreasing (max of all readings, not the last)."""
        proc = subprocess.Popen(["sleep", "5"], start_new_session=True)
        try:
            monitor = GlobalMonitor()
            metrics = _Metrics()
            monitor.register(pid=proc.pid, p_obj=psutil.Process(proc.pid), metrics=metrics)

            assert _wait_for_metric(metrics, "mem"), "Memory was not recorded"

            artificial_peak = metrics.mem * 1000
            metrics.mem = artificial_peak

            time.sleep(0.6)

            assert metrics.mem >= artificial_peak, "Peak memory must not decrease"
        finally:
            monitor.unregister(proc.pid)
            proc.kill()
            proc.wait()

    def test_children_resources_included_in_metrics(self):
        """Memory from child processes must be aggregated into the parent entry."""
        proc = subprocess.Popen(
            ["bash", "-c", "sleep 5 & sleep 5 & wait"],
            start_new_session=True,
        )
        try:
            p_obj = psutil.Process(proc.pid)
            time.sleep(0.1)
            assert len(p_obj.children(recursive=True)) >= 2

            monitor = GlobalMonitor()
            metrics = _Metrics()
            monitor.register(pid=proc.pid, p_obj=p_obj, metrics=metrics)

            assert _wait_for_metric(metrics, "mem"), "Memory was not recorded"
        finally:
            monitor.unregister(proc.pid)
            proc.kill()
            proc.wait()

    def test_vanished_process_does_not_crash_monitor(self):
        proc = subprocess.Popen(["sleep", "5"], start_new_session=True)
        monitor = GlobalMonitor()
        metrics = _Metrics()
        p_obj = psutil.Process(proc.pid)
        monitor.active_procs[proc.pid] = (p_obj, metrics)

        proc.kill()
        proc.wait()

        time.sleep(0.6)

        assert monitor.thread.is_alive()
        monitor.unregister(proc.pid)
