import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional, Union

from custom_types import (
    Config,
    ExecConfig,
    ExecutionTriplet,
    FileConfig,
    FormulatorConfig,
    TestCase,
    ThreadConfig,
    VisualizationConfig,
)
from metadata_registry import FORMAT_REGISTRY, resolve_format_metadata
from parser_strategy import PARSER_REGISTRY

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR: Path = Path(__file__).parent.resolve()
_base_dir: Path = _DEFAULT_BASE_DIR


def get_base_dir() -> Path:
    """Returns the current base directory used for resolving relative paths."""
    return _base_dir


def set_base_dir(path: Path) -> None:
    """Sets the base directory used for resolving relative paths."""
    global _base_dir
    _base_dir = path.resolve()


def reset_base_dir() -> None:
    """Resets the base directory to the default (src/ directory). Useful for testing."""
    global _base_dir
    _base_dir = _DEFAULT_BASE_DIR


def _resolve_path(path_str: str) -> str:
    """Resolves *path_str* relative to the current base directory if not absolute.

    Returns the resolved path as a string.
    """
    p = Path(path_str)
    if not p.is_absolute():
        p = (_base_dir / p).resolve()
    return str(p)


def _ensure_results_directory(path_str: str) -> None:
    """Creates parent directories for *path* and checks it is writable if it already exists.

    Raises PermissionError if the path exists but is not writable.
    """
    path = Path(path_str).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"Cannot write to result file: {path}")

def _validate_name_and_paths(
    name: str, cmd: str, component_type: str, check_executable: bool = False
) -> Union[str, Path]:
    """
    Validates *name* is not reserved and resolves *cmd* to an executable path.

    Returns the system command as-is if found on PATH, otherwise resolves it
    relative to the current base directory. When *check_executable* is True, also verifies
    the path is a file and has execute permission.

    Raises ValueError, FileNotFoundError, or PermissionError on invalid input.
    """
    if name.lower() == "none":
        raise ValueError(
            f"{component_type} name cannot be '{name}' as it is reserved for test cases "
            "without a formulator. Please choose a different name for the formulator."
        )
    if cmd is None or cmd.strip() == "":
        raise ValueError(f"{component_type} config '{name}' has an empty 'cmd' field, which is not valid.")
    if shutil.which(cmd):
        return cmd  # system command found in PATH, return as is
    path_obj = Path(cmd)
    if not path_obj.is_absolute():
        path_obj = (_base_dir / path_obj).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"Config '{name}' points to non-existent: {path_obj}")
    
    if check_executable:
        if not path_obj.is_file():
            raise ValueError(f"{component_type} '{name}' path is a directory, but needs to be an executable file.")
        if not os.access(path_obj, os.X_OK):
            raise PermissionError(f"{component_type} '{name}' at {path_obj} is not executable. Run 'chmod +x'.")
    
    return path_obj

def _get_validated_path(name: str, raw_path: str, component_type: str, enabled: bool, is_exec: bool = False) -> str:
    """
    Returns validated path if component is on, else return resolved from relative path.
    """
    if enabled:
        return str(_validate_name_and_paths(
            name=name, cmd=raw_path, component_type=component_type, check_executable=is_exec
        ))
    return _resolve_path(path_str=raw_path)


def _validate_type_field(name: str, type_value: str, component_type: str) -> None:
    """Raises ValueError if *type_value* is empty, 'UNKNOWN', or not present in the format registry."""
    if type_value is None or type_value.strip() == "":
        raise ValueError(f"{component_type} config '{name}' has an empty 'type' field, which is not valid.")
    if type_value == "UNKNOWN":
        raise ValueError(
            f"{component_type} config '{name}' has 'type' field set to 'UNKNOWN', which is not "
            f"valid. Please specify a valid type for the {component_type.lower()}."
        )
    if resolve_format_metadata(type_value).format_type == "UNKNOWN":
        raise ValueError(
            f"{component_type} config '{name}' has unrecognized 'type' field value "
            f"'{type_value}'. Valid types are: {list(FORMAT_REGISTRY)}."
        )
    
