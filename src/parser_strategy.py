from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import Optional

from custom_types import Result, TestCase

class ResultParser(ABC):
    """
    Strategy Design Pattern for parsing solver outputs.
    """
    @abstractmethod
    def parse(self, result: Result, output_path: Optional[Path] = None) -> Result:
        pass

class GenericParser(ResultParser):
    STATUS_MAP = {}     # e.g., {"s SATISFIABLE": "SAT"}
    METRIC_PATTERNS = {} # e.g., {"conflicts": [r"conflicts:\s+(\d+)", "c conflicts:\s+(\d+)"]}

    def parse(self, result: Result, output_path: Optional[Path] = None) -> Result:
        content = result.stdout
        print(f"Parsing output for {result.solver} on {result.problem}...")
        
        for keyword, status_name in self.STATUS_MAP.items():
            if keyword in content:
                result.status = status_name
                break
        if result.status == "UNKNOWN" and output_path and output_path.exists():
            print(f"Status not in STDOUT. Checking file: {output_path}")
            content = output_path.read_text()

            for keyword, status_name in self.STATUS_MAP.items():
                if keyword in content:
                    result.status = status_name
                    break
        
        for key, patterns in self.METRIC_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
                if match:
                    val = match.group(1)
                    result.metrics[key] = int(val) if val.isdigit() else val
                    break
        print(f"Parsed status: {result.status}, metrics: {result.metrics}")
        result.stdout = "Parsed and cleared."
        return result
    
    
class GenericBreaker(GenericParser):
    STATUS_MAP = {}
    METRIC_PATTERNS = {}

class SATparser(GenericParser):
    STATUS_MAP = {
        "s SATISFIABLE": "SAT",
        "s UNSATISFIABLE": "UNSAT",
        "s UNKNOWN": "UNKNOWN"
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
    STATUS_MAP = {
        "s OPTIMUM FOUND": "SAT",
        "s INCONSISENT": "UNSAT",
        "s UNKNOWN": "UNKNOWN"
    }
    METRIC_PATTERNS = {
        "nodes": r"c nodes:\s+(\d+)",
        "iterations": r"c iterations:\s+(\d+)",
        "objective": r"c objective:\s+([\d\.\-]+)"
    }
    

sat_p = SATparser()
ilp_p = ILPparser()
gen_p = GenericParser()

PARSER_REGISTRY = {
    # --- Types ---
    "SAT": sat_p,
    "ILP": ilp_p,
    
    # --- Specific Solver Names (The Fallbacks) ---
    "CADICAL": sat_p,
    "KISSAT":  sat_p,
    "GLUCOSE": gen_p,
    
    # --- System ---
    "DEFAULT": gen_p
}

def get_parser(parser_type: str) -> ResultParser:
    return PARSER_REGISTRY.get(parser_type.upper(), PARSER_REGISTRY["DEFAULT"])
