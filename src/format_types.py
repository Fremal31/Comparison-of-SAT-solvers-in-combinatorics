from typing import NamedTuple, Type, Any, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from converter import Converter
    from parser_strategy import ResultParser
    from custom_types import FileConfig, FormulatorConfig, ExecutionTriplet, TestCase


class FormatMetadata(NamedTuple):
    format_type: str
    suffix: str
    converter_class: Type['Converter']
    parser_class: 'ResultParser'


class ExperimentContext(NamedTuple):
    base_path: Path
    log_dir: Path
    format_info: FormatMetadata


class ConversionTask(NamedTuple):
    problem: 'FileConfig'
    config: 'FormulatorConfig'
    work_dir: ExperimentContext


class SolvingTask(NamedTuple):
    triplet: 'ExecutionTriplet'
    test_case: 'TestCase'
    timeout: float
    work_dir: ExperimentContext
