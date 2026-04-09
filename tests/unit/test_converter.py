import pytest
from pathlib import Path
from unittest.mock import MagicMock

from converter import Converter
from generic_executor import GenericExecutor
from custom_types import FileConfig, FormulatorConfig, RawResult, ConversionError
from metadata_registry import resolve_format_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(output_mode: str = "stdout", options: list = None) -> FormulatorConfig:
    return FormulatorConfig(
        name="test_formulator",
        formulator_type="SAT",
        cmd="echo",
        enabled=True,
        options=options or ["{input}"],
        output_mode=output_mode,
    )


def _make_converter(output_mode: str = "stdout", executor: GenericExecutor = None,
                    options: list = None) -> Converter:
    cfg = _make_cfg(output_mode=output_mode, options=options)
    metadata = resolve_format_metadata(format_type="SAT")
    return Converter(converter_cfg=cfg, metadata=metadata, executor=executor)


def _make_problem(tmp_path: Path, name: str = "test") -> FileConfig:
    p = tmp_path / f"{name}.g6"
    p.write_text("some graph data")
    return FileConfig(name=name, path=str(p))


def _make_raw(stdout: str = "", exit_code: int = 0) -> RawResult:
    return RawResult(stdout=stdout, exit_code=exit_code, time=0.1, memory_peak_mb=1.0)


def _make_raw_failed(error: str = "boom") -> RawResult:
    return RawResult(launch_failed=True, error=error)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConverterInit:
    def test_valid_mode_accepted(self):
        _make_converter(output_mode="stdout")

    def test_stdout_multi_mode_accepted(self):
        _make_converter(output_mode="stdout_multi")

    def test_directory_mode_accepted(self):
        _make_converter(output_mode="directory")

    def test_unsupported_mode_raises(self):
        with pytest.raises(ConversionError, match="Unsupported output mode"):
            _make_converter(output_mode="invalid")

    def test_executor_injected(self):
        executor = MagicMock(spec=GenericExecutor)
        converter = _make_converter(executor=executor)
        assert converter._executor is executor


# ---------------------------------------------------------------------------
# stdout mode
# ---------------------------------------------------------------------------

