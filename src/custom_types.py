from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union


class Status(str, Enum):
    SAT = "SAT"
    UNSAT = "UNSAT"
    OK = "OK"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    EXIT_ERROR = "EXIT_ERROR"
    MISSING_OUTPUT = "MISSING_OUTPUT"
    PARSER_ERROR = "PARSER_ERROR"
    BREAKER_ERROR = "BREAKER_ERROR"
    UNKNOWN = "UNKNOWN"


class RunOutcome(str, Enum):
    """How the whole benchmark run terminated (distinct from a single solver's
    Status). Set in main.py and rendered in the HTML summary."""
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"  # KeyboardInterrupt — partial results
    ERROR = "error"              # unhandled exception aborted the run


EXIT_CODE_TIMEOUT = -1

CRITICAL_STATUSES: set[Status] = {
    Status.ERROR,
    Status.MISSING_OUTPUT,
    Status.EXIT_ERROR,
    Status.PARSER_ERROR,
    Status.BREAKER_ERROR,
    Status.TIMEOUT,
}
"""Statuses that indicate a non-recoverable failure — used to short-circuit solver execution."""

NULL_PROBLEM = "NULL_PROBLEM"        # sentinel; a real run should never surface this
NULL_FORMULATOR = "NULL_FORMULATOR"
NULL_BREAKER = "NULL_BREAKER"
NULL_SOLVER = "NULL_SOLVER"          # sentinel; a real run should never surface this



@dataclass
class FileConfig:
    """
    A raw problem file to be converted by a formulator before solving.

    name       — unique identifier used as a key throughout the pipeline
    path       — path to the problem file
    enabled    — if False, skipped during batch mode triplet generation
    parameters — optional list of parameter dicts; each dict turns the source
                 file into one independent problem instance. Empty/missing means
                 a single instance with no parameters (legacy behaviour).
                 Parameter values are substituted into formulator option templates
                 via {key} placeholders. See cmd_builder.build_cmd.
    """
    name: str
    path: str
    enabled: bool = True
    parameters: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FormulatorConfig:
    """
    Configuration for a formulator script that converts a problem file into a solver-ready formula.

    name            — unique identifier used as a key throughout the pipeline
    formulator_type — output format produced (e.g. SAT, ILP)
    cmd             — path to the formulator script or system command
    enabled         — if False, skipped during batch mode triplet generation
    options         — command-line flags; supports {input}, {output}, <, > tokens
    output_mode     — how the formulator delivers its output: 'stdout', 'stdout_multi', or 'directory'
    """
    name: str
    formulator_type: str
    cmd: str
    enabled: bool
    options: list[str] = field(default_factory=list)
    output_mode: str = "stdout"

@dataclass
class ExecConfig:
    """
    Configuration for a solver or symmetry breaker executable.

    name        — unique identifier used as a key throughout the pipeline
    solver_type — format type the solver accepts (e.g. SAT, ILP)
    cmd         — system command or path to the solver binary
    options     — command-line flags; supports {input}, {output}, <, > tokens
    enabled     — if False, skipped during batch mode triplet generation
    parser      — explicit parser key from PARSER_REGISTRY; if None, resolved from solver_type
    """
    name: str
    solver_type: str
    cmd: str
    options: list[str] = field(default_factory=list)
    enabled: bool = True
    parser: Optional[str] = None  # explicit parser key; if None, resolved from solver_type
    threads: int = 1


