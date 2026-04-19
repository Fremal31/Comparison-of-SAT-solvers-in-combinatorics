import stat
import pytest
from pathlib import Path

from conversion_phase import _worker_convert
from custom_types import FormulatorConfig, FileConfig
from format_types import ExperimentContext, ConversionTask
from metadata_registry import resolve_format_metadata
from conftest import SIMPLE_CNF


def make_conversion_task(formulator_cmd: str, tmp_path: Path, problem_path: Path = SIMPLE_CNF) -> ConversionTask:
    cfg = FormulatorConfig(
        name="test_formulator",
        formulator_type="SAT",
        cmd=formulator_cmd,
        enabled=True,
        options=["{input}"],
        output_mode="stdout",
    )
    problem = FileConfig(name="test_problem", path=str(problem_path))
    fmt = resolve_format_metadata("SAT")
    ctx = ExperimentContext(base_path=tmp_path, log_dir=tmp_path, format_info=fmt)
    return ConversionTask(problem=problem, config=cfg, work_dir=ctx, timeout=5.0)


# ---------------------------------------------------------------------------
# _worker_convert
# ---------------------------------------------------------------------------

class TestWorkerConvert:
    def test_failing_formulator_returns_empty_list(self, tmp_path: Path):
        p = tmp_path / "bad_formulator.sh"
        p.write_text("#!/bin/bash\nexit 1\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        task = make_conversion_task(str(p), tmp_path)
        test_cases, raw = _worker_convert(task)

        assert test_cases == []
        assert raw is None

    def test_timeout_formulator_returns_empty_list(self, tmp_path: Path):
        p = tmp_path / "slow_formulator.sh"
        p.write_text("#!/bin/bash\nsleep 10\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        cfg = FormulatorConfig(
            name="slow_formulator", formulator_type="SAT",
            cmd=str(p), enabled=True, options=["{input}"], output_mode="stdout",
        )
        problem = FileConfig(name="test_problem", path=str(SIMPLE_CNF))
        fmt = resolve_format_metadata("SAT")
        ctx = ExperimentContext(base_path=tmp_path, log_dir=tmp_path, format_info=fmt)
        task = ConversionTask(problem=problem, config=cfg, work_dir=ctx, timeout=0.1)

        test_cases, raw = _worker_convert(task)

        assert test_cases == []
        assert raw is None

    def test_successful_formulator_returns_test_cases(self, tmp_path: Path):
        p = tmp_path / "good_formulator.sh"
        p.write_text("#!/bin/bash\necho 'p cnf 1 1\n1 0'\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

        task = make_conversion_task(str(p), tmp_path)
        test_cases, raw = _worker_convert(task)

        assert len(test_cases) >= 1
        assert raw is not None
