import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runner import Runner
from generic_executor import GenericExecutor
from custom_types import (
    ExecConfig, TestCase, Result, RawResult, RunnerError,
    EXIT_CODE_TIMEOUT
)
from parser_strategy import GenericParser, SATparser, ResultParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(name: str = "test_solver", cmd: str = "echo") -> ExecConfig:
    return ExecConfig(name=name, solver_type="SAT", cmd=cmd, options=["{input}"])


def _make_tc(tmp_path: Path, name: str = "test") -> TestCase:
    p = tmp_path / f"{name}.cnf"
    p.write_text("p cnf 1 1\n1 0\n")
    return TestCase(name=name, path=p, tc_type="SAT")


def _make_raw(exit_code: int = 0, stdout: str = "", stderr: str = "",
              timed_out: bool = False, launch_failed: bool = False,
              error: str = None, time: float = 0.5) -> RawResult:
    return RawResult(
        exit_code=exit_code, stdout=stdout, stderr=stderr,
        timed_out=timed_out, launch_failed=launch_failed,
        error=error, time=time, cpu_time=0.1, memory_peak_mb=1.0,
        cpu_avg=10.0
    )


def _make_runner(executor: GenericExecutor, parser: ResultParser = None) -> Runner:
    config = _make_config()
    return Runner(config, parser or GenericParser(), executor=executor)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestRunnerInit:
    def test_empty_cmd_raises(self):
        config = ExecConfig(name="bad", solver_type="SAT", cmd="")
        with pytest.raises(ValueError):
            Runner(config, GenericParser())

    def test_nonexistent_cmd_raises(self):
        config = ExecConfig(name="bad", solver_type="SAT", cmd="/nonexistent/solver")
        with pytest.raises(FileNotFoundError):
            Runner(config, GenericParser())

    def test_valid_cmd_accepted(self):
        config = _make_config(cmd="echo")
        runner = Runner(config, GenericParser())
        assert runner._name == "test_solver"

    def test_custom_executor_injected(self):
        executor = MagicMock(spec=GenericExecutor)
        config = _make_config()
        runner = Runner(config, GenericParser(), executor=executor)
        assert runner._executor is executor

    def test_parser_stored(self):
        parser = SATparser()
        config = _make_config()
        runner = Runner(config, parser)
        assert runner._parser is parser


# ---------------------------------------------------------------------------
# Input validation in run()
# ---------------------------------------------------------------------------

class TestRunValidation:
    def test_none_output_path_raises(self, tmp_path: Path):
        runner = _make_runner(MagicMock())
        tc = _make_tc(tmp_path)
        with pytest.raises(ValueError, match="output_path"):
            runner.run(tc, timeout=5, output_path=None)

    def test_missing_input_file_raises(self, tmp_path: Path):
        runner = _make_runner(MagicMock())
        tc = TestCase(name="missing", path=tmp_path / "nonexistent.cnf", tc_type="SAT")
        with pytest.raises(FileNotFoundError):
            runner.run(tc, timeout=5, output_path=tmp_path / "out.log")

    def test_negative_timeout_raises(self, tmp_path: Path):
        runner = _make_runner(MagicMock())
        tc = _make_tc(tmp_path)
        with pytest.raises(ValueError, match="positive"):
            runner.run(tc, timeout=-1, output_path=tmp_path / "out.log")


# ---------------------------------------------------------------------------
# RawResult → Result mapping
# ---------------------------------------------------------------------------

class TestResultMapping:
    def test_normal_exit_maps_fields(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(exit_code=10, stdout="s SATISFIABLE")
        runner = _make_runner(executor, parser=SATparser())
        tc = _make_tc(tmp_path)
        out = tmp_path / "out.log"
        result = runner.run(tc, timeout=5, output_path=out)
        assert result.solver == "test_solver"
        assert result.problem == "test"
        assert result.time == 0.5
        assert result.cpu_time == 0.1
        assert result.memory_peak_mb == 1.0
        assert result.cpu_usage_avg == 10.0

    def test_timeout_maps_to_timeout_status(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(timed_out=True)
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "TIMEOUT"
        assert result.exit_code == EXIT_CODE_TIMEOUT
        assert "timeout" in result.error.lower()

    def test_launch_failure_maps_to_error_status(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(launch_failed=True, error="No such file")
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "ERROR"
        assert "No such file" in result.error

    def test_negative_exit_code_maps_to_exit_error(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(exit_code=-9)
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "EXIT_ERROR"
        assert "SIGNAL 9" in result.error

    def test_raw_error_without_special_status_preserved(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(exit_code=0, error="some warning")
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "UNKNOWN"
        assert "some warning" in result.error

    def test_stdout_and_stderr_stripped(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="  hello  \n", stderr="  warn  \n")
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        #assert result.stdout == "hello"
        assert result.stderr == "warn"


# ---------------------------------------------------------------------------
# Parser integration
# ---------------------------------------------------------------------------

class TestParserIntegration:
    def test_parser_called_with_result(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="s SATISFIABLE", exit_code=10)
        runner = _make_runner(executor, parser=SATparser())
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "SAT"

    def test_parser_failure_sets_parser_error(self, tmp_path: Path):
        class BrokenParser(GenericParser):
            def parse(self, result, output_path=None):
                raise RuntimeError("boom")

        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(exit_code=0)
        runner = _make_runner(executor, parser=BrokenParser())
        tc = _make_tc(tmp_path)
        result = runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
        assert result.status == "PARSER_ERROR"
        assert "boom" in result.error

    def test_parser_receives_output_path_when_exists(self, tmp_path: Path):
        mock_parser = MagicMock(spec=ResultParser)
        mock_parser.parse.return_value = Result(solver="test", status="SAT")

        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()

        runner = _make_runner(executor, parser=mock_parser)
        tc = _make_tc(tmp_path)
        out = tmp_path / "out.log"
        out.write_text("some output")
        runner.run(tc, timeout=5, output_path=out)

        mock_parser.parse.assert_called_once()
        call_kwargs = mock_parser.parse.call_args
        assert call_kwargs.kwargs.get("output_path") == out or call_kwargs[1].get("output_path") == out


# ---------------------------------------------------------------------------
# Executor exception handling
# ---------------------------------------------------------------------------

class TestExecutorExceptions:
    def test_executor_exception_raises_runner_error(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.side_effect = OSError("disk full")
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        with pytest.raises(RunnerError, match="disk full"):
            runner.run(tc, timeout=5, output_path=tmp_path / "out.log")

    def test_keyboard_interrupt_propagates(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.side_effect = KeyboardInterrupt
        runner = _make_runner(executor)
        tc = _make_tc(tmp_path)
        with pytest.raises(KeyboardInterrupt):
            runner.run(tc, timeout=5, output_path=tmp_path / "out.log")