@dataclass
class TestCase:
    """
    A solver-ready formula file, either converted from a problem file or pre-encoded.

    name            — identifier for this test case, usually derived from the problem name
    path            — path to the formula file (.cnf, .lp, etc.)
    problem_cfg     — the source problem this was converted from, or None for pre-encoded files
    formulator_cfg  — the formulator used to produce this file, or None for pre-encoded files
    tc_type         — format type (SAT, ILP, etc.); auto-detected from file extension if not set
    generated_files — files created during conversion or symmetry breaking, tracked for cleanup
    enabled         — if False, skipped during execution
    """
    __test__ = False  # prevent pytest from treating this as a test case class
    name: str
    path: Union[str, Path]
    problem_cfg: Optional[FileConfig] = None
    formulator_cfg: Optional[FormulatorConfig] = None
    tc_type: str = "UNKNOWN"
    generated_files: list[Path] = field(default_factory=list)
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.tc_type is None or self.tc_type == "UNKNOWN" or self.tc_type == "":
            from metadata_registry import resolve_format_metadata

            self.tc_type = resolve_format_metadata(path=Path(self.path)).format_type


@dataclass
class ExecutionTriplet:
    """
    A single benchmark run combination: one problem, one formulator, one solver,
    and an optional symmetry breaker.

    problem    — the source problem file config
    formulator — the formulator used to convert the problem
    solver     — the solver to run, or None if the triplet should be expanded
                 to all compatible solvers by the solver manager
    breaker    — optional symmetry breaker applied before solving
    test_case  — set directly in triplet mode for pre-encoded files; problem and
                 formulator are then populated with dummy placeholders
    """
    problem: Optional[FileConfig]
    formulator: Optional[FormulatorConfig]
    solver: Optional[ExecConfig] = None
    breaker: Optional[ExecConfig] = None
    test_case: Optional[TestCase] = None
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """
    The outcome of a single solver run.

    metrics         — solver-specific values extracted by the parser (e.g. conflicts, decisions)
    solver          — name of the solver
    problem         — name of the test case (converted formula file)
    parent_problem  — name of the original problem file before conversion
    formulator      — name of the formulator used, or None if not applicable
    breaker         — name of the symmetry breaker used, or None if not applied
    break_time      — time spent on symmetry breaking in seconds
    status          — SAT, UNSAT, TIMEOUT, ERROR, BREAKER_ERROR, or UNKNOWN
    error           — error message if execution failed, empty string otherwise
    exit_code       — process exit code; -1 if timed out or not yet set
    cpu_usage_avg   — average CPU usage percentage during execution
    memory_peak_mb  — peak RSS memory usage in megabytes
    time            — solver wall-clock time in seconds (excludes break_time and conversion_time)
    cpu_time        — total CPU time (user + system) in seconds
    stdout          — captured stdout, cleared to 'Parsed and cleared.' after parsing
    stderr          — captured stderr
    """
    metrics: dict[str, Any] = field(default_factory=dict)
    solver: Optional[str] = None
    problem: Optional[str] = None
    parent_problem: Optional[str] = None  # original problem name before conversion
    parameters: dict[str, Any] = field(default_factory=dict)
    formulator: str = NULL_FORMULATOR
    breaker: str = NULL_BREAKER
    break_time: float = 0.0
    break_cpu_time: float = 0.0
    break_memory_mb: float = 0.0
    conversion_time: float = 0.0
    conversion_cpu_time: float = 0.0
    conversion_memory_mb: float = 0.0
    status: Status = Status.UNKNOWN
    error: str = ""
    exit_code: int = -1
    cpu_usage_avg: float = 0.0
    memory_peak_mb: float = 0.0
    time: float = 0.0
    cpu_time: float = 0.0
    stdout: str = ""
    stderr: str = ""
    cores_used: Optional[list[int]] = None

    @property
    def total_time(self) -> float:
        return self.conversion_time + self.break_time + self.time


@dataclass
class VisualizationConfig:
    """
    Configuration for optional plot generation after a benchmark run.

    enabled     — if True, plots are generated after the run completes
    output_dir  — directory where plots are saved
    per_problem — if True, emit the per-(problem, params) time-breakdown bars
    comparison  — if True, emit the cross-solver charts (status counts,
                  CPU-time box plot, cactus/survival plot)

    The per-class toggles default to True so configs that omit them keep the
    original "all plots" behaviour.
    """
    enabled: bool = False
    output_dir: str = "./results/plots"
    per_problem: bool = True
    comparison: bool = True


