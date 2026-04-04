from pathlib import Path
import json
import os
import sys
import shutil
import traceback
from typing import List, Dict, Any, Optional, Union

from metadata_registry import resolve_format_metadata, FORMAT_REGISTRY
from graph import log_results_to_csv, log_results_to_json, generate_plots
from solver_manager import MultiSolverManager
from custom_types import (
    Config, ExecConfig, FormulatorConfig, FileConfig, TestCase,
    ExecutionTriplet, VisualizationConfig
)



BASE_DIR = Path(__file__).parent.resolve()  # src/ directory; used as base for resolving relative config paths
# DEFAULT_CONFIG_PATH = BASE_DIR.parent / "example_config.json"
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"  # change this to point to a different config file



def _ensure_results_directory(path_str: str) -> None:
    """Creates parent directories for *path* and checks it is writable if it already exists.

    Raises PermissionError if the path exists but is not writable.
    """
    path = Path(path_str).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"Cannot write to result file: {path}")

def _validate_name_and_paths(name: str, cmd: str, component_type: str, check_executable: bool = False) -> Union[str, Path]:
    """
    Validates *name* is not reserved and resolves *cmd* to an executable path.

    Returns the system command as-is if found on PATH, otherwise resolves it
    relative to the project root. When *check_executable* is True, also verifies
    the path is a file and has execute permission.

    Raises ValueError, FileNotFoundError, or PermissionError on invalid input.
    """
    if name.lower() == "none":
        raise ValueError(f"{component_type} name cannot be '{name}' as it is reserved for test cases without a formulator. Please choose a different name for the formulator.")
    if cmd is None or cmd.strip() == "":
        raise ValueError(f"{component_type} config '{name}' has an empty 'cmd' field, which is not valid.")
    if shutil.which(cmd):
        return cmd  # system command found in PATH, return as is
    path_obj = Path(cmd)
    if not path_obj.is_absolute():
        path_obj = (BASE_DIR.parent / path_obj).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"Config '{name}' points to non-existent: {path_obj}")
    
    if check_executable:
        if not path_obj.is_file():
            raise ValueError(f"{component_type} '{name}' path is a directory, but needs to be an executable file.")
        if not os.access(path_obj, os.X_OK):
            raise PermissionError(f"{component_type} '{name}' at {path_obj} is not executable. Run 'chmod +x'.")
    
    return path_obj
                         
def _validate_type_field(name: str, type_value: str, component_type: str) -> None:
    """Raises ValueError if *type_value* is empty, 'UNKNOWN', or not present in the format registry."""
    if type_value is None or type_value.strip() == "":
        raise ValueError(f"{component_type} config '{name}' has an empty 'type' field, which is not valid.")
    if type_value == "UNKNOWN":
        raise ValueError(f"{component_type} config '{name}' has 'type' field set to 'UNKNOWN', which is not valid. Please specify a valid type for the {component_type.lower()}.")
    if resolve_format_metadata(type_value).format_type == "UNKNOWN":
        raise ValueError(f"{component_type} config '{name}' has unrecognized 'type' field value '{type_value}'. Valid types are: {[t for t in FORMAT_REGISTRY]}.")
    
def _parse_single_formulator_config(name: str, data: Dict) -> FormulatorConfig:
    """Parses and validates a single formulator entry from the config dict.

    Raises ValueError if required fields are missing or invalid, FileNotFoundError
    if the cmd path does not exist, and PermissionError if it is not executable.
    """
    component_type = "Formulator"
    if 'cmd' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'cmd' field.")
    path_to_formulator = _validate_name_and_paths(name, data.get('cmd', ''), component_type=component_type, check_executable=True)
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

def _parse_formulator_config(data: Dict) -> List[FormulatorConfig]:
    """Parses all formulator entries from the config dict."""
    return [_parse_single_formulator_config(k, v) for k, v in data.items()]