class TestHandleStdout:
    def test_single_testcase_returned(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="p cnf 1 1\n1 0\n")
        converter = _make_converter(executor=executor)
        problem = _make_problem(tmp_path)
        out = tmp_path / "test.cnf"

        test_cases, raw = converter.convert(problem, out)

        assert len(test_cases) == 1
        assert test_cases[0].name == "test"
        assert test_cases[0].tc_type == "SAT"
        assert raw.time == 0.1

    def test_output_file_created(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="p cnf 1 1\n1 0\n")
        converter = _make_converter(executor=executor)
        out = tmp_path / "test.cnf"

        converter.convert(_make_problem(tmp_path), out)

        assert out.exists()
        assert "p cnf" in out.read_text()

    def test_launch_failure_raises(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw_failed()
        converter = _make_converter(executor=executor)

        with pytest.raises(ConversionError, match="failed to launch"):
            converter.convert(_make_problem(tmp_path), tmp_path / "out.cnf")

    def test_nonzero_exit_raises(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(exit_code=1)
        converter = _make_converter(executor=executor)

        with pytest.raises(ConversionError, match="failed"):
            converter.convert(_make_problem(tmp_path), tmp_path / "out.cnf")

    def test_testcase_links_to_problem(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="p cnf 1 1\n1 0\n")
        converter = _make_converter(executor=executor)
        problem = _make_problem(tmp_path)
        out = tmp_path / "test.cnf"

        test_cases, _ = converter.convert(problem, out)

        assert test_cases[0].problem_cfg is problem
        assert test_cases[0].formulator_cfg is not None

    def test_generated_files_tracked(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="p cnf 1 1\n1 0\n")
        converter = _make_converter(executor=executor)
        out = tmp_path / "test.cnf"

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert out in test_cases[0].generated_files


# ---------------------------------------------------------------------------
# stdout_multi mode
# ---------------------------------------------------------------------------

class TestHandleStdoutMulti:
    def test_splits_into_multiple_testcases(self, tmp_path: Path):
        two_formulas = "p cnf 1 1\n1 0\n\np cnf 2 1\n1 2 0\n"
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout=two_formulas)
        converter = _make_converter(output_mode="stdout_multi", executor=executor)
        out = tmp_path / "test.cnf"

        test_cases, raw = converter.convert(_make_problem(tmp_path), out)

        assert len(test_cases) == 2
        assert raw.time == 0.1

    def test_files_named_with_index(self, tmp_path: Path):
        two_formulas = "p cnf 1 1\n1 0\n\np cnf 2 1\n1 2 0\n"
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout=two_formulas)
        converter = _make_converter(output_mode="stdout_multi", executor=executor)
        out = tmp_path / "test.cnf"

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert test_cases[0].name == "test_0"
        assert test_cases[1].name == "test_1"
        assert Path(test_cases[0].path).name == "test_0.cnf"
        assert Path(test_cases[1].path).name == "test_1.cnf"

    def test_each_file_has_correct_content(self, tmp_path: Path):
        formula_a = "p cnf 1 1\n1 0"
        formula_b = "p cnf 2 1\n1 2 0"
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout=f"{formula_a}\n\n{formula_b}\n")
        converter = _make_converter(output_mode="stdout_multi", executor=executor)
        out = tmp_path / "test.cnf"

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert Path(test_cases[0].path).read_text() == formula_a
        assert Path(test_cases[1].path).read_text() == formula_b

    def test_single_formula_returns_one_testcase(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="p cnf 1 1\n1 0\n")
        converter = _make_converter(output_mode="stdout_multi", executor=executor)
        out = tmp_path / "test.cnf"

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert len(test_cases) == 1

    def test_empty_output_raises(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="")
        converter = _make_converter(output_mode="stdout_multi", executor=executor)

        with pytest.raises(ConversionError, match="empty output"):
            converter.convert(_make_problem(tmp_path), tmp_path / "out.cnf")

    def test_whitespace_only_output_raises(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout="   \n\n  \n")
        converter = _make_converter(output_mode="stdout_multi", executor=executor)

        with pytest.raises(ConversionError, match="empty output"):
            converter.convert(_make_problem(tmp_path), tmp_path / "out.cnf")

    def test_testcases_link_to_problem(self, tmp_path: Path):
        two_formulas = "p cnf 1 1\n1 0\n\np cnf 2 1\n1 2 0\n"
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw(stdout=two_formulas)
        converter = _make_converter(output_mode="stdout_multi", executor=executor)
        problem = _make_problem(tmp_path)
        out = tmp_path / "test.cnf"

        test_cases, _ = converter.convert(problem, out)

        for tc in test_cases:
            assert tc.problem_cfg is problem
            assert tc.tc_type == "SAT"

    def test_reads_from_file_when_piped(self, tmp_path: Path):
        two_formulas = "p cnf 1 1\n1 0\n\np cnf 2 1\n1 2 0\n"
        executor = MagicMock(spec=GenericExecutor)
        # Simulate stdout piped to file: stdout is empty, file exists
        raw = _make_raw(stdout="")
        executor.execute.return_value = raw
        converter = _make_converter(output_mode="stdout_multi", executor=executor, options=[">", "{input}"])

        # Pre-create the tmp file as if executor wrote to it
        out = tmp_path / "test.cnf"
        tmp_file = out.with_suffix(out.suffix + ".tmp")
        tmp_file.write_text(two_formulas)

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert len(test_cases) == 2


# ---------------------------------------------------------------------------
# directory mode
# ---------------------------------------------------------------------------

