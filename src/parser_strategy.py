from __future__ import annotations
from typing import Optional, Dict, List, Union, Match, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from custom_types import Result

from custom_types import RunnerError, STATUS_UNKNOWN, STATUS_SAT, STATUS_UNSAT, STATUS_TIMEOUT

from abc import ABC, abstractmethod
from pathlib import Path
import re

_PARSE_TAIL_BYTES = 65536  # 64 KB — more than enough for any solver's summary section


def _tail_str(text: str) -> str:
    """Returns the last _PARSE_TAIL_BYTES characters of *text*, starting at a line boundary."""
    if len(text) <= _PARSE_TAIL_BYTES:
        return text
    nl = text.find('\n', len(text) - _PARSE_TAIL_BYTES)
    return text[nl + 1:] if nl != -1 else text[-_PARSE_TAIL_BYTES:]


def _read_tail(path: Path) -> str:
    """Reads only the last _PARSE_TAIL_BYTES of a file without loading it fully into memory."""
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - _PARSE_TAIL_BYTES))
        raw = f.read()
    text = raw.decode('utf-8', errors='replace')
    if size > _PARSE_TAIL_BYTES:
        nl = text.find('\n')
        return text[nl + 1:] if nl != -1 else text
    return text


def _try_to_convert_to_numeric(value: str) -> Union[int, float, str]:
    """Tries to convert *value* to int, then float. Returns the original string if neither works."""
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value

class ResultParser(ABC):
    """
    Abstract base class for solver output parsers (Strategy pattern).

    Subclasses implement *parse* to extract status and metrics from solver
    output and populate the Result object.
    """
    @abstractmethod
    def parse(self, result: Result, output_path: Optional[Path] = None) -> Result:
        """Parses solver output from *result.stdout* or *output_path* and returns
        the updated Result with status and metrics populated."""

class GenericParser(ResultParser):
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
    STATUS_MAP: Dict[str, str] = {}
    METRIC_PATTERNS: Dict[str, List[str]] = {}
    _compiled_patterns: Dict[str, List["re.Pattern[str]"]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for key, patterns in cls.METRIC_PATTERNS.items():
            if isinstance(patterns, str):
                raise RunnerError(f"Patterns in METRIC_PATTERN should be List[str] instead of str")
        cls._compiled_patterns = {
            key: [re.compile(p, re.MULTILINE | re.IGNORECASE) for p in patterns]
            for key, patterns in cls.METRIC_PATTERNS.items()
        }

    @staticmethod
    def _extract_last_metric(content: str, compiled: "re.Pattern[str]") -> Optional[str]:
        matches = compiled.findall(content)
        if not matches:
            return None
        last = matches[-1]
        return last if isinstance(last, str) else last[0]

    def _extract_status(self, content: str) -> Optional[str]:
        """Returns the first matching status from *content*, or None."""
        for keyword, status_name in self.STATUS_MAP.items():
            if keyword in content:
                return status_name
        return None

    def _extract_metrics(self, content: str, metrics: Dict[str, Any]) -> None:
        """Extracts metrics from *content* into *metrics* dict. Only sets a
        metric if it hasn't been found yet (first source wins)."""
        for key, compiled_list in self._compiled_patterns.items():
            if key in metrics:
                continue
            for compiled in compiled_list:
                raw: Optional[str] = self._extract_last_metric(content=content, compiled=compiled)
                if raw:
                    metrics[key] = _try_to_convert_to_numeric(raw)
                    break

    def parse(self, result: Result, output_path: Optional[Path] = None) -> Result:
        stdout_content = _tail_str(result.stdout)
        #stdout_content = (result.stdout)
        file_content = None
        if output_path and output_path.exists():
            file_content = _read_tail(output_path)
            #file_content = output_path.read_text()

        status = self._extract_status(stdout_content)
        if status is None and file_content is not None:
            status = self._extract_status(file_content)
        if status is not None:
            result.status = status

        self._extract_metrics(stdout_content, result.metrics)
        if file_content is not None:
            self._extract_metrics(file_content, result.metrics)

        result.stdout = "Parsed and cleared."
        return result
    
    
class GenericBreaker(GenericParser):
    """Parser for symmetry breakers — expects no status or metrics in output."""

class SATparser(GenericParser):
    """Parser for DIMACS-compatible SAT solvers using the standard 's SATISFIABLE' output format.
    Covers Glucose, CaDiCaL, Kissat, Minisat and similar solvers."""
    STATUS_MAP = {
        "s SATISFIABLE": STATUS_SAT,
        "s UNSATISFIABLE": STATUS_UNSAT,
        "s UNKNOWN": STATUS_UNKNOWN
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


class ILPparser(GenericParser):
    """Parser for generic ILP solvers."""
    STATUS_MAP = {
        "optimal solution found": STATUS_SAT,
        "unfeasible": STATUS_UNSAT,
        "infeasible": STATUS_UNSAT,
        "not feasible": STATUS_UNSAT,
        "feasible": STATUS_SAT,  # must come after unfeasible/infeasible — first match wins
        "s UNKNOWN": STATUS_UNKNOWN
    }
    METRIC_PATTERNS = {
        "nodes": [r"c nodes:\s+(\d+)"],
        "iterations": [r"c iterations:\s+(\d+)"],
        "objective": [r"c objective:\s+([\d\.\-]+)"]
    }
    

class HiGHSParser(GenericParser):
    """Parser for the HiGHS ILP/LP solver."""
    STATUS_MAP = {
        "Optimal": STATUS_SAT,
        "Infeasible": STATUS_UNSAT,
        "feasible": STATUS_SAT,
        
        "Timeout": STATUS_TIMEOUT
    }

    METRIC_PATTERNS = {
        #"status": [r"Status\s+([a-zA-Z]+)"], 
        "nodes": [r"Nodes\s+(\d+)"],
        "iterations": [r"LP iterations\s+(\d+)"],
        "objective": [r"Primal bound\s+([\d\.\-]+)"]
    }


class SMTparser(GenericParser):
    STATUS_MAP = {
        "UNSAT": STATUS_UNSAT,
        "SAT": STATUS_SAT,
    }

    METRIC_PATTERNS = {
    }
    

sat_p = SATparser()
ilp_p = ILPparser()
smt_p = SMTparser()
gen_p = GenericParser()

PARSER_REGISTRY = {
    # --- Types ---
    "SAT": sat_p,
    "ILP": ilp_p,
    "SMT": smt_p,
    
    # --- Specific Solver Names (The Fallbacks) ---
    "CADICAL": sat_p,
    "KISSAT":  sat_p,
    "GLUCOSE": sat_p,
    
    "HIGHS": HiGHSParser(),
    # --- System ---
    "DEFAULT": gen_p
}

def get_parser(parser_type: str) -> ResultParser:
    """Looks up *parser_type* (case-insensitive) in PARSER_REGISTRY.

    Falls back to the DEFAULT generic parser if the key is not found.
    """
    return PARSER_REGISTRY.get(parser_type.upper(), PARSER_REGISTRY["DEFAULT"])
