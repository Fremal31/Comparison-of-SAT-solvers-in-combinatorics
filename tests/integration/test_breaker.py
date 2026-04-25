import stat
import pytest
from pathlib import Path

from breaker import SymmetryBreaker
from custom_types import ExecConfig, TestCase, ExecutionTriplet, Status
from format_types import ExperimentContext, SolvingTask
from generic_executor import GenericExecutor
from metadata_registry import resolve_format_metadata
from conftest import SIMPLE_CNF

pytestmark = pytest.mark.integration


def make_breaker_exec(path: Path) -> ExecConfig:
    return ExecConfig(name="test_breaker", solver_type="SAT", cmd=str(path), options=["{input}", "{output}"])


def make_solver_exec(tmp_path: Path) -> ExecConfig:
    p = tmp_path / "dummy_solver.sh"
    p.write_text("#!/bin/bash\necho 's SATISFIABLE'\nexit 10\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return ExecConfig(name="dummy_solver", solver_type="SAT", cmd=str(p), options=["{input}"])


def make_task(breaker_exec: ExecConfig, solver_exec: ExecConfig, test_case: TestCase, tmp_path: Path) -> SolvingTask:
    triplet = ExecutionTriplet(problem=None, formulator=None, solver=solver_exec, breaker=breaker_exec)
    fmt = resolve_format_metadata("SAT")
    ctx = ExperimentContext(base_path=tmp_path, log_dir=tmp_path, format_info=fmt)
    return SolvingTask(triplet=triplet, test_case=test_case, timeout=5.0, work_dir=ctx)


# ---------------------------------------------------------------------------
# Successful break
# ---------------------------------------------------------------------------

class TestSymmetryBreakerSuccess:
    def test_returns_new_test_case(self, tmp_path: Path):
        p = tmp_path / "good_breaker.sh"
        p.write_text("#!/bin/bash\ncp \"$1\" \"$2\"\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        tc = TestCase(name="simple", path=SIMPLE_CNF, tc_type="SAT")
        task = make_task(make_breaker_exec(p), make_solver_exec(tmp_path), tc, tmp_path)
        processed_tc, br_res = SymmetryBreaker(GenericExecutor()).apply(task, core_ids=[])

        assert processed_tc is not None
        assert processed_tc.path != tc.path

    def test_break_time_recorded(self, tmp_path: Path):
        p = tmp_path / "good_breaker.sh"
        p.write_text("#!/bin/bash\ncp \"$1\" \"$2\"\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        tc = TestCase(name="simple", path=SIMPLE_CNF, tc_type="SAT")
        task = make_task(make_breaker_exec(p), make_solver_exec(tmp_path), tc, tmp_path)
        _, br_res = SymmetryBreaker(GenericExecutor()).apply(task, core_ids=[])

        assert br_res.time >= 0


# ---------------------------------------------------------------------------
# Breaker failure modes → all must produce Status.BREAKER_ERROR
# ---------------------------------------------------------------------------

class TestSymmetryBreakerFailures:
    def test_crash_produces_breaker_error(self, tmp_path: Path):
        """Non-timeout crash must produce BREAKER_ERROR, not TIMEOUT."""
        p = tmp_path / "crash_breaker.sh"
        p.write_text("#!/bin/bash\nexit 1\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        tc = TestCase(name="simple", path=SIMPLE_CNF, tc_type="SAT")
        task = make_task(make_breaker_exec(p), make_solver_exec(tmp_path), tc, tmp_path)
        processed_tc, br_res = SymmetryBreaker(GenericExecutor()).apply(task, core_ids=[])

        assert processed_tc is None
        assert br_res.status == Status.BREAKER_ERROR

    def test_timeout_produces_breaker_error(self, tmp_path: Path):
        p = tmp_path / "slow_breaker.sh"
        p.write_text("#!/bin/bash\nsleep 10\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        tc = TestCase(name="simple", path=SIMPLE_CNF, tc_type="SAT")
        breaker_exec = ExecConfig(name="slow_breaker", solver_type="SAT", cmd=str(p), options=["{input}", "{output}"])
        triplet = ExecutionTriplet(problem=None, formulator=None, solver=make_solver_exec(tmp_path), breaker=breaker_exec)
        fmt = resolve_format_metadata("SAT")
        ctx = ExperimentContext(base_path=tmp_path, log_dir=tmp_path, format_info=fmt)
        task = SolvingTask(triplet=triplet, test_case=tc, timeout=0.1, work_dir=ctx)

        processed_tc, br_res = SymmetryBreaker(GenericExecutor()).apply(task, core_ids=[])

        assert processed_tc is None
        assert br_res.status == Status.TIMEOUT

    def test_empty_output_produces_breaker_error(self, tmp_path: Path):
        """Breaker exits 0 but writes nothing to output → BREAKER_ERROR."""
        p = tmp_path / "no_output_breaker.sh"
        p.write_text("#!/bin/bash\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        tc = TestCase(name="simple", path=SIMPLE_CNF, tc_type="SAT")
        task = make_task(make_breaker_exec(p), make_solver_exec(tmp_path), tc, tmp_path)
        processed_tc, br_res = SymmetryBreaker(GenericExecutor()).apply(task, core_ids=[])

        assert processed_tc is None
        assert br_res.status == Status.BREAKER_ERROR
