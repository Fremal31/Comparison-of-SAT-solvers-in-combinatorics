from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Union, Final
from typing_extensions import Literal
from abc import ABC, abstractmethod
from pathlib import Path

@dataclass
class Result:
    solver: Optional[str] = None
    original_cnf: Optional[str] = None
    break_time: Optional[float] = None
    status: Literal["ERROR", "UNKNOWN", "TIMEOUT", "SYM_BREAK_ERROR", "SAT", "UNSAT"] = "UNKNOWN"
    error: str = ""
    exit_code: int = -1
    cpu_usage_avg: float = 0.0
    cpu_usage_max: float = 0.0
    memory_peak_mb: float = 0.0
    time: float = 0.0
    cpu_time: float = 0.0
    stdout: str = ""
    stderr: str = ""
    

class ResultParser(ABC):
    """
    Strategy Design Pattern for types of solvers
    """

    @abstractmethod
    def parse_status(self, result: Result) -> Result:
        pass

class SATparser(ResultParser):
    def parse_status(self, result: Result) -> str:
        if result.exit_code == 10:
            return "SAT"
        elif result.exit_code == 20:
            return "UNSAT"
        else:
            return "UNKNOWN"
        


class ILPparser(ResultParser):
    pass