def _parse_single_formulator_config(name: str, data: dict[str, Any]) -> FormulatorConfig:
    """Parses and validates a single formulator entry from the config dict.

    Raises ValueError if required fields are missing or invalid, FileNotFoundError
    if the cmd path does not exist, and PermissionError if it is not executable.
    """
    component_type = "Formulator"
    if 'cmd' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'cmd' field.")
    enabled: bool = data.get('enabled', False)

    raw_path: Optional[str] = data.get("cmd")
    if raw_path is None:
        raise ValueError("Missing cmd in config.")
    path_to_formulator = _get_validated_path(
        name=name, raw_path=raw_path, component_type=component_type, enabled=enabled, is_exec=True
    )
    
    if 'type' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'type' field.")
    _validate_type_field(name, data.get('type', ''), component_type=component_type)
    return FormulatorConfig(
        name=name,
        formulator_type=data['type'],
        cmd=str(path_to_formulator),
        enabled=data.get('enabled', False),
        options=data.get('options', []),
        output_mode=data.get('output_mode', "stdout")
    )

def _parse_formulator_config(data: dict[str, Any]) -> list[FormulatorConfig]:
    """Parses all formulator entries from the config dict."""
    return [_parse_single_formulator_config(k, v) for k, v in data.items()]

def _parse_single_exec_config(name: str, data: dict[str, Any]) -> ExecConfig:
    """Parses and validates a single solver or breaker entry from the config dict.

    Raises ValueError if required fields are missing or invalid, FileNotFoundError
    if the cmd path does not exist, and PermissionError if it is not executable.
    """
    component_type = "Solver/Breaker"
    if 'cmd' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'cmd' field.")
    enabled: bool = data.get('enabled', False)

    raw_path: Optional[str] = data.get("cmd")
    if raw_path is None:
        raise ValueError("Missing cmd in config.")
    path_to_solver: str = _get_validated_path(
        name=name, raw_path=raw_path, component_type=component_type, enabled=enabled, is_exec=True
    )
    
    if 'type' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'type' field.")
    _validate_type_field(name, data.get('type', ''), component_type=component_type)

    if data.get('output_param') is not None:
        logger.warning(
            "'%s' has 'output_param' set — this field is deprecated. Use '{output}' in options instead.", name
        )

    parser_key: Optional[str] = data.get('parser')
    if parser_key is not None and parser_key.upper() not in PARSER_REGISTRY:
        raise ValueError(
            f"Solver/Breaker config '{name}' specifies unknown parser '{parser_key}'. "
            f"Valid keys: {list(PARSER_REGISTRY)}."
        )

    return ExecConfig(
        name=name,
        solver_type=resolve_format_metadata(format_type=data['type']).format_type,
        cmd=str(path_to_solver),
        options=data.get('options', []),
        enabled=data.get('enabled', False),
        parser=parser_key,
        threads=data.get('threads', 1)
    )

def _parse_exec_config(data: dict[str, Any]) -> list[ExecConfig]:
    """Parses all solver or breaker entries from the config dict."""
    return [_parse_single_exec_config(k, v) for k, v in data.items()]