def _parse_single_exec_config(name: str, data: Dict) -> ExecConfig:
    """Parses and validates a single solver or breaker entry from the config dict.

    Raises ValueError if required fields are missing or invalid, FileNotFoundError
    if the cmd path does not exist, and PermissionError if it is not executable.
    """
    component_type = "Solver/Breaker"
    if 'cmd' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'cmd' field.")
    path_to_solver = _validate_name_and_paths(name, data.get('cmd', ''), component_type=component_type, check_executable=True)

    if 'type' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'type' field.")
    _validate_type_field(name, data.get('type', ''), component_type=component_type)

    if data.get('output_param') is not None:
        print(f"Warning: '{name}' has 'output_param' set — this field is deprecated. Use '{{output}}' in options instead.")

    return ExecConfig(
        name=name,
        solver_type=resolve_format_metadata(format_type=data['type']).format_type,
        cmd=str(path_to_solver),
        options=data.get('options', []),
        enabled=data.get('enabled', False),
        parser=data.get('parser', None)
    )

def _parse_exec_config(data: Dict) -> List[ExecConfig]:
    """Parses all solver or breaker entries from the config dict."""
    return [_parse_single_exec_config(k, v) for k, v in data.items()]

def _parse_single_file_config(name: str, data: Dict) -> FileConfig:
    """Parses and validates a single problem file entry from the config dict.

    Raises ValueError if the path field is missing, FileNotFoundError if the
    path does not exist.
    """
    component_type = "File"
    if 'path' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'path' field.")
    path_to_problem = _validate_name_and_paths(name, data.get('path', ''), component_type=component_type)
    return FileConfig(
        name=name,
        path=str(path_to_problem),
        enabled=data.get('enabled', True)
    )

def _parse_file_config(data: Dict) -> List[FileConfig]:
    """Parses all problem file entries from the config dict."""
    return [_parse_single_file_config(k, v) for k, v in data.items()]

def _parse_single_without_converter(name: str, data: Dict) -> TestCase:
    """Parses and validates a single pre-encoded file entry from the config dict.

    Raises ValueError if the path field is missing or the type cannot be determined
    from the file extension and no explicit type is provided.
    """
    component_type = "Test case without converter"
    if 'path' not in data:
        raise ValueError(f"{component_type} config '{name}' is missing required 'path' field.")
    path_to_tc = _validate_name_and_paths(name, data.get('path', ''), component_type="File without converter")
    test_case: TestCase = TestCase(
        name=name,
        path=str(path_to_tc),
        tc_type=data.get('type'),
        enabled=data.get('enabled', True)
    )
    if not test_case.tc_type or test_case.tc_type.strip() == "" or test_case.tc_type.upper() == "UNKNOWN":
        raise ValueError(f"{component_type} '{name}' has an unknown type and no 'type' field specified. Please specify the type explicitly in the config or ensure the file extension is recognized.")
    return test_case

def _parse_without_converter(data: Dict) -> List[TestCase]:
    """Parses all pre-encoded file entries from the config dict."""
    return [_parse_single_without_converter(k, v) for k, v in data.items()]

def _get_triplet_cfg(section: str, name: Optional[str], parser_func: Any, full_config: Dict) -> Optional[Any]:
    """Looks up *name* in *section* of *full_config* and parses it with *parser_func*.
    Returns None if *name* is not set."""
    if not name: return None
    if name not in full_config.get(section, {}):
        raise ValueError(f"Triplet references {section} '{name}' which does not exist in config.")
    return parser_func(name, full_config[section][name])

