from pathlib import Path
from dataclasses import dataclass, field
from typing import NamedTuple, List, Dict, Optional, Union, Literal, Type
from enum import Enum

from .converter import Converter
from .parser_strategy import *
from .custom_types import FormatMetadata

# note: this is a simple heuristic and may not cover all cases, but it allows us to infer the format type from the file extension when the format type is not explicitly provided.


FORMAT_REGISTRY: Dict[str, FormatMetadata] = {
    "SAT": FormatMetadata("SAT", ".cnf", Converter, SATparser()),
    "ILP": FormatMetadata("ILP", ".lp", Converter, ILPparser()),
    "SMT": FormatMetadata("SMT", ".smt2", Converter, SATparser()),
    "DEFAULT": FormatMetadata("UNKNOWN", ".txt", Converter, GenericParser())
}

# requires unique suffixes for each format type - if multiple formats share the same suffix, this will only keep the last one 
SUFFIX_TO_TYPE: Dict[str, str] = {m.suffix: m.format_type for m in FORMAT_REGISTRY.values()}

def resolve_format_metadata(format_type: Optional[str] = None, path: Optional[Path] = None) -> FormatMetadata:
    if format_type:
        key = format_type.upper()
        if key in FORMAT_REGISTRY:
            return FORMAT_REGISTRY[key]

    if path:
        ext = Path(path).suffix.lower()
        if ext in SUFFIX_TO_TYPE:
            return FORMAT_REGISTRY[SUFFIX_TO_TYPE[ext]]
            

    return FORMAT_REGISTRY["DEFAULT"]