def _parse_parameters_field(name: str, raw: Any) -> list[dict[str, Any]]:
    """Validates and returns the *parameters* sweep declared on a file entry.

    Accepts a list of dicts (one entry per concrete instance). Missing or
    empty -> empty list, meaning a single instance with no parameters
    (legacy behaviour). Each dict's keys must be strings; values are passed
    through unchanged and stringified later by *cmd_builder*.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"File config '{name}': 'parameters' must be a list of dicts, got {type(raw).__name__}."
        )
    parsed: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(
                f"File config '{name}': 'parameters[{i}]' must be a dict, got {type(entry).__name__}."
            )
        for key in entry:
            if not isinstance(key, str):
                raise ValueError(
                    f"File config '{name}': 'parameters[{i}]' has non-string key {key!r}."
                )
        parsed.append(dict(entry))
    return parsed


def _parse_single_file_config(name: str, data: dict[str, Any]) -> list[FileConfig]:
    """Parses and validates a single problem file entry from the config dict.

    If the path points to a directory, expands into one FileConfig per file
    in that directory, named {config_name}_{file_stem}.

    Raises ValueError if the path field is missing, FileNotFoundError if the
    path does not exist.
    """
    component_type = "File"
    enabled: bool = data.get('enabled', True)
    if 'path' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'path' field.")
    raw_path: Optional[str] = data.get('path')
    if raw_path is None:
        raise ValueError("Missing path in config")
    path_to_problem: str = _get_validated_path(
        name=name, raw_path=raw_path, component_type=component_type, enabled=enabled, is_exec=False
    )
    resolved = Path(path_to_problem)
    parameters: list[dict[str, Any]] = _parse_parameters_field(name=name, raw=data.get('parameters'))

    if resolved.is_dir():
        files: list[Path] = sorted(f for f in resolved.iterdir() if f.is_file())
        if not files:
            raise ValueError(f"{component_type} config '{name}' points to an empty directory: {resolved}")
        result: list[FileConfig] = []
        for f in files:
            result.append(FileConfig(name=f"{name}_{f.stem}", path=str(f), enabled=enabled, parameters=parameters))
        return result

    return [FileConfig(
        name=name,
        path=str(resolved),
        enabled=enabled,
        parameters=parameters)]

def _parse_file_config(data: dict[str, Any]) -> list[FileConfig]:
    """Parses all problem file entries from the config dict.
    Directory entries are expanded into one FileConfig per file."""
    configs: list[FileConfig] = []
    for k, v in data.items():
        configs.extend(_parse_single_file_config(k, v))
    return configs

def _parse_single_without_converter(name: str, data: dict[str, Any]) -> TestCase:
    """Parses and validates a single pre-encoded file entry from the config dict.

    Raises ValueError if the path field is missing or the type cannot be determined
    from the file extension and no explicit type is provided.
    """
    component_type = "Test case without converter"
    enabled: bool = data.get('enabled', True)

    if 'path' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'path' field.")
    
    raw_path: Optional[str] = data.get('path')
    tc_type: str = data.get('type', "UNKNOWN")
    if raw_path is None:
        raise ValueError("Missing path in config")
    path_to_tc: str = _get_validated_path(
        name=name, raw_path=raw_path, component_type=component_type, enabled=enabled, is_exec=False
    )
    test_case: TestCase = TestCase(
        name=name,
        path=str(path_to_tc),
        tc_type=tc_type,
        enabled=enabled
    )
    if not test_case.tc_type or test_case.tc_type.strip() == "" or test_case.tc_type.upper() == "UNKNOWN":
        raise ValueError(
            f"{component_type} '{name}' has an unknown type and no 'type' field specified. "
            "Please specify the type explicitly in the config or ensure the file extension is recognized."
        )
    _validate_type_field(name, test_case.tc_type, component_type)
    return test_case

def _parse_without_converter(data: dict[str, Any]) -> list[TestCase]:
    """Parses all pre-encoded file entries from the config dict."""
    return [_parse_single_without_converter(k, v) for k, v in data.items()]

def _lookup(name: Optional[str], registry: dict[str, Any], section: str) -> Optional[Any]:
    """Looks up *name* in *registry*. Returns None if *name* is not set.
    Raises ValueError if *name* is set but not found in *registry*."""
    if not name:
        return None
    if name not in registry:
        raise ValueError(f"Triplet references {section} '{name}' which does not exist in config.")
    return registry[name]

def _parse_triplets(
    triplets: list[dict[str, Any]],
    files: dict[str, list[FileConfig]],
    formulators: dict[str, FormulatorConfig],
    solvers: dict[str, ExecConfig],
    breakers: dict[str, ExecConfig],
    without_converter: dict[str, TestCase],
) -> list[ExecutionTriplet]:
    """
    Resolves named triplet entries to their full config objects.

    Each triplet must define either a (problem, formulator) pair or a
    without_converter entry, but not both. The *solver* field is optional —
    if omitted, the triplet is expanded to all compatible solvers later by
    the solver manager.

    Raises ValueError on invalid combinations.
    """
    all_triplets: list[ExecutionTriplet] = []
    
    for t in triplets:
        problem_name = t.get('problem')
        formulator_name = t.get('formulator')
        solver_name = t.get('solver')
        breaker_name = t.get('breaker')
        tc_name = t.get('without_converter')

        problem_cfgs: Optional[list[FileConfig]] = _lookup(problem_name, files, 'files')
        formulator_cfg: Optional[FormulatorConfig] = _lookup(formulator_name, formulators, 'formulators')
        solver_cfg: Optional[ExecConfig] = _lookup(solver_name, solvers, 'solvers')
        breaker_cfg: Optional[ExecConfig] = _lookup(breaker_name, breakers, 'breakers')
        test_case_cfg: Optional[TestCase] = _lookup(tc_name, without_converter, 'without_converter')

        if formulator_cfg and not formulator_cfg.enabled:
            raise ValueError(
                f"Configuration Error: Triplet uses formulator '{formulator_cfg.name}', which is disabled."
            )
            
        if solver_cfg and not solver_cfg.enabled:
            raise ValueError(f"Configuration Error: Triplet uses solver '{solver_cfg.name}', which is disabled.")

        if test_case_cfg and not test_case_cfg.enabled:
             raise ValueError(f"Configuration Error: Triplet uses test case '{test_case_cfg.name}', which is disabled.")
        
        if breaker_cfg and not breaker_cfg.enabled:
             raise ValueError(f"Configuration Error: Triplet uses test case '{breaker_cfg.name}', which is disabled.")

        if test_case_cfg:
            if (problem_cfgs is not None or formulator_cfg is not None):
                raise ValueError(
                    f"Error: Triplet with test case {test_case_cfg.name} also has problem and formulator "
                    "defined. Please choose either test_case or problem/formulator, not both."
                )
        else:
            if not problem_cfgs and not formulator_cfg:
                raise ValueError("Error: Triplet must define either (problem + formulator) or without_converter.")
            if (problem_cfgs and not formulator_cfg):
                raise ValueError(f"Error: Triplet with problem name: {problem_name} has no formulator.")
            if (not problem_cfgs and formulator_cfg):
                raise ValueError(f"Error: Triplet with formulator name: {formulator_cfg.name} has no problem.")

        if test_case_cfg:
            all_triplets.append(ExecutionTriplet(
                problem=None,
                formulator=formulator_cfg,
                solver=solver_cfg,
                breaker=breaker_cfg,
                test_case=test_case_cfg
            ))
        elif problem_cfgs:
            for problem_cfg in problem_cfgs:
                params_list: list[dict[str, Any]] = (
                    problem_cfg.parameters if problem_cfg.parameters else [{}]
                )
                for params in params_list:
                    all_triplets.append(ExecutionTriplet(
                        problem=problem_cfg,
                        formulator=formulator_cfg,
                        solver=solver_cfg,
                        breaker=breaker_cfg,
                        test_case=None,
                        parameters=dict(params),
                    ))
    return all_triplets

def _validate_max_threads(max_threads: int) -> int:
    """
    Validates *max_threads* is positive and caps it at max(1, cpu_count - 1).

    If *max_threads* is 0 or less, returns the system default cap. 
    Prints a warning if the configured value exceeds the cap.
    """
    cpu_cores: int = os.cpu_count() or 1
    cap: int = max(1, cpu_cores - 1)

    if max_threads <= 0:
        return cap
    if max_threads > cap:
        logger.warning(
            "Configured max_threads %d exceeds logical CPU count %d. Using %d instead.", max_threads, cpu_cores, cap
        )
        return cap
    return max_threads


def _validate_poll_interval(value: Any) -> float:
    """
    Validates the GlobalMonitor sampling interval (seconds). Must be a positive
    number. Warns for values likely to be impractical: a very small interval
    drives high /proc read overhead, while a large one risks missing
    short-lived memory spikes between samples.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"monitor_poll_interval must be a positive number of seconds, got {value!r}")
    interval = float(value)
    if interval < 0.05:
        logger.warning("monitor_poll_interval %gs is very small; expect high /proc read overhead.", interval)
    elif interval > 5.0:
        logger.warning("monitor_poll_interval %gs is large; short-lived memory spikes may be missed.", interval)
    return interval


