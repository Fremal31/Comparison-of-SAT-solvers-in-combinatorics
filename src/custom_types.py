from pathlib import Path
from dataclasses import dataclass, field
from typing import NamedTuple, List, Dict, Optional, Union, Literal, Type, Final, Any
from enum import Enum
from format_types import FormatMetadata, ExperimentContext, ConversionTask, SolvingTask


STATUS_OK: Final = "OK"
STATUS_TIMEOUT: Final = "TIMEOUT"
STATUS_ERROR: Final = "ERROR"
STATUS_EXIT_ERROR: Final = "EXIT_ERROR"
STATUS_MISSING_OUTPUT: Final = "MISSING_OUTPUT"
STATUS_PARSER_ERROR: Final = "PARSER_ERROR"
STATUS_BREAKER_ERROR: Final = "BREAKER_ERROR"

CRITICAL_STATUSES: set[str] = {STATUS_ERROR, STATUS_MISSING_OUTPUT, STATUS_EXIT_ERROR, STATUS_PARSER_ERROR, STATUS_BREAKER_ERROR}


@dataclass
class FileConfig:
    name: str
    path: str
    enabled: bool = True

@dataclass
class FormulatorConfig:
    name: str
    formulator_type: str
    cmd: str
    enabled: bool
    options: List[str] = field(default_factory=list)
    output_mode: str = "stdout"
    output_param: Optional[str] = None

@dataclass
class ExecConfig:
    name: str
    solver_type: str
    cmd: str
    options: List[str] = field(default_factory=list)
    enabled: bool = True
    output_param: Optional[str] = None
    parser: Optional[str] = None

@dataclass
class TestCase:
    name: Optional[str]
    path: Union[str, Path]
    problem_cfg: Optional[FileConfig] = None
    formulator_cfg: Optional[FormulatorConfig] = None
    tc_type: Optional[str] = "UNKNOWN"
    generated_files: List[Path] = field(default_factory=list)
    enabled: bool = True

    def __post_init__(self):
        if self.tc_type is None or self.tc_type == "UNKNOWN" or self.tc_type == "":
            from metadata_registry import resolve_format_metadata
            self.tc_type = resolve_format_metadata(path=self.path).format_type


@dataclass
class ExecutionTriplet:
    problem: Optional[FileConfig]
    formulator: Optional[FormulatorConfig]
    solver: ExecConfig
    breaker: Optional[ExecConfig] = None
    test_case: Optional[TestCase] = None


@dataclass
class Result:
    metrics: dict[str, Any] = field(default_factory=dict)
    solver: Optional[str] = None
    problem: Optional[str] = None
    parent_problem: Optional[str] = None
    formulator: Optional[str] = None
    breaker: str = "None"
    break_time: float = 0.0
    status: str = "UNKNOWN"
    error: str = ""
    exit_code: int = -1
    cpu_usage_avg: float = 0.0
    cpu_usage_max: float = 0.0
    memory_peak_mb: float = 0.0
    time: float = 0.0
    cpu_time: float = 0.0
    stdout: str = ""
    stderr: str = ""


@dataclass
class Config:
    metrics_measured: Dict[str, bool]
    solvers: List[ExecConfig]
    formulators: List[FormulatorConfig]
    breakers: List[ExecConfig]
    files: List[FileConfig]
    without_converter: List[TestCase]
    timeout: int
    triplets: List[ExecutionTriplet]
    triplet_mode: bool
    max_threads: int
    delete_working_dir: bool
    working_dir: Path
    results_csv: str


class RunnerError(Exception):
    """Exception raised for errors during the solver execution process."""
    pass

class ConversionError(Exception):
    """Base exception for converter failures."""
    pass