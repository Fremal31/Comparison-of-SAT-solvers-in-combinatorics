import pytest
from pathlib import Path

from custom_types import FileConfig, FormulatorConfig, ConversionError
from converter import Converter
from metadata_registry import resolve_format_metadata
from conftest import SMALL_G6, FIXTURES_DIR

pytestmark = pytest.mark.integration

FORMULATOR_CMD = str(Path(__file__).parent.parent.parent / "formulator" / "formulator.py")


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
        assert len(result) == 1

    def test_output_file_created(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        converter.convert(make_problem(), output_path=output_path)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_output_is_valid_dimacs(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        converter.convert(make_problem(), output_path=output_path)
        content = output_path.read_text()
        assert "p cnf" in content

    def test_returns_testcase_with_correct_name(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        assert result[0].name == "small"

    def test_returns_testcase_with_correct_type(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        assert result[0].tc_type == "SAT"

    def test_testcase_links_back_to_problem(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        problem = make_problem()
        result = converter.convert(problem, output_path=output_path)
        assert result[0].problem_cfg == problem

    def test_generated_files_tracked(self, tmp_path: Path):
        converter = make_converter()
        output_path = tmp_path / "small.cnf"
        result = converter.convert(make_problem(), output_path=output_path)
        assert output_path in result[0].generated_files


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
        converter = Converter(converter_cfg=cfg, metadata=metadata)
        with pytest.raises(ConversionError, match="Unsupported output mode"):
            converter.convert(make_problem(), output_path=tmp_path / "out.cnf")

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
        assert result is not None
