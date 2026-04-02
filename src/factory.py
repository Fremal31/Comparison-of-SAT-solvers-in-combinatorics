from typing import Dict, Type, Optional
from pathlib import Path
from converter import Converter
from parser_strategy import get_parser
from runner import Runner
from custom_types import FormulatorConfig, ExecConfig, FormatMetadata
from metadata_registry import resolve_format_metadata

def get_converter(form_cfg: FormulatorConfig) -> Converter:
    metadata = resolve_format_metadata(format_type=form_cfg.formulator_type)
    return metadata.converter_class(converter_cfg=form_cfg, metadata=metadata)

def get_runner(problem_type: str, solv_cfg: ExecConfig) -> Runner:
    if solv_cfg.parser and isinstance(solv_cfg.parser, str):
        parser = get_parser(solv_cfg.parser)
    else:
        metadata = resolve_format_metadata(format_type=problem_type)
        parser = metadata.parser_class if metadata and metadata.parser_class else get_parser("generic")
    return Runner(solv_cfg, parser)
   