def _validate_threading(data: dict[str, Any]) -> ThreadConfig:
    """
    Parses and validates ThreadConfig.

    When allowed_cores is set, max_threads is capped at len(allowed_cores)
    (one worker per pinned core). When allowed_cores is null, max_threads is
    used as configured with no cap; a value of 0 or less falls back to the
    system N-1 default. monitor_poll_interval defaults to 0.5 s.
    """
    requested_max_threads: int = data.get("max_threads", 0)
    allowed_cores: Optional[list[int]] = data.get("allowed_cores")
    ensure_cleanup_on_crash: bool = data.get("ensure_cleanup_on_crash", False)
    monitor_poll_interval: float = _validate_poll_interval(data.get("monitor_poll_interval", 0.5))

    max_threads: int = 0
    if allowed_cores:
        worker_capacity: int = len(allowed_cores)
        if requested_max_threads <= 0:
            max_threads = worker_capacity
        elif requested_max_threads > worker_capacity:
            logger.warning(
                "Requested max_threads %d exceeds allowed_cores count %d. Capping.",
                requested_max_threads, worker_capacity
            )
            max_threads = worker_capacity
        else:
            max_threads = requested_max_threads
    else:
        if requested_max_threads <= 0:
            max_threads = _validate_max_threads(max_threads=0)
        else:
            cpu_cores: int = os.cpu_count() or 1
            if requested_max_threads > cpu_cores:
                logger.warning(
                    "Requested max_threads %d exceeds logical CPU count %d; running oversubscribed.",
                    requested_max_threads, cpu_cores
                )
            max_threads = requested_max_threads

    return ThreadConfig(
        max_threads=max_threads,
        allowed_cores=allowed_cores,
        ensure_cleanup_on_crash=ensure_cleanup_on_crash,
        monitor_poll_interval=monitor_poll_interval,
    )

