from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from custom_types import Result

import re
from abc import ABC, abstractmethod
from pathlib import Path

from custom_types import RunnerError, Status

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PARSE_BYTES = 65536  # 64 KB — more than enough for any solver's summary section


def _head_str(text: str) -> str:
    """Returns the first _PARSE_BYTES characters of *text*, ending at a line boundary."""
    if len(text) <= _PARSE_BYTES:
        return text
    nl = text.rfind('\n', 0, _PARSE_BYTES)
    return text[:nl] if nl != -1 else text[:_PARSE_BYTES]

def _tail_str(text: str) -> str:
    """Returns the last _PARSE_BYTES characters of *text*, starting at a line boundary."""
    if len(text) <= _PARSE_BYTES:
        return text
    nl = text.find('\n', len(text) - _PARSE_BYTES)
    return text[nl + 1:] if nl != -1 else text[-_PARSE_BYTES:]

def _read_head(path: Path) -> str:
    """Reads only the first _PARSE_BYTES of a file without loading it fully into memory."""
    with open(path, 'rb') as f:
        raw = f.read(_PARSE_BYTES)
    return raw.decode('utf-8', errors='replace')

def _read_tail(path: Path) -> str:
    """Reads only the last _PARSE_BYTES of a file without loading it fully into memory."""
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - _PARSE_BYTES))
        raw = f.read()
    text = raw.decode('utf-8', errors='replace')
    if size > _PARSE_BYTES:
        nl = text.find('\n')
        return text[nl + 1:] if nl != -1 else text
    return text

def _try_to_convert_to_numeric(value: str) -> int | float | str:
    """Tries to convert *value* to int, then float. Returns the original string if neither works."""
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class ResultParser(ABC):
    """
    Abstract base class for solver output parsers (Strategy pattern).

    Subclasses implement *parse* to extract status and metrics from solver
    output and populate the Result object.
    """
    @abstractmethod
    def parse(self, result: Result, output_path: Path | None = None,
              enabled_metrics: set[str] | None = None) -> Result:
        """Parses solver output from *result.stdout* or *output_path* and returns
        the updated Result with status and metrics populated.

        If *enabled_metrics* is provided, only metric keys in the set are extracted;
        keys outside it are skipped (saves regex time). None means extract all."""