class TestHandleDirectory:
    def test_collects_files_from_directory(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()
        converter = _make_converter(output_mode="directory", executor=executor)
        problem = _make_problem(tmp_path)
        out = tmp_path / "work" / "test.cnf"
        out.parent.mkdir(parents=True)

        # Simulate formulator writing files to the directory
        (out.parent / "graph_0.cnf").write_text("p cnf 1 1\n1 0\n")
        (out.parent / "graph_1.cnf").write_text("p cnf 2 1\n1 2 0\n")

        test_cases, raw = converter.convert(problem, out)

        assert len(test_cases) == 2
        assert raw.time == 0.1

    def test_files_sorted_by_name(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()
        converter = _make_converter(output_mode="directory", executor=executor)
        out = tmp_path / "work" / "test.cnf"
        out.parent.mkdir(parents=True)

        (out.parent / "b.cnf").write_text("formula b")
        (out.parent / "a.cnf").write_text("formula a")

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert Path(test_cases[0].path).name == "a.cnf"
        assert Path(test_cases[1].path).name == "b.cnf"

    def test_ignores_wrong_suffix(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()
        converter = _make_converter(output_mode="directory", executor=executor)
        out = tmp_path / "work" / "test.cnf"
        out.parent.mkdir(parents=True)

        (out.parent / "good.cnf").write_text("p cnf 1 1\n1 0\n")
        (out.parent / "bad.txt").write_text("not a formula")
        (out.parent / "bad.lp").write_text("not a formula")

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert len(test_cases) == 1
        assert Path(test_cases[0].path).name == "good.cnf"

    def test_no_files_raises(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()
        converter = _make_converter(output_mode="directory", executor=executor)
        out = tmp_path / "work" / "test.cnf"
        out.parent.mkdir(parents=True)

        with pytest.raises(ConversionError, match="produced no"):
            converter.convert(_make_problem(tmp_path), out)

    def test_testcases_indexed(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()
        converter = _make_converter(output_mode="directory", executor=executor)
        out = tmp_path / "work" / "test.cnf"
        out.parent.mkdir(parents=True)

        (out.parent / "a.cnf").write_text("formula")
        (out.parent / "b.cnf").write_text("formula")

        test_cases, _ = converter.convert(_make_problem(tmp_path), out)

        assert test_cases[0].name == "test_0"
        assert test_cases[1].name == "test_1"

    def test_testcases_link_to_problem(self, tmp_path: Path):
        executor = MagicMock(spec=GenericExecutor)
        executor.execute.return_value = _make_raw()
        converter = _make_converter(output_mode="directory", executor=executor)
        problem = _make_problem(tmp_path)
        out = tmp_path / "work" / "test.cnf"
        out.parent.mkdir(parents=True)

        (out.parent / "a.cnf").write_text("formula")

        test_cases, _ = converter.convert(problem, out)

        assert test_cases[0].problem_cfg is problem
        assert test_cases[0].tc_type == "SAT"


# ---------------------------------------------------------------------------
# _split_formulas
# ---------------------------------------------------------------------------

class TestSplitFormulas:
    def test_two_formulas(self):
        result = Converter._split_formulas("a\n\nb")
        assert result == ["a", "b"]

    def test_single_formula(self):
        result = Converter._split_formulas("a\nb\nc")
        assert result == ["a\nb\nc"]

    def test_trailing_blank_lines(self):
        result = Converter._split_formulas("a\n\nb\n\n")
        assert result == ["a", "b"]

    def test_leading_blank_lines(self):
        result = Converter._split_formulas("\n\na\n\nb")
        assert result == ["a", "b"]

    def test_empty_string(self):
        result = Converter._split_formulas("")
        assert result == []

    def test_whitespace_only(self):
        result = Converter._split_formulas("  \n\n  \n")
        assert result == []

    def test_multiple_blank_lines_between(self):
        result = Converter._split_formulas("a\n\n\n\nb")
        assert result == ["a", "b"]