def _validate_working_dir(working_dir: str, confirm_delete: bool) -> Path:
    """
    Validates the working directory path and returns it as a resolved Path.

    Raises ValueError if the path exists but is not a directory or is non-empty
    and *confirm_delete* is False. Raises PermissionError if not writable.
    """
    path: Path = Path(working_dir).resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"Config 'working_dir' path exists but is not a directory: {path}")
    if path.exists() and not os.access(path=path, mode=os.W_OK):
        raise PermissionError(f"Cannot write to working directory: {path}")
    if path.exists() and not confirm_delete and any(path.iterdir()):
        raise ValueError(
            f"Working directory {path} is not empty. To prevent accidental data loss, please specify "
            "an empty or new directory, or set 'delete_working_dir' to true to automatically clear it."
        )
    return path

def _validate_timeout(timeout: int) -> int:
    """Raises ValueError if *timeout* is negative."""
    if timeout < 0:
        raise ValueError("Config 'timeout' must be a non-negative integer.")
    return timeout

def _flatten_metrics_measured(raw: dict[str, Any]) -> dict[str, bool]:
    """Flattens a (possibly grouped) metrics_measured dict into a flat name -> bool map.

    Nested dict values (one level deep) are unwrapped and their entries are merged
    into the result. Used so that config.json can group SAT-specific and
    ILP-specific metrics for readability while internal code stays flat.

    Raises ValueError if a flattened name collides with another entry.
    """
    flat: dict[str, bool] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key in flat:
                    raise ValueError(f"Duplicate metric name '{sub_key}' after flattening 'metrics_measured.{key}'.")
                flat[sub_key] = bool(sub_value)
        else:
            if key in flat:
                raise ValueError(f"Duplicate metric name '{key}' in 'metrics_measured'.")
            flat[key] = bool(value)
    return flat


