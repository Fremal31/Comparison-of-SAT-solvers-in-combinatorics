from typing import Optional, Dict
from pathlib import Path

from converter import Converter
from parser_strategy import SATparser, ILPparser, SMTparser, GenericParser
from format_types import FormatMetadata

FORMAT_REGISTRY: Dict[str, FormatMetadata] = {
    "SAT": FormatMetadata(format_type="SAT", suffix=".cnf", converter_class=Converter, parser_class=SATparser()),
    "ILP": FormatMetadata(format_type="ILP", suffix=".lp", converter_class=Converter, parser_class=ILPparser()),
    "SMT": FormatMetadata(format_type="SMT", suffix=".smt2", converter_class=Converter, parser_class=SMTparser()),
    "DEFAULT": FormatMetadata(format_type="UNKNOWN", suffix=".txt", converter_class=Converter, parser_class=GenericParser()),
    "UNKNOWN": FormatMetadata(format_type="UNKNOWN", suffix=".txt", converter_class=Converter, parser_class=GenericParser())
}

# requires unique suffixes for each format type - if multiple formats share the same suffix, this will only keep the last one 
SUFFIX_TO_TYPE: Dict[str, str] = {m.suffix: m.format_type for m in FORMAT_REGISTRY.values()}

def resolve_format_metadata(format_type: Optional[str] = None, path: Optional[Path] = None) -> FormatMetadata:
    """
    Looks up FormatMetadata by *format_type* string first, then by file extension
    from *path* if provided. Falls back to the DEFAULT entry if neither matches.
    """
    if format_type:
        key = format_type.upper()
        if key in FORMAT_REGISTRY:
            return FORMAT_REGISTRY[key]

    if path:
        ext = Path(path).suffix.lower()
        if ext in SUFFIX_TO_TYPE:
            return FORMAT_REGISTRY[SUFFIX_TO_TYPE[ext]]
            

    return FORMAT_REGISTRY["DEFAULT"]