@dataclass
class PlotResult:
    """
    comparison  — paths to the cross-solver charts (cactus, status counts,
                  CPU-time box plot), shown in the report's Plots section
    per_problem — map of (instance, params_tag) -> path of that instance's
                  time-breakdown chart, embedded as expandable rows in the
                  verdict table. The key matches InstanceSummary
                  (parent_problem, params_tag) so the two line up.
    """
    comparison: list[str] = field(default_factory=list)
    per_problem: dict[tuple[str, str], str] = field(default_factory=dict)


@dataclass
class ThreadConfig:
    """
    Parallel-execution and monitoring tuning.

    max_threads             — number of parallel worker threads (one subprocess each)
    allowed_cores           — CPU core ids to pin workers to via taskset; None disables pinning
    ensure_cleanup_on_crash — if True, set PR_SET_PDEATHSIG on spawned solvers so the kernel
                              kills them if the framework dies before it can reap them
    monitor_poll_interval   — seconds between GlobalMonitor sampling cycles (CPU/memory)
    """
    max_threads: int
    allowed_cores: Optional[list[int]] = None
    ensure_cleanup_on_crash: bool = False
    monitor_poll_interval: float = 0.5

@dataclass
class Config:
    """
    The fully parsed and validated experiment configuration.

    metrics_measured  — dict of metric name to bool; controls which columns appear in CSV output
    solvers           — list of all solver configs (enabled and disabled)
    formulators       — list of all formulator configs
    breakers          — list of all symmetry breaker configs
    files             — list of problem file configs to be converted
    without_converter — list of pre-encoded test cases that skip the formulator step
    timeout           — maximum execution time per solver run in seconds
    triplets          — explicit run combinations used in triplet mode
    triplet_mode      — if True, only triplets are run; if False, full cross-product is generated
    max_threads       — number of parallel worker processes
    delete_working_dir — if True, working_dir is deleted at the start of each run
    working_dir       — directory for intermediate files and logs
    results_csv       — path to the output CSV file
    results_json      — path to the structured output JSON file
    results_jsonl     — path to the incremental JSONL file (crash-safe, one result per line)
    results_html      — path to the self-contained HTML report (sortable/filterable table, embedded plots)
    visualization     — plot generation configuration
    """
    metrics_measured: dict[str, bool]
    solvers: list[ExecConfig]
    formulators: list[FormulatorConfig]
    breakers: list[ExecConfig]
    files: list[FileConfig]
    without_converter: list[TestCase]
    timeout: int
    triplets: list[ExecutionTriplet]
    triplet_mode: bool
    thread_config: ThreadConfig
    delete_working_dir: bool
    working_dir: Path
    results_csv: str
    results_json: str
    results_jsonl: str
    results_html: str
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)
    use_hardlink: bool = False


@dataclass
class RawResult:
    """
    Low-level result from GenericExecutor — contains only subprocess output
    and resource metrics, with no solver-specific interpretation.

    stdout         — captured stdout (empty if piped to file)
    stderr         — captured stderr
    exit_code      — process exit code; -1 if not set
    time           — wall-clock time in seconds
    cpu_time       — total CPU time (user + system) in seconds
    memory_peak_mb — peak RSS memory usage in megabytes
    cpu_avg        — average CPU usage percentage
    timed_out      — True if the process exceeded the timeout
    launch_failed  — True if the process failed to start
    error          — error message if execution failed
    """
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    time: float = 0.0
    cpu_time: float = 0.0
    memory_peak_mb: float = 0.0
    cpu_avg: float = 0.0
    timed_out: bool = False
    launch_failed: bool = False
    error: Optional[str] = None
    cores_used: Optional[list[int]] = None


class RunnerError(Exception):
    """Exception raised for errors during the solver execution process."""
    pass

class ConversionError(Exception):
    """Base exception for converter failures."""
    pass