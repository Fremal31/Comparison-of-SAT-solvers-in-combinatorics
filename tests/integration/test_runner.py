import pytest
import stat
from pathlib import Path

from custom_types import ExecConfig, TestCase, Result
from parser_strategy import SATparser, GenericParser
from runner import Runner
from conftest import SIMPLE_CNF, UNSAT_CNF

pytestmark = pytest.mark.integration


def make_runner(solver_path: Path, options: list = None, parser=None) -> Runner:
    config = ExecConfig(
        name="test_solver",
        solver_type="SAT",
        cmd=str(solver_path),
        options=options or ["{input}"],
    )
    return Runner(config, parser or GenericParser())


def make_tc(path: Path, name: str = "test") -> TestCase:
    return TestCase(name=name, path=path, tc_type="SAT")


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------

class TestRunnerBasicExecution:
    def test_sat_result(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver, parser=SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "SAT"
        assert result.exit_code == 10

    def test_unsat_result(self, unsat_solver: Path, tmp_path: Path):
        runner = make_runner(unsat_solver, parser=SATparser())
        result = runner.run(make_tc(UNSAT_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "UNSAT"
        assert result.exit_code == 20

    def test_result_has_solver_and_problem_name(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF, name="my_problem"), timeout=5, output_path=tmp_path / "out.log")
        assert result.solver == "test_solver"
        assert result.problem == "my_problem"

    def test_time_is_positive(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.time > 0

    def test_memory_peak_is_non_negative(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.memory_peak_mb >= 0

    def test_output_log_created(self, sat_solver: Path, tmp_path: Path):
        out = tmp_path / "out.log"
        runner = make_runner(sat_solver)
        runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=out)
        assert out.exists()

    def test_cpu_time_is_non_negative(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.cpu_time >= 0

    def test_cpu_usage_avg_is_non_negative(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.cpu_usage_avg >= 0

    def test_cpu_usage_max_is_non_negative(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.cpu_usage_max >= 0

    def test_break_time_defaults_to_zero(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.break_time == 0.0

    def test_exit_code_set_on_normal_exit(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver, parser=SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.exit_code == 10

    def test_solver_stderr_captured(self, tmp_path: Path):
        p = tmp_path / "stderr_solver.sh"
        p.write_text("#!/bin/bash\necho 'some error' >&2\necho 's SATISFIABLE'\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        runner = make_runner(p, parser=SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert "some error" in result.stderr

    def test_solver_no_output_status_unknown(self, tmp_path: Path):
        p = tmp_path / "silent_solver.sh"
        p.write_text("#!/bin/bash\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        runner = make_runner(p)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "UNKNOWN"

    def test_large_output_does_not_crash(self, tmp_path: Path):
        p = tmp_path / "large_output_solver.sh"
        p.write_text("#!/bin/bash\npython3 -c 'print(\"c comment\" * 10000)'\necho 's SATISFIABLE'\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        runner = make_runner(p, parser=SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "SAT"

    def test_embedded_input_token_in_flag(self, tmp_path: Path):
        """Solver receiving input as --file=/path/to/input."""
        p = tmp_path / "flag_solver.sh"
        p.write_text("#!/bin/bash\necho 's SATISFIABLE'\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        config = ExecConfig(name="flag_solver", solver_type="SAT", cmd=str(p), options=["--file={input}"])
        runner = Runner(config, SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "SAT"


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestRunnerTimeout:
    def test_timeout_sets_status(self, timeout_solver: Path, tmp_path: Path):
        runner = make_runner(timeout_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=0.5, output_path=tmp_path / "out.log")
        assert result.status == "TIMEOUT"

    def test_timeout_sets_exit_code(self, timeout_solver: Path, tmp_path: Path):
        runner = make_runner(timeout_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=0.5, output_path=tmp_path / "out.log")
        assert result.exit_code == -1

    def test_timeout_sets_error_message(self, timeout_solver: Path, tmp_path: Path):
        runner = make_runner(timeout_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=0.5, output_path=tmp_path / "out.log")
        assert "timeout" in result.error.lower()

    def test_zero_timeout_triggers_timeout(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=0, output_path=tmp_path / "out.log")
        assert result.status == "TIMEOUT"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestRunnerErrors:
    def test_missing_input_file_raises(self, sat_solver: Path, tmp_path: Path):
        runner = make_runner(sat_solver)
        tc = TestCase(name="missing", path=tmp_path / "nonexistent.cnf", tc_type="SAT")
        with pytest.raises(FileNotFoundError):
            runner.run(tc, timeout=5, output_path=tmp_path / "out.log")

    def test_none_output_path_raises(self, sat_solver: Path):
        runner = make_runner(sat_solver)
        with pytest.raises(ValueError):
            runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=None)

    def test_nonexistent_solver_raises(self, tmp_path: Path):
        config = ExecConfig(
            name="bad_solver",
            solver_type="SAT",
            cmd=str(tmp_path / "nonexistent_solver"),
            options=["{input}"],
        )
        with pytest.raises(FileNotFoundError):
            Runner(config, GenericParser())

    def test_signal_termination_sets_exit_error(self, tmp_path: Path):
        p = tmp_path / "signal_solver.sh"
        p.write_text("#!/bin/bash\nkill -9 $$\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        runner = make_runner(p)
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "EXIT_ERROR"
        assert result.exit_code < 0

    def test_parser_failure_sets_parser_error(self, tmp_path: Path):
        class BrokenParser(GenericParser):
            def parse(self, result, output_path=None):
                raise RuntimeError("parser exploded")
        p = tmp_path / "sat_solver.sh"
        p.write_text("#!/bin/bash\necho 's SATISFIABLE'\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        config = ExecConfig(name="test", solver_type="SAT", cmd=str(p), options=["{input}"])
        runner = Runner(config, BrokenParser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "PARSER_ERROR"
        assert "parser exploded" in result.error


# ---------------------------------------------------------------------------
# stdin / stdout options
# ---------------------------------------------------------------------------

class TestRunnerOptions:
    def test_stdin_input(self, tmp_path: Path):
        """Solver that reads from stdin should work with < token."""
        p = tmp_path / "stdin_solver.sh"
        p.write_text("#!/bin/bash\ncat > /dev/null\necho 's SATISFIABLE'\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        config = ExecConfig(name="stdin_solver", solver_type="SAT", cmd=str(p), options=["<"])
        runner = Runner(config, SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "SAT"

    def test_stdout_redirect(self, tmp_path: Path):
        """Solver that writes to stdout should work with > token."""
        p = tmp_path / "stdout_solver.sh"
        p.write_text("#!/bin/bash\necho 's SATISFIABLE'\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        out = tmp_path / "out.log"
        config = ExecConfig(name="stdout_solver", solver_type="SAT", cmd=str(p), options=[">", "{input}"])
        runner = Runner(config, SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=out)
        assert out.exists()
        assert "SATISFIABLE" in out.read_text()

    def test_output_token(self, tmp_path: Path):
        """Solver that writes to a file via {output} flag."""
        p = tmp_path / "file_solver.sh"
        p.write_text("#!/bin/bash\necho 's SATISFIABLE' > $1\nexit 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        out = tmp_path / "out.log"
        config = ExecConfig(name="file_solver", solver_type="SAT", cmd=str(p), options=["{output}"])
        runner = Runner(config, SATparser())
        result = runner.run(make_tc(SIMPLE_CNF), timeout=5, output_path=out)
        assert result.status == "SAT"
