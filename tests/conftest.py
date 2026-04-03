import sys
import os
import stat
from pathlib import Path
from typing import Generator

import pytest

# make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from custom_types import ExecConfig, FormulatorConfig, FileConfig, TestCase, Result

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SIMPLE_CNF   = FIXTURES_DIR / "simple.cnf"
UNSAT_CNF    = FIXTURES_DIR / "unsat.cnf"
SIMPLE_LP    = FIXTURES_DIR / "simple.lp"
SMALL_G6     = FIXTURES_DIR / "small.g6"

# ---------------------------------------------------------------------------
# Dummy solver scripts
# ---------------------------------------------------------------------------

@pytest.fixture
def sat_solver(tmp_path: Path) -> Path:
    """A dummy solver script that prints 's SATISFIABLE' and exits 10."""
    p = tmp_path / "sat_solver.sh"
    p.write_text("#!/bin/bash\necho 's SATISFIABLE'\nexit 10\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


@pytest.fixture
def unsat_solver(tmp_path: Path) -> Path:
    """A dummy solver script that prints 's UNSATISFIABLE' and exits 20."""
    p = tmp_path / "unsat_solver.sh"
    p.write_text("#!/bin/bash\necho 's UNSATISFIABLE'\nexit 20\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


@pytest.fixture
def timeout_solver(tmp_path: Path) -> Path:
    """A dummy solver script that sleeps indefinitely to trigger timeout."""
    p = tmp_path / "timeout_solver.sh"
    p.write_text("#!/bin/bash\nsleep 60\nexit 10\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


@pytest.fixture
def error_solver(tmp_path: Path) -> Path:
    """A dummy solver script that exits with a non-zero error code."""
    p = tmp_path / "error_solver.sh"
    p.write_text("#!/bin/bash\nexit 1\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p

# ---------------------------------------------------------------------------
# Config dataclass fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sat_exec_config(sat_solver: Path) -> ExecConfig:
    """ExecConfig pointing to the dummy SAT solver."""
    return ExecConfig(
        name="dummy_sat",
        solver_type="SAT",
        cmd=str(sat_solver),
        options=["{input}"],
    )


@pytest.fixture
def simple_file_config() -> FileConfig:
    """FileConfig pointing to the small.g6 fixture — a raw problem file to be converted."""
    return FileConfig(name="small", path=str(SMALL_G6))


@pytest.fixture
def simple_test_case() -> TestCase:
    """TestCase pointing to the simple.cnf fixture."""
    return TestCase(name="simple", path=SIMPLE_CNF, tc_type="SAT")


@pytest.fixture
def unsat_test_case() -> TestCase:
    """TestCase pointing to the unsat.cnf fixture."""
    return TestCase(name="unsat", path=UNSAT_CNF, tc_type="SAT")