def _validate_data(data: dict[str, Any]) -> None:
    """Validates the top-level structure of the raw config dict, checking required
    sections are present and have the correct types."""
    if 'solvers' not in data:
        raise ValueError("Config is missing required 'solvers' section.")
    if not data.get('solvers'):
        raise ValueError("The 'solvers' section is empty. You need at least one solver enabled.")
    if data.get('solvers') and not isinstance(data['solvers'], dict):
        raise ValueError("Config 'solvers' must be a dictionary mapping solver names to their configurations.")
    
    if 'metrics_measured' in data:
        mm = data['metrics_measured']
        if not isinstance(mm, dict):
            raise ValueError(
                "Config 'metrics_measured' must be a dictionary mapping metric names to boolean values, "
                "optionally with nested group dicts."
            )
        for key, value in mm.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if not isinstance(sub_value, bool):
                        raise ValueError(f"Config 'metrics_measured.{key}.{sub_key}' must be a boolean.")
            elif not isinstance(value, bool):
                raise ValueError(f"Config 'metrics_measured.{key}' must be a boolean or a dict of booleans.")
    
    if 'files' in data and not isinstance(data['files'], dict):
        raise ValueError("Config 'files' must be a dictionary mapping file names to their configurations.")
    
    if 'formulators' in data and not isinstance(data['formulators'], dict): 
        raise ValueError("Config 'formulators' must be a dictionary mapping formulator names to their configurations.")
    if 'breakers' in data and not isinstance(data['breakers'], dict):
        raise ValueError("Config 'breakers' must be a dictionary mapping breaker names to their configurations.")
    
    if 'triplets' in data and not isinstance(data['triplets'], list):
        raise ValueError("Config 'triplets' must be a list of objects.")
    if 'without_converter' in data and not isinstance(data['without_converter'], dict):
        raise ValueError(
            "Config 'without_converter' must be a dictionary mapping test case names to their configurations."
        )
    if data.get('triplet_mode', False) and 'triplets' not in data:
        raise ValueError("Triplet_mode set to True but is missing required 'triplets' section.")
    
    seen_names: dict[str, str] = {}
    for section in ('files', 'formulators', 'solvers', 'breakers', 'without_converter'):
        for name in data.get(section, {}):
            if name in seen_names:
                raise ValueError(
                    f"Duplicate name '{name}' found in '{section}' and '{seen_names[name]}'. "
                    "All component names must be unique across the config."
                )
            seen_names[name] = section


def _validate_result_paths(data: dict[str, Any]) -> None:
    """All four result output paths are required — there are no defaults so a
    misconfigured run cannot silently dump results in an unexpected location."""
    for required in ('results_csv', 'results_json', 'results_jsonl', 'results_html'):
        if required not in data:
            raise ValueError(f"Config is missing required '{required}' field.")
        if not isinstance(data[required], str) or not data[required].strip():
            raise ValueError(f"Config '{required}' must be a non-empty string path.")
    
def _check_thread_limits(solvers: list[ExecConfig], breakers: list[ExecConfig], thread_cfg: ThreadConfig) -> None:
    """
    Ensures no single solver or breaker requests more threads than are 
    available in the physical core pool.
    """
    capacity: int = 0
    capacity = len(thread_cfg.allowed_cores) if thread_cfg.allowed_cores else thread_cfg.max_threads 

    for component in solvers + breakers:
        if component.enabled and component.threads > capacity:
            raise ValueError(
                f"Resource Error: '{component.name}' requests {component.threads} threads, "
                f"but the configuration only allows a maximum of {capacity} cores. "
                "Decrease solver threads or increase allowed_cores to ensure clean benchmarks."
            )