class GenericSolverOutputParser(ResultParser):
    """
    Configurable parser driven by *STATUS_MAP* and *METRIC_PATTERNS* class attributes.

    Scans stdout for status keywords first; if status remains UNKNOWN and
    *output_path* is provided, falls back to reading the output file for status.
    Metrics are extracted from both sources — stdout first, then the output file
    for any metrics not yet found.

    If a solver writes its output to a file rather than stdout, configure it
    with '{output}' or '>' in options so the file becomes the primary source.

    NOTE: STATUS_MAP keys are matched as substrings in order - if one key is a
    substring of another, the longer, more specific one should come first to
    avoid false matches.

    Subclass and override *STATUS_MAP* and *METRIC_PATTERNS* to support a new solver.
    """
    STATUS_MAP: dict[str, Status] = {}
    METRIC_PATTERNS: dict[str, list[str]] = {}
    _compiled_patterns: dict[str, list[re.Pattern[str]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for _key, patterns in cls.METRIC_PATTERNS.items():
            if isinstance(patterns, str):
                raise RunnerError("Patterns in METRIC_PATTERN should be List[str] instead of str")
        cls._compiled_patterns = {
            key: [re.compile(p, re.MULTILINE | re.IGNORECASE) for p in patterns]
            for key, patterns in cls.METRIC_PATTERNS.items()
        }

    @staticmethod
    def _extract_last_metric(content: str, compiled: re.Pattern[str]) -> str | None:
        matches = compiled.findall(content)
        if not matches:
            return None
        last = matches[-1]
        return last if isinstance(last, str) else last[0]

    def _extract_status(self, content: str) -> Status | None:
        """Returns the first matching status from *content*, or None."""
        for keyword, status_name in self.STATUS_MAP.items():
            if keyword in content:
                return status_name
        return None

    def _extract_metrics(self, content: str, metrics: dict[str, Any],
                         enabled_metrics: set[str] | None = None) -> None:
        """Extracts metrics from *content* into *metrics* dict. Only sets a
        metric if it hasn't been found yet (first source wins). If *enabled_metrics*
        is provided, keys outside the set are skipped — neither matched nor stored."""
        for key, compiled_list in self._compiled_patterns.items():
            if enabled_metrics is not None and key not in enabled_metrics:
                continue
            if key in metrics:
                continue
            for compiled in compiled_list:
                raw: str | None = self._extract_last_metric(content=content, compiled=compiled)
                if raw:
                    metrics[key] = _try_to_convert_to_numeric(raw)
                    break

    def parse(self, result: Result, output_path: Path | None = None,
              enabled_metrics: set[str] | None = None) -> Result:
        stdout_content = _head_str(result.stdout) + _tail_str(result.stdout)
        file_content = None
        if output_path and output_path.exists():
            file_content = _read_head(output_path) + _read_tail(output_path)

        status = self._extract_status(stdout_content)
        if status is None and file_content is not None:
            status = self._extract_status(file_content)
        if status is not None:
            result.status = status

        self._extract_metrics(stdout_content, result.metrics, enabled_metrics)
        if file_content is not None:
            self._extract_metrics(file_content, result.metrics, enabled_metrics)

        result.stdout = "Parsed and cleared."
        return result


class GenericBreaker(GenericSolverOutputParser):
    """Parser for symmetry breakers — expects no status or metrics in output."""


# ---------------------------------------------------------------------------
# SAT parsers
# ---------------------------------------------------------------------------

class SATparser(GenericSolverOutputParser):
    """Parser for DIMACS-compatible SAT solvers using the standard 's SATISFIABLE' output format.
    Covers Glucose, CaDiCaL, Kissat, Minisat and similar solvers."""
    STATUS_MAP = {
        "s SATISFIABLE": Status.SAT,
        "s UNSATISFIABLE": Status.UNSAT,
        "s UNKNOWN": Status.UNKNOWN
    }
    METRIC_PATTERNS = {
        "conflicts": [
            r"^\s*c?\s*nb\s+conflicts\s*:\s*(\d+)",  # Glucose (handles 'c' or no 'c')
            r"^\s*c?\s*conflicts\s*:\s*(\d+)",       # Cadical / Kissat / Minisat
            r"^conflicts\s+(\d+)",                   # Some older solvers
            r"-\s+conflicts\s+:\s+(\d+)"             # Tabular outputs
        ],
        "restarts": [
            r"^\s*c?\s*nb\s+restarts\s*:\s*(\d+)",   # Glucose
            r"^\s*c?\s*restarts\s*:\s*(\d+)",        # Cadical / Kissat
            r"^restarts\s+(\d+)"                     # Minisat
        ],
        "decisions": [
            r"^\s*c?\s*decisions\s*:\s*(\d+)",       # Standard
            r"^decisions\s+(\d+)"                    # Minisat
        ],
        "propagations": [
            r"^\s*c?\s*propagations\s*:\s*(\d+)",    # Standard
            r"^propagations\s+(\d+)"                 # Minisat
        ],
        "clauses": [
            r"^\s*c?\s*clauses\s*:\s*(\d+)",         # Standard
            r"^num\s+clauses\s*:\s*(\d+)"            # Alternative
        ],
        "learned": [
            r"^\s*c?\s*learned\s*:\s*(\d+)",         # Standard
            r"^\s*c?\s*nb\s+learned\s*:\s*(\d+)"     # Glucose specific
        ]
    }


# ---------------------------------------------------------------------------
# ILP parsers
# ---------------------------------------------------------------------------

class ILPparser(GenericSolverOutputParser):
    """Parser for generic ILP solvers."""
    STATUS_MAP = {
        "optimal solution found": Status.SAT,
        "unfeasible": Status.UNSAT,
        "infeasible": Status.UNSAT,
        "not feasible": Status.UNSAT,
        "feasible": Status.SAT,  # must come after unfeasible/infeasible — first match wins
        "s UNKNOWN": Status.UNKNOWN
    }
    METRIC_PATTERNS = {
        "nodes": [r"c nodes:\s+(\d+)"],
        "iterations": [r"c iterations:\s+(\d+)"],
        "objective": [r"c objective:\s+([\d\.\-]+)"]
    }


class HiGHSParser(GenericSolverOutputParser):
    """Parser for the HiGHS ILP/LP solver."""
    STATUS_MAP = {
        "Optimal": Status.SAT,
        "Infeasible": Status.UNSAT,
        "feasible": Status.SAT,
        "Timeout": Status.TIMEOUT
    }
    METRIC_PATTERNS = {
        "nodes": [r"Nodes\s+(\d+)"],
        "iterations": [r"LP iterations\s+(\d+)"],
        "objective": [r"Primal bound\s+([\d\.\-]+)"]
    }


# ---------------------------------------------------------------------------
# SMT parsers
# ---------------------------------------------------------------------------

class SMTparser(GenericSolverOutputParser):
    STATUS_MAP = {
        "UNSAT": Status.UNSAT,
        "SAT": Status.SAT,
    }
    METRIC_PATTERNS = {}


# ---------------------------------------------------------------------------
# CP-SAT parsers
# ---------------------------------------------------------------------------

class CPSATParser(GenericSolverOutputParser):
    """Parser for Google OR-Tools CP-SAT solver.
    Matches OR-Tools' native status strings and summary metrics."""
    STATUS_MAP = {
        "INFEASIBLE": Status.UNSAT,  # before FEASIBLE — 'INFEASIBLE' contains 'FEASIBLE'
        "FEASIBLE":   Status.SAT,
        "OPTIMAL":    Status.SAT,
        "UNKNOWN":    Status.UNKNOWN,
    }
    METRIC_PATTERNS = {
        "conflicts": [r"conflicts:\s*(\d+)"],
        "branches":  [r"branches:\s*(\d+)"],
        "wall_time": [r"wall_time:\s*([\d\.]+)"],
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

sat_p   = SATparser()
ilp_p   = ILPparser()
smt_p   = SMTparser()
gen_p   = GenericSolverOutputParser()
cpsat_p = CPSATParser()

PARSER_REGISTRY = {
    # --- By format type ---
    "SAT":   sat_p,
    "ILP":   ilp_p,
    "SMT":   smt_p,
    "CPSAT": cpsat_p,

    # --- By solver name ---
    "CADICAL": sat_p,
    "KISSAT":  sat_p,
    "GLUCOSE": sat_p,

    "HIGHS": HiGHSParser(),

    # --- Fallback ---
    "DEFAULT": gen_p,
}

def get_parser(parser_type: str) -> ResultParser:
    """Looks up *parser_type* (case-insensitive) in PARSER_REGISTRY.

    Falls back to the DEFAULT generic parser if the key is not found.
    """
    return PARSER_REGISTRY.get(parser_type.upper(), PARSER_REGISTRY["DEFAULT"])
