import pytest
from pathlib import Path

from custom_types import FileConfig, FormulatorConfig, ConversionError
from converter import Converter
from metadata_registry import resolve_format_metadata
from conftest import SMALL_G6

pytestmark = pytest.mark.integration

FORMULATOR_CMD = str(Path(__file__).parent.parent.parent / "formulator" / "hamilton_SAT.py")


def make_converter(options: list = None) -> Converter:
    cfg = FormulatorConfig(
        name="test_formulator",
        formulator_type="SAT",
        cmd=FORMULATOR_CMD,
        enabled=True,
        options=options or ["{input}"],
        output_mode="stdout",
    )
    metadata = resolve_format_metadata(format_type="SAT")
    return Converter(converter_cfg=cfg, metadata=metadata)


def make_problem(path: Path = None) -> FileConfig:
    return FileConfig(name="small", path=str(path or SMALL_G6))


# ---------------------------------------------------------------------------
# Basic conversion
# ---------------------------------------------------------------------------

class TestConverterBasic:
    def test_converts_g6_to_cnf(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        assert result is not None
        test_cases, raw_result = result
        
        assert test_cases is not None
        assert len(test_cases) == 1

        assert raw_result is not None

    def test_output_file_created(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        converter.convert(make_problem(), output_path=output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_returns_testcase_with_correct_name(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        test_cases, raw_result = result
        
        assert test_cases[0].name == "small"

    def test_returns_testcase_with_correct_type(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        test_cases, raw_result = result
        
        assert test_cases[0].tc_type == "SAT"

    def test_testcase_links_back_to_problem(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        problem = make_problem()
        result = converter.convert(problem, output_path=output_path)
        test_cases, raw_result = result
        
        assert test_cases[0].problem_cfg == problem

    # def test_generated_files_tracked(self, tmp_path: Path):
    #     converter = make_converter()
    #     output_path = tmp_path / "small.cnf"
    #     result = converter.convert(make_problem(), output_path=output_path)
    #     test_cases, raw_result = result
        
    #     assert output_path in test_cases[0].generated_files

    def test_tmp_file_cleaned_up_after_conversion(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        converter.convert(make_problem(), output_path=output_path)
        assert not (tmp_path / "small.cnf.tmp").exists()

    def test_output_file_overwritten_if_exists(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        output_path.write_text("old content")
        converter.convert(make_problem(), output_path=output_path)
        assert "p cnf" in output_path.read_text()

    def test_testcase_path_matches_output_path(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        test_cases, raw_result = result
        assert test_cases[0].path == output_path

    def test_testcase_formulator_cfg_set(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        test_cases, raw_result = result

        assert test_cases[0].formulator_cfg is not None
        assert test_cases[0].formulator_cfg.name == "test_formulator"

    def test_dimacs_clauses_terminated_with_zero(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        converter.convert(make_problem(), output_path=output_path)
        clause_lines = [
            l for l in output_path.read_text().splitlines()
            if l and not l.startswith("c") and not l.startswith("p")
        ]
        assert all(l.strip().endswith("0") for l in clause_lines)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestConverterErrors:
    def test_unsupported_output_mode_raises(self, tmp_path: Path):
        cfg = FormulatorConfig(
            name="bad_formulator",
            formulator_type="SAT",
            cmd=FORMULATOR_CMD,
            enabled=True,
            options=["{input}"],
            output_mode="unsupported_mode",
        )
        metadata = resolve_format_metadata(format_type="SAT")
        with pytest.raises(ConversionError, match="Unsupported output mode"):
            Converter(converter_cfg=cfg, metadata=metadata)

    def test_missing_problem_path_raises(self, tmp_path: Path):
        converter = make_converter()
        problem = FileConfig(name="missing", path=str(tmp_path / "nonexistent.g6"))
        with pytest.raises(ConversionError):
            converter.convert(problem, output_path=tmp_path / "out.cnf")

    def test_stdin_mode_works(self, tmp_path: Path):
        """Formulator should also work when fed via stdin."""
        converter = make_converter(options=["-", "<"])
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0
        assert result is not None

    def test_problem_with_no_name_uses_output_stem(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "derived_name.cnf"
        problem = FileConfig(name="", path=str(SMALL_G6))
        result = converter.convert(problem, output_path=output_path)
        test_cases, raw_result = result

        assert test_cases[0].name == "derived_name"