def load_config(config_path: Path) -> Config:
    """
    Loads, validates, and parses the JSON config file at *config_path* into a
    fully typed Config object. Sets the base directory for relative path resolution
    to the config file's parent directory. Also ensures result output directories
    are writable.

    Raises FileNotFoundError if the config file does not exist.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    set_base_dir(config_path.resolve().parent)
    
    with config_path.open() as f:
        data = json.load(f)
    _validate_data(data)
    _validate_result_paths(data)

    _ensure_results_directory(path_str=_resolve_path(data['results_csv']))
    _ensure_results_directory(path_str=_resolve_path(data['results_json']))
    _ensure_results_directory(path_str=_resolve_path(data['results_jsonl']))
    _ensure_results_directory(path_str=_resolve_path(data['results_html']))
    _ensure_results_directory(
        path_str=_resolve_path(data.get('visualization', {}).get('output_dir', './results/plots'))
    )

    solvers: list[ExecConfig] = _parse_exec_config(data=data.get('solvers', {}))
    formulators: list[FormulatorConfig] = _parse_formulator_config(data=data.get('formulators', {}))
    files: list[FileConfig] = []
    breakers: list[ExecConfig] = _parse_exec_config(data=data.get('breakers', {}))
    without_converter: list[TestCase] = _parse_without_converter(data=data.get('without_converter', {}))

    thread_config: ThreadConfig = _validate_threading(data.get('threading', {}))
    _check_thread_limits(solvers=solvers, breakers=breakers, thread_cfg=thread_config)

    # Build name -> object lookups for triplet resolution
    formulators_by_name = {f.name: f for f in formulators}
    solvers_by_name = {s.name: s for s in solvers}
    breakers_by_name = {b.name: b for b in breakers}
    wc_by_name = {tc.name: tc for tc in without_converter}
    files_by_name: dict[str, list[FileConfig]] = {}
    for key, val in data.get('files', {}).items():
        parsed: list[FileConfig] = _parse_single_file_config(key, val)
        files.extend(parsed)
        files_by_name[key] = parsed

    triplet_mode: bool = data.get('triplet_mode', False)
    triplets: list[ExecutionTriplet] = []
    if triplet_mode:
        triplets= _parse_triplets(
            triplets=data.get('triplets', []),
            files=files_by_name,
            formulators=formulators_by_name,
            solvers=solvers_by_name,
            breakers=breakers_by_name,
            without_converter=wc_by_name,
        )

    return Config(
        metrics_measured=_flatten_metrics_measured(data.get('metrics_measured', {})),
        solvers=solvers,
        formulators=formulators,
        files=files,
        without_converter=without_converter,
        triplets=triplets,
        timeout=_validate_timeout(timeout=data.get('timeout', 5)),
        thread_config=thread_config,
        breakers=breakers,
        triplet_mode=triplet_mode,
        working_dir=_validate_working_dir(
            working_dir=_resolve_path(data.get('working_dir', '/tmp/solver_comparison')),
            confirm_delete=data.get('delete_working_dir', False),
        ),
        delete_working_dir=data.get('delete_working_dir', False),
        use_hardlink=data.get('use_hardlink', False),
        results_csv=_resolve_path(data['results_csv']),
        results_json=_resolve_path(data['results_json']),
        results_jsonl=_resolve_path(data['results_jsonl']),
        results_html=_resolve_path(data['results_html']),
        visualization=VisualizationConfig(
            enabled=data.get('visualization', {}).get('enabled', False),
            output_dir=_resolve_path(data.get('visualization', {}).get('output_dir', './results/plots')),
            per_problem=data.get('visualization', {}).get('per_problem', True),
            comparison=data.get('visualization', {}).get('comparison', True),
        )
    )
