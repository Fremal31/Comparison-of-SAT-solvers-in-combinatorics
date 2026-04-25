import threading
import pytest
import psutil
from unittest.mock import patch, MagicMock

from generic_executor import GlobalMonitor, GenericExecutor, _Metrics


def _reset_monitor():
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


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        assert GlobalMonitor() is GlobalMonitor()

    def test_monitoring_thread_is_running(self):
        assert GlobalMonitor().thread.is_alive()


# ---------------------------------------------------------------------------
# register / unregister
# ---------------------------------------------------------------------------

class TestRegisterUnregister:
    def test_register_adds_pid(self):
        monitor = GlobalMonitor()
        monitor.register(pid=1234, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())
        assert 1234 in monitor.active_procs

    def test_unregister_removes_pid(self):
        monitor = GlobalMonitor()
        monitor.register(pid=1234, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())
        monitor.unregister(1234)
        assert 1234 not in monitor.active_procs

    def test_unregister_unknown_pid_is_safe(self):
        GlobalMonitor().unregister(99999)

    def test_register_does_not_kill_when_not_in_kill_mode(self):
        with patch.object(GenericExecutor, '_kill_process') as mock_kill:
            GlobalMonitor().register(pid=1234, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())
        mock_kill.assert_not_called()


# ---------------------------------------------------------------------------
# kill_all
# ---------------------------------------------------------------------------

class TestKillAll:
    def test_sets_killing_flag(self):
        monitor = GlobalMonitor()
        assert not monitor._killing
        with patch.object(GenericExecutor, '_kill_process'):
            monitor.kill_all()
        assert monitor._killing

    def test_kills_all_registered_pids(self):
        monitor = GlobalMonitor()
        mock_p = MagicMock(spec=psutil.Process)
        monitor.active_procs[1234] = (mock_p, _Metrics())
        monitor.active_procs[5678] = (mock_p, _Metrics())

        with patch.object(GenericExecutor, '_kill_process') as mock_kill:
            monitor.kill_all()

        assert mock_kill.call_count == 2
        mock_kill.assert_any_call(1234)
        mock_kill.assert_any_call(5678)

    def test_kills_nothing_when_no_procs_registered(self):
        with patch.object(GenericExecutor, '_kill_process') as mock_kill:
            GlobalMonitor().kill_all()
        mock_kill.assert_not_called()


# ---------------------------------------------------------------------------
# _killing flag: late registration
# ---------------------------------------------------------------------------

class TestKillingFlag:
    def test_register_after_kill_all_kills_immediately(self):
        monitor = GlobalMonitor()
        with patch.object(GenericExecutor, '_kill_process') as mock_kill:
            monitor.kill_all()
            mock_kill.reset_mock()
            monitor.register(pid=9999, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())
            mock_kill.assert_called_once_with(9999)

    def test_killing_flag_persists_across_registrations(self):
        monitor = GlobalMonitor()
        with patch.object(GenericExecutor, '_kill_process') as mock_kill:
            monitor.kill_all()
            mock_kill.reset_mock()
            monitor.register(pid=1111, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())
            monitor.register(pid=2222, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())
        assert mock_kill.call_count == 2

    def test_concurrent_register_and_kill_all(self):
        """Processes registered concurrently with kill_all must all be killed."""
        monitor = GlobalMonitor()
        killed = []
        barrier = threading.Barrier(2)

        def register_many():
            barrier.wait()
            for pid in range(100, 110):
                monitor.register(pid=pid, p_obj=MagicMock(spec=psutil.Process), metrics=_Metrics())

        with patch.object(GenericExecutor, '_kill_process', side_effect=lambda pid: killed.append(pid)):
            t = threading.Thread(target=register_many)
            t.start()
            barrier.wait()
            monitor.kill_all()
            t.join()

        for pid in range(100, 110):
            assert pid in killed, f"pid {pid} was registered but never killed"


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_halts_monitoring_thread(self):
        monitor = GlobalMonitor()
        assert monitor.thread.is_alive()
        monitor.stop()
        monitor.thread.join(timeout=2.0)
        assert not monitor.thread.is_alive()
