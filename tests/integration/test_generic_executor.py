import pytest
import sys
import stat
from pathlib import Path

from generic_executor import GenericExecutor
from custom_types import RawResult

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_script(tmp_path: Path, name: str, content: str) -> str:
    p = tmp_path / name
    p.write_text(content)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestExecuteValidation:
    def test_empty_cmd_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            GenericExecutor().execute(cmd=[], timeout=5)

    def test_none_timeout_is_allowed(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=None)
        assert res.exit_code == 0


# ---------------------------------------------------------------------------
# Normal execution
# ---------------------------------------------------------------------------

class TestExecuteNormal:
    def test_captures_stdout(self, tmp_path: Path):
        script = _make_script(tmp_path, "echo.sh", "#!/bin/bash\necho hello\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert "hello" in res.stdout
        assert res.exit_code == 0

    def test_captures_stderr(self, tmp_path: Path):
        script = _make_script(tmp_path, "err.sh", "#!/bin/bash\necho oops >&2\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert "oops" in res.stderr

    def test_exit_code_preserved(self, tmp_path: Path):
        script = _make_script(tmp_path, "exit42.sh", "#!/bin/bash\nexit 42\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.exit_code == 42

    def test_time_is_positive(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.time > 0

    def test_timed_out_is_false(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.timed_out is False

    def test_launch_failed_is_false(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.launch_failed is False

    def test_error_is_none(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.error is None


# ---------------------------------------------------------------------------
# stdin / stdout paths
# ---------------------------------------------------------------------------

class TestExecuteIO:
    def test_stdin_path_fed_to_process(self, tmp_path: Path):
        input_file = tmp_path / "input.txt"
        input_file.write_text("hello from stdin")
        script = _make_script(tmp_path, "cat.sh", "#!/bin/bash\ncat\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5, stdin_path=str(input_file))
        assert "hello from stdin" in res.stdout

    def test_stdout_path_redirects_output(self, tmp_path: Path):
        out_file = tmp_path / "output.txt"
        script = _make_script(tmp_path, "echo.sh", "#!/bin/bash\necho redirected\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5, stdout_path=str(out_file))
        assert out_file.exists()
        assert "redirected" in out_file.read_text()
        assert res.stdout == ""

    def test_both_stdin_and_stdout_paths(self, tmp_path: Path):
        input_file = tmp_path / "input.txt"
        input_file.write_text("pipe me")
        out_file = tmp_path / "output.txt"
        script = _make_script(tmp_path, "cat.sh", "#!/bin/bash\ncat\nexit 0\n")
        res = GenericExecutor().execute(
            cmd=[script], timeout=5,
            stdin_path=str(input_file), stdout_path=str(out_file)
        )
        assert "pipe me" in out_file.read_text()


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestExecuteTimeout:
    def test_timeout_sets_timed_out(self, tmp_path: Path):
        script = _make_script(tmp_path, "slow.sh", "#!/bin/bash\nsleep 10\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=0.3)
        assert res.timed_out is True

    def test_timeout_does_not_set_launch_failed(self, tmp_path: Path):
        script = _make_script(tmp_path, "slow.sh", "#!/bin/bash\nsleep 10\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=0.3)
        assert res.launch_failed is False

    def test_zero_timeout(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=0)
        assert res.timed_out is True


# ---------------------------------------------------------------------------
# Launch failure
# ---------------------------------------------------------------------------

class TestExecuteLaunchFailure:
    def test_nonexistent_command_sets_launch_failed(self):
        res = GenericExecutor().execute(cmd=["/nonexistent/binary"], timeout=5)
        assert res.launch_failed is True
        assert res.error is not None

    def test_nonexistent_command_does_not_set_timed_out(self):
        res = GenericExecutor().execute(cmd=["/nonexistent/binary"], timeout=5)
        assert res.timed_out is False

    def test_nonexistent_stdin_path_sets_error(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5, stdin_path="/nonexistent/input")
        assert res.error is not None
        assert res.launch_failed is True


# ---------------------------------------------------------------------------
# Resource metrics
# ---------------------------------------------------------------------------

class TestExecuteMetrics:
    def test_memory_peak_non_negative(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.memory_peak_mb >= 0

    def test_cpu_avg_non_negative(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.cpu_avg >= 0

    def test_cpu_time_non_negative(self, tmp_path: Path):
        script = _make_script(tmp_path, "fast.sh", "#!/bin/bash\nexit 0\n")
        res = GenericExecutor().execute(cmd=[script], timeout=5)
        assert res.cpu_time >= 0
