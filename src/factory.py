from typing import Optional, Set

from converter import Converter
from parser_strategy import get_parser, ResultParser
from runner import Runner
from generic_executor import GenericExecutor
from custom_types import FormulatorConfig, ExecConfig
from metadata_registry import resolve_format_metadata
from format_types import FormatMetadata

def get_converter(form_cfg: FormulatorConfig) -> Converter:
    """Creates a Converter for the given formulator config, resolving the
    appropriate metadata (suffix, converter class) from the format registry."""
    metadata = resolve_format_metadata(format_type=form_cfg.formulator_type)
    return metadata.converter_class(converter_cfg=form_cfg, metadata=metadata)

def get_runner(problem_type: str, solv_cfg: ExecConfig, executor: GenericExecutor,
               enabled_metrics: Optional[Set[str]] = None) -> Runner:
    """
    Creates a Runner for the given solver config, resolving the parser strategy.

    If *solv_cfg.parser* is set, that key is looked up directly in PARSER_REGISTRY.
    Otherwise the default parser for *problem_type* is used from the format registry,
    falling back to the generic parser if none is found.

    *enabled_metrics* is forwarded to the Runner so the parser can skip extraction
    of metrics the user has disabled in config.
    """
    if solv_cfg.parser and isinstance(solv_cfg.parser, str):
        parser: ResultParser = get_parser(parser_type=solv_cfg.parser.upper())
    else:
        metadata: FormatMetadata = resolve_format_metadata(format_type=problem_type)
        parser = metadata.parser_class if metadata and metadata.parser_class else get_parser(problem_type)
    return Runner(config=solv_cfg, parser=parser, executor=executor,
                  enabled_metrics=enabled_metrics)
