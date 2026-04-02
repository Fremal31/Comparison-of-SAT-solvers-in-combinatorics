import pathlib
from pathlib import Path
import json
import os
import sys
import shutil
from typing import List, Dict, Any, Optional

from metadata_registry import resolve_format_metadata, FormatMetadata
from parser_strategy import get_parser
from solver_manager import MultiSolverManager
from custom_types import *



BASE_DIR = pathlib.Path(__file__).parent.resolve()
DEFAULT_CONFIG_PATH = BASE_DIR /".." / "example_config.json"



def _ensure_results_directory(csv_path: str):
    path = Path(csv_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"Cannot write to result file: {path}")

def _validate_name_and_paths(name: str, cmd: str, string: str) -> Path:
    if name.lower() == "none":
        raise ValueError(f"{string} name cannot be '{name}' as it is reserved for test cases without a formulator. Please choose a different name for the formulator.")
    if cmd is None or cmd.strip() == "":
        raise ValueError(f"{string} config '{name}' has an empty 'cmd' field, which is not valid.")
    if shutil.which(cmd):
        return cmd  # system command found in PATH, return as is
    path_obj = Path(cmd)
    if not path_obj.is_absolute():
        path_obj = (BASE_DIR.parent / path_obj).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"Config '{name}' points to non-existent: {path_obj}")
    
    if string in ["Solver/Breaker", "Formulator"]:
        if not path_obj.is_file():
            raise ValueError(f"{string} '{name}' path is a directory, but needs to be an executable file.")
        if not os.access(path_obj, os.X_OK):
            raise PermissionError(f"{string} '{name}' at {path_obj} is not executable. Run 'chmod +x'.")
    
    return path_obj
                         
def _validate_type_field(name: str, type_value: str, string: str) -> None:
    if type_value is None or type_value.strip() == "":
        raise ValueError(f"{string} config '{name}' has an empty 'type' field, which is not valid.")
    if type_value == "UNKNOWN":
        raise ValueError(f"{string} config '{name}' has 'type' field set to 'UNKNOWN', which is not valid. Please specify a valid type for the {string.lower()}.")
    if resolve_format_metadata(type_value).format_type == "UNKNOWN":
        raise ValueError(f"{string} config '{name}' has unrecognized 'type' field value '{type_value}'. Valid types are: {[t for t in FORMAT_REGISTRY]}.")

def _parse_single_formulator_config(name: str, data: Dict) -> FormulatorConfig:
    string = "Formulator"
    if 'cmd' not in data:
        raise ValueError(f"{string} config '{name}' is missing required 'cmd' field.")
    path_to_formulator = _validate_name_and_paths(name, data.get('cmd', ''), string=string)
    if 'type' not in data:
        raise ValueError(f"{string} config '{name}' is missing required 'type' field.")
    _validate_type_field(name, data.get('type', ''), string=string)
    return FormulatorConfig(
        name=name,
        formulator_type=data.get('type', "UNKNOWN"),
        cmd=path_to_formulator,
        enabled=data.get('enabled', False),
        options=data.get('options', []),
        output_mode=data.get('output_mode', "stdout"),
        output_param=data.get('output_param', None)
    )

def _parse_formulator_config(data: Dict) -> List[FormulatorConfig]:
    return [_parse_single_formulator_config(k, v) for k, v in data.items()]

