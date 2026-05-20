import pytest
from pathlib import Path
from typing import List
import unittest.mock as mock

from custom_types import Result
from plots import generate_plots


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(solver: str = "kissat", problem: str = "test", status: str = "SAT",
                time: float = 1.0, conflicts: int = 42) -> Result:
    return Result(solver=solver, problem=problem, status=status, time=time,
                  metrics={"conflicts": conflicts})


def make_results() -> List[Result]:
    return [
        make_result(solver="kissat", problem="p1", status="SAT", time=1.0, conflicts=10),
        make_result(solver="cadical", problem="p1", status="UNSAT", time=2.0, conflicts=20),
    ]


# ---------------------------------------------------------------------------
# generate_plots
# ---------------------------------------------------------------------------

class TestGeneratePlots:
    def test_skips_if_no_results(self, tmp_path: Path, caplog):
        """Ensures the function returns early with a log message if results are empty."""
        import logging
        caplog.set_level(logging.INFO)
        generate_plots([], str(tmp_path))
        assert "No data to visualize" in caplog.text

    def test_directory_creation(self, tmp_path: Path):
        """Verifies that the output directory is created when plotting proceeds."""
        try:
            import pandas
            import matplotlib
        except ImportError:
            pytest.skip("Skipping directory creation test: Dependencies not installed.")

        out_dir = tmp_path / "new_plots_dir"
        results = [make_result()]

        generate_plots(results, str(out_dir))

        assert out_dir.exists()
        assert out_dir.is_dir()

    def test_handles_missing_dependencies(self, tmp_path: Path, caplog):
        """Mocks an ImportError to verify the try-except block handles missing libs."""
        with mock.patch('builtins.__import__', side_effect=ImportError(name="matplotlib")):
            generate_plots(make_results(), str(tmp_path))
            assert "skipped" in caplog.text
            assert "matplotlib" in caplog.text

    @pytest.mark.skipif(False, reason="Requires matplotlib and pandas installed")
    def test_generates_svg_files(self, tmp_path: Path):
        """
        Integration test: Verifies SVG files are actually written to disk.
        This will only pass if matplotlib and pandas are in the test env.
        """
        try:
            import matplotlib
            import pandas
        except ImportError:
            pytest.skip("Plotting dependencies not found in test environment.")

        results = [
            make_result(solver="s1", problem="p1", time=1.0),
            make_result(solver="s2", problem="p1", time=2.0)
        ]
        out_dir = tmp_path / "viz"

        generate_plots(results, str(out_dir), timeout=5.0)

        assert (out_dir / "time_p1.svg").exists()
        assert (out_dir / "status_counts.svg").exists()
        assert (out_dir / "cpu_time_distribution.svg").exists()

    def test_plot_logic_error_handling(self, tmp_path: Path, caplog):
        """Verifies that a failure in one plot doesn't crash the whole function."""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("Pandas required for this test.")

        # Create malformed result
        results = [make_result()]

        with mock.patch('matplotlib.pyplot.subplots', side_effect=Exception("Render error")):
            generate_plots(results, str(tmp_path))
            assert "Could not generate" in caplog.text
