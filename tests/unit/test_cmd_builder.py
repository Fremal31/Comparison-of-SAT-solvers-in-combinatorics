import pytest
from pathlib import Path

from cmd_builder import build_cmd, CmdResult

INPUT  = Path("/tmp/input.cnf")
OUTPUT = Path("/tmp/output.log")
EXE    = "solver"


def cmd(options):
    return build_cmd(EXE, options, INPUT, OUTPUT)


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------

class TestInputToken:
    def test_input_token_replaced(self):
        result = cmd(["{input}"])
        assert str(INPUT) in result.cmd

    def test_input_auto_appended_when_absent(self):
        result = cmd(["-n"])
        assert str(INPUT) in result.cmd
        assert result.cmd == [EXE, "-n", str(INPUT)]

    def test_input_not_auto_appended_when_stdin(self):
        result = cmd(["<"])
        assert str(INPUT) not in result.cmd
        assert result.use_stdin is True

    def test_stdin_suppresses_explicit_input_token(self):
        result = cmd(["<", "{input}"])
        assert str(INPUT) not in result.cmd
        assert result.use_stdin is True

    def test_stdin_suppresses_embedded_input_token(self):
        result = cmd(["<", "--file={input}"])
        assert str(INPUT) not in result.cmd
        assert result.use_stdin is True

    def test_input_token_position_independent(self):
        result = cmd(["-n", "{input}", "-v"])
        assert result.cmd == [EXE, "-n", str(INPUT), "-v"]


# ---------------------------------------------------------------------------
# Output handling
# ---------------------------------------------------------------------------

class TestOutputToken:
    def test_output_token_replaced(self):
        result = cmd(["-o", "{output}"])
        assert str(OUTPUT) in result.cmd
        assert result.use_stdout_pipe is False

    def test_stdout_pipe_when_gt_only(self):
        result = cmd([">"])
        assert result.use_stdout_pipe is True
        assert str(OUTPUT) not in result.cmd

    def test_stdout_pipe_default_when_no_output_token(self):
        result = cmd(["{input}"])
        assert result.use_stdout_pipe is True

    def test_stdout_pipe_default_empty_options(self):
        result = cmd([])
        assert result.use_stdout_pipe is True

    def test_output_token_wins_over_gt(self):
        """When both > and {output} are present, {output} takes priority."""
        result = cmd([">", "-o", "{output}"])
        assert result.use_stdout_pipe is False
        assert str(OUTPUT) in result.cmd

    def test_embedded_output_token_replaced(self):
        result = cmd(["--out={output}"])
        assert f"--out={OUTPUT}" in result.cmd
        assert result.use_stdout_pipe is False


# ---------------------------------------------------------------------------
# Combined stdin + stdout
# ---------------------------------------------------------------------------

class TestCombined:
    def test_stdin_and_stdout_pipe(self):
        result = cmd(["<", ">"])
        assert result.use_stdin is True
        assert result.use_stdout_pipe is True
        assert str(INPUT) not in result.cmd

    def test_stdin_and_output_token(self):
        result = cmd(["<", "-o", "{output}"])
        assert result.use_stdin is True
        assert result.use_stdout_pipe is False
        assert str(OUTPUT) in result.cmd

    def test_all_tokens(self):
        result = cmd(["<", "{input}", ">"])
        assert result.use_stdin is True
        assert result.use_stdout_pipe is True
        assert str(INPUT) not in result.cmd


# ---------------------------------------------------------------------------
# Command structure
# ---------------------------------------------------------------------------

class TestCommandStructure:
    def test_executable_is_first(self):
        result = cmd(["{input}"])
        assert result.cmd[0] == EXE

    def test_control_chars_not_in_cmd(self):
        result = cmd(["<", ">"])
        assert "<" not in result.cmd
        assert ">" not in result.cmd

    def test_regular_flags_preserved(self):
        result = cmd(["-n", "-v", "{input}"])
        assert "-n" in result.cmd
        assert "-v" in result.cmd

    def test_returns_cmd_result_namedtuple(self):
        result = cmd(["{input}"])
        assert isinstance(result, CmdResult)

    def test_path_objects_accepted(self):
        result = build_cmd(Path("/usr/bin/solver"), ["{input}"], INPUT, OUTPUT)
        assert result.cmd[0] == "/usr/bin/solver"

    def test_duplicate_input_tokens_both_replaced(self):
        result = cmd(["{input}", "-o", "{input}"])
        assert result.cmd.count(str(INPUT)) == 2

    def test_input_and_output_embedded_in_same_arg(self):
        result = cmd(["{input}={output}"])
        assert f"{INPUT}={OUTPUT}" in result.cmd
        assert result.use_stdout_pipe is False

    def test_empty_options(self):
        result = cmd([])
        assert result.cmd == [EXE, str(INPUT)]
        assert result.use_stdin is False
        assert result.use_stdout_pipe is True

    def test_stdin_with_regular_flags_no_input_token(self):
        """< with no {input} token — stdin used, flags preserved, no path appended."""
        result = cmd(["<", "-n"])
        assert result.use_stdin is True
        assert "-n" in result.cmd
        assert str(INPUT) not in result.cmd

    def test_duplicate_stdin_tokens(self):
        result = cmd(["<", "<"])
        assert result.use_stdin is True
        assert "<" not in result.cmd

    def test_duplicate_stdout_tokens(self):
        result = cmd([">", ">"])
        assert result.use_stdout_pipe is True
        assert ">" not in result.cmd


# ---------------------------------------------------------------------------
# Parameter substitution
# ---------------------------------------------------------------------------

class TestParameterSubstitution:
    def test_parameter_token_replaced(self):
        result = build_cmd(EXE, ["-p", "{p}", "{input}"], INPUT, OUTPUT, parameters={"p": 5})
        assert "5" in result.cmd
        assert "{p}" not in " ".join(result.cmd)

    def test_multiple_parameters_replaced(self):
        result = build_cmd(EXE, ["-p", "{p}", "-q", "{q}", "{input}"],
                           INPUT, OUTPUT, parameters={"p": 5, "q": 2})
        assert "5" in result.cmd
        assert "2" in result.cmd

    def test_parameter_embedded_in_arg(self):
        result = build_cmd(EXE, ["--p={p}", "{input}"], INPUT, OUTPUT, parameters={"p": 7})
        assert "--p=7" in result.cmd

    def test_parameter_value_stringified(self):
        result = build_cmd(EXE, ["{n}", "{input}"], INPUT, OUTPUT, parameters={"n": 3.14})
        assert "3.14" in result.cmd

    def test_unresolved_placeholder_raises(self):
        with pytest.raises(ValueError, match="Unresolved placeholder"):
            build_cmd(EXE, ["-p", "{missing}", "{input}"], INPUT, OUTPUT, parameters={"p": 5})

    def test_no_parameters_with_no_placeholders_passes(self):
        result = build_cmd(EXE, ["-n", "{input}"], INPUT, OUTPUT, parameters={})
        assert result.cmd == [EXE, "-n", str(INPUT)]

    def test_none_parameters_treated_as_empty(self):
        result = build_cmd(EXE, ["-n", "{input}"], INPUT, OUTPUT, parameters=None)
        assert result.cmd == [EXE, "-n", str(INPUT)]

    def test_parameter_does_not_collide_with_input_token(self):
        result = build_cmd(EXE, ["{p}", "{input}"], INPUT, OUTPUT, parameters={"p": "X"})
        assert "X" in result.cmd
        assert str(INPUT) in result.cmd
