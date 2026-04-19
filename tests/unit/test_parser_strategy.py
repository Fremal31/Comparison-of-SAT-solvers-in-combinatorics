import pytest
from pathlib import Path

from custom_types import Result, RunnerError
from parser_strategy import SATparser, ILPparser, HiGHSParser, GenericParser, get_parser, ResultParser, _try_to_convert_to_numeric

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(stdout: str = "") -> Result:
    return Result(solver="test", problem="test", stdout=stdout)


# ---------------------------------------------------------------------------
# _try_to_convert_to_numeric
# ---------------------------------------------------------------------------

class TestTryToConvertToNumeric:
    def test_integer(self):
        assert _try_to_convert_to_numeric("42") == 42
        assert isinstance(_try_to_convert_to_numeric("42"), int)

    def test_negative_integer(self):
        assert _try_to_convert_to_numeric("-7") == -7

    def test_zero(self):
        assert _try_to_convert_to_numeric("0") == 0
        assert isinstance(_try_to_convert_to_numeric("0"), int)

    def test_float(self):
        assert _try_to_convert_to_numeric("3.14") == 3.14
        assert isinstance(_try_to_convert_to_numeric("3.14"), float)

    def test_negative_float(self):
        assert _try_to_convert_to_numeric("-3.14") == -3.14

    def test_string_passthrough(self):
        assert _try_to_convert_to_numeric("hello") == "hello"
        assert isinstance(_try_to_convert_to_numeric("hello"), str)

    def test_empty_string(self):
        assert _try_to_convert_to_numeric("") == ""

    def test_integer_preferred_over_float(self):
        """'42' should be int, not float."""
        assert isinstance(_try_to_convert_to_numeric("42"), int)


# ---------------------------------------------------------------------------
# METRIC_PATTERNS validation
# ---------------------------------------------------------------------------

class TestMetricPatternsValidation:
    def test_string_instead_of_list_raises(self):
        with pytest.raises(RunnerError, match="List\\[str\\]"):
            class BadParser(GenericParser):
                STATUS_MAP = {"SAT": "SAT"}
                METRIC_PATTERNS = {"conflicts": r"conflicts:\s+(\d+)"}  # str, not List[str]


# ---------------------------------------------------------------------------
# Parser contract — any ResultParser subclass should pass these tests
# Inherit from ParserContractBase and set parser, sat_output, unsat_output
# ---------------------------------------------------------------------------

class ParserContractBase:
    """
    Base contract test for ResultParser implementations.

    To test a new parser, subclass this and set:
        parser      — an instance of the parser to test
        sat_output  — solver output string that should produce SAT status
        unsat_output — solver output string that should produce UNSAT status
    """
    parser: ResultParser
    sat_output: str
    unsat_output: str

    def test_returns_result(self):
        result = self.parser.parse(make_result(self.sat_output))
        assert isinstance(result, Result)

    def test_sat_status(self):
        result = self.parser.parse(make_result(self.sat_output))
        assert result.status == "SAT"

    def test_unsat_status(self):
        result = self.parser.parse(make_result(self.unsat_output))
        assert result.status == "UNSAT"

    def test_stdout_cleared_after_parse(self):
        result = self.parser.parse(make_result(self.sat_output))
        assert result.stdout == "Parsed and cleared."

    def test_does_not_crash_on_empty_stdout(self):
        result = self.parser.parse(make_result(""))
        assert isinstance(result, Result)

    def test_does_not_crash_on_none_output_path(self):
        result = self.parser.parse(make_result(self.sat_output), output_path=None)
        assert isinstance(result, Result)

    def test_does_not_crash_on_missing_output_file(self, tmp_path: Path):
        result = self.parser.parse(make_result(""), output_path=tmp_path / "missing.out")
        assert isinstance(result, Result)


class TestSATparserContract(ParserContractBase):
    parser = SATparser()
    sat_output = "s SATISFIABLE"
    unsat_output = "s UNSATISFIABLE"


class TestILPparserContract(ParserContractBase):
    parser = ILPparser()
    sat_output = "feasible"
    unsat_output = "unfeasible"


class TestHiGHSParserContract(ParserContractBase):
    parser = HiGHSParser()
    sat_output = "Optimal"
    unsat_output = "Infeasible"


# ---------------------------------------------------------------------------
# SATparser
# ---------------------------------------------------------------------------

