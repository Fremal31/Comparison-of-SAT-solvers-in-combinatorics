import pytest
from pathlib import Path

from metadata_registry import resolve_format_metadata, FORMAT_REGISTRY
from format_types import FormatMetadata
from parser_strategy import SATparser, ILPparser, GenericParser


# ---------------------------------------------------------------------------
# Format registry contract — every entry in FORMAT_REGISTRY should pass these
# To test a new format type, add it to FORMAT_REGISTRY and it will be picked
# up automatically by TestFormatRegistryContract.
# ---------------------------------------------------------------------------

class TestFormatRegistryContract:
    """
    Validates that every entry in FORMAT_REGISTRY satisfies the minimum contract.
    New format types added to FORMAT_REGISTRY are automatically covered.
    """
    @pytest.fixture(params=[
        key for key in FORMAT_REGISTRY if key not in ("DEFAULT", "UNKNOWN")
    ])
    def entry(self, request) -> FormatMetadata:
        return FORMAT_REGISTRY[request.param]

    def test_format_type_is_non_empty_string(self, entry: FormatMetadata):
        assert isinstance(entry.format_type, str) and entry.format_type

    def test_suffix_starts_with_dot(self, entry: FormatMetadata):
        assert entry.suffix.startswith(".")

    def test_converter_class_is_set(self, entry: FormatMetadata):
        assert entry.converter_class is not None

    def test_parser_class_is_set(self, entry: FormatMetadata):
        assert entry.parser_class is not None

    def test_suffix_resolves_back_to_same_type(self, entry: FormatMetadata):
        """A file with this entry's suffix should resolve back to the same format type."""
        meta = resolve_format_metadata(path=Path(f"problem{entry.suffix}"))
        assert meta.format_type == entry.format_type


# ---------------------------------------------------------------------------
# Resolution by format_type string
# ---------------------------------------------------------------------------

class TestResolveByType:
    def test_sat_type(self):
        meta = resolve_format_metadata(format_type="SAT")
        assert meta.format_type == "SAT"
        assert meta.suffix == ".cnf"

    def test_ilp_type(self):
        meta = resolve_format_metadata(format_type="ILP")
        assert meta.format_type == "ILP"
        assert meta.suffix == ".lp"

    def test_smt_type(self):
        meta = resolve_format_metadata(format_type="SMT")
        assert meta.format_type == "SMT"
        assert meta.suffix == ".smt2"

    def test_case_insensitive(self):
        assert resolve_format_metadata(format_type="sat").format_type == "SAT"
        assert resolve_format_metadata(format_type="Ilp").format_type == "ILP"

    def test_unknown_type_returns_default(self):
        meta = resolve_format_metadata(format_type="UNKNOWN")
        assert meta.format_type == "UNKNOWN"

    def test_unrecognized_type_returns_default(self):
        meta = resolve_format_metadata(format_type="NONEXISTENT")
        assert meta.format_type == "UNKNOWN"


# ---------------------------------------------------------------------------
# Resolution by file path extension
# ---------------------------------------------------------------------------

class TestResolveByPath:
    def test_cnf_extension(self):
        meta = resolve_format_metadata(path=Path("problem.cnf"))
        assert meta.format_type == "SAT"

    def test_lp_extension(self):
        meta = resolve_format_metadata(path=Path("problem.lp"))
        assert meta.format_type == "ILP"

    def test_unrecognized_extension_returns_default(self):
        meta = resolve_format_metadata(path=Path("problem.txt"))
        assert meta.format_type == "UNKNOWN"

    def test_no_extension_returns_default(self):
        meta = resolve_format_metadata(path=Path("problem"))
        assert meta.format_type == "UNKNOWN"

    def test_extension_case_insensitive(self):
        meta = resolve_format_metadata(path=Path("problem.CNF"))
        assert meta.format_type == "SAT"


# ---------------------------------------------------------------------------
# Priority: format_type takes precedence over path
# ---------------------------------------------------------------------------

class TestResolvePriority:
    def test_type_wins_over_path(self):
        meta = resolve_format_metadata(format_type="ILP", path=Path("problem.cnf"))
        assert meta.format_type == "ILP"

    def test_falls_back_to_path_when_type_unrecognized(self):
        meta = resolve_format_metadata(format_type="NONEXISTENT", path=Path("problem.cnf"))
        assert meta.format_type == "SAT"

    def test_falls_back_to_path_when_type_and_suffix_unrecognized(self):
        meta = resolve_format_metadata(format_type="NONEXISTENT", path=Path("problem"))
        assert meta.format_type == "UNKNOWN"


    def test_no_args_returns_default(self):
        meta = resolve_format_metadata()
        assert meta.format_type == "UNKNOWN"


# ---------------------------------------------------------------------------
# Parser class assignment
# ---------------------------------------------------------------------------

class TestParserAssignment:
    def test_sat_has_sat_parser(self):
        meta = resolve_format_metadata(format_type="SAT")
        assert isinstance(meta.parser_class, SATparser)

    def test_ilp_has_ilp_parser(self):
        meta = resolve_format_metadata(format_type="ILP")
        assert isinstance(meta.parser_class, ILPparser)

    def test_default_has_generic_parser(self):
        meta = resolve_format_metadata(format_type="UNKNOWN")
        assert isinstance(meta.parser_class, GenericParser)