def _parse_triplets(triplets: List[Dict], full_config: Dict) -> List[ExecutionTriplet]:
    """
    Resolves named triplet entries to their full config objects.

    Each triplet must define a solver and either a (problem, formulator) pair
    or a without_converter entry, but not both. Raises ValueError on invalid combinations.
    """
    all_triplets: List[ExecutionTriplet] = []
    
    for t in triplets:
        problem_name = t.get('problem')
        formulator_name = t.get('formulator')
        solver_name = t.get('solver')
        breaker_name = t.get('breaker')
        tc_name = t.get('without_converter')

        problem_cfg: Optional[FileConfig] = _get_triplet_cfg('files', problem_name, _parse_single_file_config, full_config)
        formulator_cfg: Optional[FormulatorConfig] = _get_triplet_cfg('formulators', formulator_name, _parse_single_formulator_config, full_config)
        solver_cfg: Optional[ExecConfig] = _get_triplet_cfg('solvers', solver_name, _parse_single_exec_config, full_config)
        breaker_cfg: Optional[ExecConfig] = _get_triplet_cfg('breakers', breaker_name, _parse_single_exec_config, full_config)
        test_case_cfg: Optional[TestCase] = _get_triplet_cfg('without_converter', tc_name, _parse_single_without_converter, full_config)

        if not solver_cfg:
            raise ValueError(f"Error: Triplet has no solver defined.")

        if test_case_cfg:
            if (problem_cfg is not None or formulator_cfg is not None):
                raise ValueError(f"Error: Triplet with test case {test_case_cfg.name} also has problem and formulator defined. Please choose either test_case or problem/formulator, not both.")
        else:
            if not problem_cfg and not formulator_cfg:
                raise ValueError(f"Error: Triplet with solver name: {solver_cfg.name} has no problem and formulator.")
            if (problem_cfg and not formulator_cfg):
                raise ValueError(f"Error: Triplet with problem name: {problem_cfg.name} has no formulator.")
            if (not problem_cfg and formulator_cfg):
                raise ValueError(f"Error: Triplet with formulator name: {formulator_cfg.name} has no problem.")

        all_triplets.append(ExecutionTriplet(
            problem=problem_cfg,
            formulator=formulator_cfg,
            solver=solver_cfg,
            breaker=breaker_cfg,
            test_case=test_case_cfg
        ))
    return all_triplets

def _validate_max_threads(max_threads: int) -> int:
    """
    Validates *max_threads* is positive and caps it at max(1, cpu_count - 1).

    Prints a warning if the configured value exceeds the cap.
    """
    if max_threads <= 0:
        raise ValueError("Config 'max_threads' must be a positive integer.")
    cpu_cores = os.cpu_count() or 1
    cap = max(1, cpu_cores - 1)
    if max_threads > cap:
        print(f"Warning: Configured max_threads {max_threads} exceeds logical CPU count {cpu_cores}. Using {cap} instead.")
        return cap
    return max_threads

def _validate_working_dir(working_dir: str, confirm_delete: bool) -> Path:
    """
    Validates the working directory path and returns it as a resolved Path.

    Raises ValueError if the path exists but is not a directory or is non-empty
    and *confirm_delete* is False. Raises PermissionError if not writable.
    """
    path = Path(working_dir).resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"Config 'working_dir' path exists but is not a directory: {path}")
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"Cannot write to working directory: {path}")
    if path.exists() and not confirm_delete and any(path.iterdir()):
        raise ValueError(f"Working directory {path} is not empty. To prevent accidental data loss, please specify an empty or new directory, or set 'delete_working_dir' to true to automatically clear it.")
    return path

def _validate_timeout(timeout: int) -> int:
    """Raises ValueError if *timeout* is negative."""
    if timeout < 0:
        raise ValueError("Config 'timeout' must be a non-negative integer.")
    return timeout