class TestSATparser:
    parser = SATparser()

    def test_unknown_status(self):
        result = self.parser.parse(make_result("s UNKNOWN"))
        assert result.status == "UNKNOWN"

    def test_no_status_remains_unknown(self):
        result = self.parser.parse(make_result("some random output"))
        assert result.status == "UNKNOWN"

    def test_empty_stdout_remains_unknown(self):
        result = self.parser.parse(make_result(""))
        assert result.status == "UNKNOWN"

    def test_empty_stdout_no_file_remains_unknown(self):
        result = self.parser.parse(make_result(""), output_path=None)
        assert result.status == "UNKNOWN"

    def test_nonexistent_output_file_does_not_crash(self, tmp_path: Path):
        result = self.parser.parse(make_result(""), output_path=tmp_path / "missing.out")
        assert result.status == "UNKNOWN"

    def test_empty_output_file_does_not_crash(self, tmp_path: Path):
        out = tmp_path / "empty.out"
        out.write_text("")
        result = self.parser.parse(make_result(""), output_path=out)
        assert result.status == "UNKNOWN"

    def test_conflicts_kissat_style(self):
        result = self.parser.parse(make_result("s SATISFIABLE\nc conflicts: 42"))
        assert result.metrics.get("conflicts") == 42

    def test_metric_value_zero(self):
        result = self.parser.parse(make_result("s SATISFIABLE\nc conflicts: 0"))
        assert result.metrics.get("conflicts") == 0

    def test_first_status_wins(self):
        result = self.parser.parse(make_result("s SATISFIABLE\ns UNSATISFIABLE"))
        assert result.status == "SAT"

    def test_conflicts_glucose_style(self):
        result = self.parser.parse(make_result("s SATISFIABLE\nc nb conflicts : 99"))
        assert result.metrics.get("conflicts") == 99

    def test_restarts_parsed(self):
        result = self.parser.parse(make_result("s SATISFIABLE\nc restarts: 5"))
        assert result.metrics.get("restarts") == 5

    def test_decisions_parsed(self):
        result = self.parser.parse(make_result("s SATISFIABLE\nc decisions: 100"))
        assert result.metrics.get("decisions") == 100

    def test_propagations_parsed(self):
        result = self.parser.parse(make_result("s SATISFIABLE\nc propagations: 200"))
        assert result.metrics.get("propagations") == 200

    def test_fallback_to_output_file(self, tmp_path: Path):
        out = tmp_path / "solver.out"
        out.write_text("s SATISFIABLE\nc conflicts: 7")
        result = self.parser.parse(make_result(""), output_path=out)
        assert result.status == "SAT"
        assert result.metrics.get("conflicts") == 7

    def test_metrics_come_from_file_when_fallback_triggered(self, tmp_path: Path):
        """When falling back to file, metrics should also come from the file."""
        out = tmp_path / "solver.out"
        out.write_text("s SATISFIABLE\nc conflicts: 99")
        result = self.parser.parse(make_result(""), output_path=out)
        assert result.metrics.get("conflicts") == 99

    def test_no_fallback_if_status_found_in_stdout(self, tmp_path: Path):
        out = tmp_path / "solver.out"
        out.write_text("s UNSATISFIABLE")
        result = self.parser.parse(make_result("s SATISFIABLE"), output_path=out)
        assert result.status == "SAT"


# ---------------------------------------------------------------------------
# ILPparser
# ---------------------------------------------------------------------------

class TestILPparser:
    parser = ILPparser()

    def test_nodes_parsed(self):
        result = self.parser.parse(make_result("feasible\nc nodes: 12"))
        assert result.metrics.get("nodes") == 12

    def test_iterations_parsed(self):
        result = self.parser.parse(make_result("feasible\nc iterations: 34"))
        assert result.metrics.get("iterations") == 34

    def test_objective_parsed(self):
        result = self.parser.parse(make_result("feasible\nc objective: 3.14"))
        assert result.metrics.get("objective") == 3.14

    def test_negative_objective_parsed(self):
        result = self.parser.parse(make_result("feasible\nc objective: -3.14"))
        assert result.metrics.get("objective") == -3.14

    def test_no_status_remains_unknown(self):
        result = self.parser.parse(make_result("some random output"))
        assert result.status == "UNKNOWN"


# ---------------------------------------------------------------------------
# HiGHSParser
# ---------------------------------------------------------------------------

class TestHiGHSParser:
    parser = HiGHSParser()

    def test_timeout_status(self):
        result = self.parser.parse(make_result("Timeout"))
        assert result.status == "TIMEOUT"

    def test_nodes_parsed(self):
        result = self.parser.parse(make_result("Optimal\nNodes         5"))
        assert result.metrics.get("nodes") == 5

    def test_lp_iterations_parsed(self):
        result = self.parser.parse(make_result("Optimal\nLP iterations  100"))
        assert result.metrics.get("iterations") == 100

    def test_objective_parsed(self):
        result = self.parser.parse(make_result("Optimal\nPrimal bound   2.5"))
        assert result.metrics.get("objective") == 2.5


# ---------------------------------------------------------------------------
# get_parser registry
# ---------------------------------------------------------------------------

class TestGetParser:
    def test_sat_key(self):
        assert isinstance(get_parser("SAT"), SATparser)

    def test_ilp_key(self):
        assert isinstance(get_parser("ILP"), ILPparser)

    def test_highs_key(self):
        assert isinstance(get_parser("Highs"), HiGHSParser)

    def test_case_insensitive(self):
        assert isinstance(get_parser("sat"), SATparser)
        assert isinstance(get_parser("kissat"), SATparser)

    def test_unknown_key_returns_generic(self):
        assert isinstance(get_parser("nonexistent"), GenericParser)

    def test_solver_specific_keys(self):
        assert isinstance(get_parser("Kissat"), SATparser)
        assert isinstance(get_parser("Cadical"), SATparser)
        assert isinstance(get_parser("Glucose"), SATparser)
