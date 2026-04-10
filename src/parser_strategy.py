from __future__ import annotations
from typing import Optional, Dict, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from custom_types import Result

from custom_types import RunnerError, STATUS_UNKNOWN, STATUS_SAT, STATUS_UNSAT, STATUS_TIMEOUT

from abc import ABC, abstractmethod
from pathlib import Path
import re


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
    *output_path* is provided, falls back to reading the output file. Metrics
    are then extracted from whichever source resolved the status. This means
    all output — status and metrics — is expected from a single source.

    If a solver writes its output to a file rather than stdout, configure it
    with '{output}' or '>' in options so the file becomes the primary source.

    NOTE: STATUS_MAP keys are matched as substrings in order - of one key is a substring of another, the longer, more specific one should come first to avoid false matches.

    Subclass and override *STATUS_MAP* and *METRIC_PATTERNS* to support a new solver.
    """
    STATUS_MAP: Dict[str, str] = {}
    METRIC_PATTERNS: Dict[str, List[str]] = {}

    def parse(self, result: Result, output_path: Optional[Path] = None) -> Result:
        for key, patterns in self.METRIC_PATTERNS.items():
            if isinstance(patterns, str):
                raise RunnerError(f"Patterns in METRIC_PATTERN should be List[str] instead of str")

        content = result.stdout
        # print(f"Parsing output for {result.solver} on {result.problem}...")
        
        for keyword, status_name in self.STATUS_MAP.items():
            if keyword in content:
                result.status = status_name
                break
        if result.status == STATUS_UNKNOWN and output_path and output_path.exists():
            # print(f"Status not in STDOUT. Checking file: {output_path}")
            content = output_path.read_text()

            for keyword, status_name in self.STATUS_MAP.items():
                if keyword in content:
                    result.status = status_name
                    break
        
        for key, patterns in self.METRIC_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
                if match:
                    raw = match.group(1) if match.groups() else match.group(0)
                    result.metrics[key] = _try_to_convert_to_numeric(raw)
        # print(f"Parsed status: {result.status}, metrics: {result.metrics}")
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
        "feasible": STATUS_SAT,
        
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
        STATUS_UNSAT: STATUS_UNSAT,
        STATUS_SAT: STATUS_SAT,
        STATUS_TIMEOUT: STATUS_TIMEOUT
    }

    METRIC_PATTERNS = {
    }
    

sat_p = SATparser()
ilp_p = ILPparser()
smt_p = SMTparser()
gen_p = GenericParser()

PARSER_REGISTRY = {
    # --- Types ---
    STATUS_SAT: sat_p,
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