def _validate_data(data: Dict[str, Any]) -> None:
    """Validates the top-level structure of the raw config dict, checking required
    sections are present and have the correct types."""
    if 'solvers' not in data:
        raise ValueError("Config is missing required 'solvers' section.")
    if not data.get('solvers'):
        raise ValueError("The 'solvers' section is empty. You need at least one solver enabled.")
    if data.get('solvers') and not isinstance(data['solvers'], dict):
        raise ValueError("Config 'solvers' must be a dictionary mapping solver names to their configurations.")
    
    if 'metrics_measured' in data and not isinstance(data['metrics_measured'], dict):
        raise ValueError("Config 'metrics_measured' must be a dictionary mapping metric names to boolean values.")
    
    if 'files' in data and not isinstance(data['files'], dict):
        raise ValueError("Config 'files' must be a dictionary mapping file names to their configurations.")
    
    if 'formulators' in data and not isinstance(data['formulators'], dict): 
        raise ValueError("Config 'formulators' must be a dictionary mapping formulator names to their configurations.")
    if 'breakers' in data and not isinstance(data['breakers'], dict):
        raise ValueError("Config 'breakers' must be a dictionary mapping breaker names to their configurations.")
    
    if 'triplets' in data and not isinstance(data['triplets'], list):
        raise ValueError("Config 'triplets' must be a list of objects.")
    if 'without_converter' in data and not isinstance(data['without_converter'], dict):
        raise ValueError("Config 'without_converter' must be a dictionary mapping test case names to their configurations.")
    if data.get('triplet_mode', False) and 'triplets' not in data:
        raise ValueError("Triplet_mode set to True but is missing required 'triplets' section.")
    


def load_config(config_path: Path) -> Config:
    """
    Loads, validates, and parses the JSON config file at *config_path* into a
    fully typed Config object. Also ensures result output directories are writable.

    Raises FileNotFoundError if the config file does not exist.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with config_path.open() as f:
        data = json.load(f)
    _validate_data(data)
  
    _ensure_results_directory(data.get('results_csv', './results/results.csv'))
    _ensure_results_directory(data.get('results_json', './results/results.json'))
    _ensure_results_directory(data.get('visualization', {}).get('output_dir', './results/plots'))

    return Config(
        metrics_measured=data.get('metrics_measured', {}),
        solvers=_parse_exec_config(data.get('solvers', {})),
        formulators=_parse_formulator_config(data.get('formulators', {})),
        files=_parse_file_config(data.get('files', {})),
        without_converter=_parse_without_converter(data.get('without_converter', {})),
        triplets=_parse_triplets(data.get('triplets', []), data),
        timeout=_validate_timeout(timeout=data.get('timeout', 5)),
        max_threads=_validate_max_threads(data.get('max_threads', 1)),
        breakers=_parse_exec_config(data.get('breakers', {})),
        triplet_mode=data.get('triplet_mode', False),
        working_dir=_validate_working_dir(data.get('working_dir', '/tmp/solver_comparison'), data.get('delete_working_dir', False)),
        delete_working_dir=data.get('delete_working_dir', False),
        results_csv=data.get('results_csv', './results/results.csv'),
        results_json=data.get('results_json', './results/results.json'),
        visualization=VisualizationConfig(
            enabled=data.get('visualization', {}).get('enabled', False),
            output_dir=data.get('visualization', {}).get('output_dir', './results/plots')
        )
    )

def main() -> None:
    """
    Entry point. Loads config, runs the benchmark pipeline, and saves results
    to CSV and JSON. Generates plots if visualization is enabled. Exits with
    code 1 if an unhandled exception occurs during execution.
    """
    config = load_config(DEFAULT_CONFIG_PATH)

    manager = MultiSolverManager(config=config)

    had_error = False

    try:
        manager.run_all_experiments_parallel_separate()
    except KeyboardInterrupt:
        print("Experiment execution interrupted by user. Ending all processes and saving data", file=sys.stderr)
    except Exception as e:
        print(f"Error during experiment execution: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        had_error = True
    finally:   
        print(f"Saving {len(manager.results)} results to {config.results_csv}...")

        fieldnames = [metric for metric, enabled in config.metrics_measured.items() if enabled]
        log_results_to_csv(manager.results, fieldnames, config.results_csv)
        print(f"Results saved to {config.results_csv}")
        log_results_to_json(manager.results, config.results_json)
        print(f"Results saved to {config.results_json}")
        if config.visualization.enabled:
            generate_plots(manager.results, config.visualization.output_dir)
            print(f"Plots saved to {config.visualization.output_dir}")
    if had_error:
        sys.exit(1)

if __name__ == "__main__":
    main()