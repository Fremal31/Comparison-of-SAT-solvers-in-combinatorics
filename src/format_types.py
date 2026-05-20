from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

if TYPE_CHECKING:
    from converter import Converter
    from custom_types import ExecutionTriplet, FileConfig, FormulatorConfig, RawResult, TestCase
    from parser_strategy import ResultParser


class FormatMetadata(NamedTuple):
    """
    Registry entry mapping a format type to its file suffix, converter class, and default parser.

    format_type     — canonical type string (e.g. SAT, ILP, UNKNOWN)
    suffix          — file extension for converted formula files (e.g. .cnf, .lp)
    converter_class — Converter class used to produce formula files of this type
    parser_class    — default ResultParser instance used when no explicit parser is configured
    """
    format_type: str
    suffix: str
    converter_class: type['Converter']
    parser_class: 'ResultParser'


class ExperimentContext(NamedTuple):
    """
    Resolved working directory paths for a single (problem, formulator) pair.

    base_path   — directory where the converted formula file is written
    log_dir     — subdirectory where solver output logs are written
    format_info — format metadata for the formula type produced by the formulator
    """
    base_path: Path
    log_dir: Path
    format_info: FormatMetadata


class ConversionTask(NamedTuple):
    """
    Unit of work for the Formulation Phase — converts one (problem, parameters, formulator) instance.

    problem    — the source problem file to convert
    config     — the formulator configuration to use
    work_dir   — resolved paths for output and logs
    timeout    — maximum execution time for the formulator in seconds, or None for no limit
    parameters — instance parameters substituted into formulator option templates
                 via {key} placeholders; empty for parameter-free problems
    """
    problem: 'FileConfig'
    config: 'FormulatorConfig'
    work_dir: ExperimentContext
    timeout: Optional[float] = None
    parameters: dict[str, Any] = {}


class SolvingTask(NamedTuple):
    """
    Unit of work for the Solving Phase — runs one solver on one test case.

    triplet            — the full execution combination (problem, formulator, solver, breaker)
    test_case          — the converted formula file to solve
    timeout            — maximum execution time in seconds, reduced by break_time if breaker was applied
    work_dir           — resolved paths for output and logs
    conversion_metrics — RawResult from the conversion phase, or None for pre-encoded files
    """
    triplet: 'ExecutionTriplet'
    test_case: 'TestCase'
    timeout: float
    work_dir: ExperimentContext
    conversion_metrics: Optional['RawResult'] = None