def _parse_single_exec_config(name: str, data: Dict) -> ExecConfig:
    string = "Solver/Breaker"
    if 'cmd' not in data:
        raise ValueError(f"{string} config '{name}' is missing required 'cmd' field.")
    path_to_solver = _validate_name_and_paths(name, data.get('cmd', ''), string=string)

    if 'type' not in data:
        raise ValueError(f"{string} config '{name}' is missing required 'type' field.")
    _validate_type_field(name, data.get('type', ''), string=string)

    if data.get('output_param') is not None and (data['output_param'].lower() == "none"):
        raise ValueError(f"{string} config '{name}' has an invalid 'output_param' field. If you do not want to specify an output parameter, please omit the 'output_param' field or set it to null.")
    
    explicit_parser_key: Optional[str] = data.get('parser')
    if explicit_parser_key:
        parser_instance = get_parser(explicit_parser_key)
    else:
        metadata = resolve_format_metadata(format_type=data.get('type'))
        parser_instance = metadata.parser_class if metadata.parser_class else GenericParser()
    return ExecConfig(
        name=name,
        solver_type=resolve_format_metadata(format_type=data.get('type')).format_type,
        cmd=path_to_solver,
        options=data.get('options', []),
        enabled=data.get('enabled', False),
        output_param=data.get('output_param', None),
        parser=parser_instance
    )

def _parse_exec_config(data: Dict) -> List[ExecConfig]:
    return [_parse_single_exec_config(k, v) for k, v in data.items()]

def _parse_single_file_config(name: str, data: Dict) -> FileConfig:
    string = "File"
    if 'path' not in data:
        raise ValueError(f"{string} config '{name}' is missing required 'path' field.")
    path_to_problem = _validate_name_and_paths(name, data.get('path', ''), string=string)
    return FileConfig(
        name=name,
        path=path_to_problem,
        enabled=data.get('enabled', True)
    )

def _parse_file_config(data: Dict) -> List[FileConfig]:
    return [_parse_single_file_config(k, v) for k, v in data.items()]

def _parse_single_without_converter(name: str, data: Dict) -> TestCase:
    string = "Test case without converter"
    if 'path' not in data:
        raise ValueError(f"{string} config '{name}' is missing required 'path' field.")
    path_to_tc = _validate_name_and_paths(name, data.get('path', ''), "File without converter")
    resolved_type = data.get('type')
    test_case: TestCase = TestCase(
        name=name,
        path=path_to_tc,
        tc_type=resolved_type,
        enabled=data.get('enabled', True)
    )
    if not test_case.tc_type or test_case.tc_type.strip() == "" or test_case.tc_type.upper() == "UNKNOWN":
        #metadata: FormatMetadata = resolve_format_metadata(path=data['path'])
        #resolved_type: str = metadata.format_type
        #if resolved_type == "UNKNOWN":
        raise ValueError(f"{string} '{name}' has an unknown type and no 'type' field specified. Please specify the type explicitly in the config or ensure the file extension is recognized.")
    return test_case

def _parse_without_converter(data: Dict) -> List[TestCase]:
    return [_parse_single_without_converter(k, v) for k, v in data.items()]

def _parse_triplets(triplets: List[Dict], full_config: Dict) -> List[ExecutionTriplet]:
    """
    Look up the full config objects based on the names provided in the triplets.
    """
    all_triplets: List[ExecutionTriplet] = []
    
    for t in triplets:
        problem_name = t.get('problem')
        formulator_name = t.get('formulator')
        solver_name = t.get('solver')
        breaker_name = t.get('breaker')
        tc_name = t.get('without_converter')

        def get_cfg(section, name, parser_func) -> Optional[Any]:
            if not name: return None
            if name not in full_config.get(section, {}):
                raise ValueError(f"Triplet references {section} '{name}' which does not exist in config.")
            cfg = parser_func(name, full_config[section][name])
            return cfg

        problem_cfg: Optional[FileConfig] = get_cfg('files', problem_name, _parse_single_file_config)
        formulator_cfg: Optional[FormulatorConfig] = get_cfg('formulators', formulator_name, _parse_single_formulator_config)
        solver_cfg: Optional[ExecConfig] = get_cfg('solvers', solver_name, _parse_single_exec_config)
        breaker_cfg: Optional[ExecConfig] = get_cfg('breakers', breaker_name, _parse_single_exec_config)
        test_case_cfg: Optional[TestCase] = get_cfg('without_converter', tc_name, _parse_single_without_converter)

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
    if max_threads <= 0:
        raise ValueError("Config 'max_threads' must be a positive integer.")
    cpu_cores = os.cpu_count() or 1
    if max_threads >= cpu_cores:
        print(f"Warning: Configured max_threads {max_threads} exceeds logical CPU count {cpu_cores}. Using {cpu_cores -1 } instead.")
        return cpu_cores - 1
    return max_threads

def _validate_working_dir(working_dir: str, confirm_delete: bool) -> Path:
    path = Path(working_dir).resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"Config 'working_dir' path exists but is not a directory: {path}")
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise PermissionError(f"Cannot create working directory at {path}: {str(e)}")
    if path.exists() and not os.access(path, os.W_OK):
        raise PermissionError(f"Cannot write to working directory: {path}")
    if path.exists() and not confirm_delete and any(path.iterdir()):
        raise ValueError(f"Working directory {path} is not empty. To prevent accidental data loss, please specify an empty or new directory, or set 'delete_working_dir' to true to automatically clear it.")
    return path

def _validate_timeout(timeout: int) -> int:
    if timeout < 0:
        raise ValueError("Config 'timeout' must be a non-negative integer.")
    return timeout

def _validate_data(data: Dict[str, Any]) -> None:
    if 'solvers' not in data:
        raise ValueError("Config is missing required 'solvers' section.")
    if not data.get('solvers'):
        raise ValueError("The 'solvers' section is empty. You need at least one solver enabled.")
    
    if 'metrics_measured' in data and not isinstance(data['metrics_measured'], dict):
        raise ValueError("Config 'metrics_measured' must be a dictionary mapping metric names to boolean values.")
    
    if 'files' in data and not isinstance(data['files'], dict):
        raise ValueError("Config 'files' must be a dictionary mapping file names to their configurations.")
    
    if 'formulators' in data and not isinstance(data['formulators'], dict): 
        raise ValueError("Config 'formulators' must be a dictionary mapping formulator names to their configurations.")
    if 'solvers' in data and not isinstance(data['solvers'], dict):
        raise ValueError("Config 'solvers' must be a dictionary mapping solver names to their configurations.")
    
    if 'breakers' in data and not isinstance(data['breakers'], dict):
        raise ValueError("Config 'breakers' must be a dictionary mapping breaker names to their configurations.")
    
    if 'triplets' in data and not isinstance(data['triplets'], list):
        raise ValueError("Config 'triplets' must be a list of objects.")
    if data.get('triplet_mode', False) == True and 'triplets' not in data:
        raise ValueError("Triplet_mode set to True but is missing required 'triplets' section.")
    


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with config_path.open() as f:
        data = json.load(f)
    _validate_data(data)
  
    _ensure_results_directory(data.get('results_csv', './results/results.csv'))

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
        working_dir=_validate_working_dir(data.get('working_dir', '/tmp/solver_comparison')),
        delete_working_dir=data.get('delete_working_dir', False),
        results_csv=data.get('results_csv', './results/results.csv')
    )

def main():
    config = load_config(DEFAULT_CONFIG_PATH)

    manager = MultiSolverManager(config=config)

    results: List[Results] = []

    try:
        results = manager.run_all_experiments_parallel_separate()
    except KeyboardInterrupt:
        print("Experiment execution interrupted by user. Ending all processes and saving data", file=sys.stderr)
    except Exception as e:
        print(f"Error during experiment execution: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        pass
    finally:   
        print(f"Saving {len(manager.results)} results to {config.results_csv}...")

        fieldnames = [metric for metric, enabled in config.metrics_measured.items() if enabled]
        print(f"DEBUG: Fields being written: {fieldnames}")
        manager.log_results(manager.results, fieldnames, config.results_csv)
        print(f"Results saved to {config.results_csv}")
    
if __name__ == "__main__":
    main()