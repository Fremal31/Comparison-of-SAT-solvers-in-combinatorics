from pathlib import Path
import os
import json
from dataclasses import dataclass
from typing import List, Dict, Optional
from .SolverManager import MultiSolverManager
from .ConverterRunner import *
from .SolverRunner import SolverConfig, TestCase


@dataclass
class G6Config:
    use_temp: bool
    path_to_g6: str
    path_to_converters: List[Dict[str, str]]


@dataclass
class SymmetryBreakingConfig:
    enabled: bool
    breaker_path: str
    use_temp_files: bool


@dataclass
class Config:
    metrics_measured: Dict[str, bool]
    solvers: List[Dict[str, str]]
    g6: G6Config
    without_converter: List[TestCase]
    timeout: int
    max_threads: int
    symmetry_breaking: SymmetryBreakingConfig
    results_csv: str


def _parse_g6_config(data: Dict) -> G6Config:
    """Parse G6 configuration from dictionary"""
    return G6Config(
        use_temp=data.get('use_temp', True),
        path_to_g6=data['path_to_g6'],
        path_to_converters=data.get('path_to_converters', [])
    )


def _parse_without_converter(data: List[Dict]) -> List[TestCase]:
    """Parse test cases from list of dictionaries"""
    return [TestCase(name=tc['name'], path=tc['path']) for tc in data]


def _parse_symmetry_breaking(data: Dict) -> SymmetryBreakingConfig:
    """Parse symmetry breaking configuration from dictionary"""
    return SymmetryBreakingConfig(
        enabled=data.get('enabled', False),
        breaker_path=data.get('breaker_path', ''),
        use_temp_files=data.get('use_temp_files', False)
    )


def load_config(config_path: Path) -> Config:
    """Load and validate configuration from JSON file into dataclass"""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with config_path.open() as f:
        data = json.load(f)
    
    required = ['solvers', 'without_converter', 'timeout', 'max_threads']
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required config field: {field}")
    
    config = Config(
        metrics_measured=data.get('metrics_measured', {}),
        solvers=data['solvers'],
        g6=_parse_g6_config(data.get('g6', {})),
        without_converter=_parse_without_converter(data.get('without_converter', [])),
        timeout=data['timeout'],
        max_threads=data['max_threads'],
        symmetry_breaking=_parse_symmetry_breaking(data.get('symmetry_breaking', {})),
        results_csv=data.get('results_csv', './results/results.csv')
    )
    
    return config

def main():
    config = load_config(Path("./src/config.json"))

    converter = Converter(
        Path(config.g6.path_to_converters[0]['path']),
        Path(config.g6.path_to_g6),
        config.g6.use_temp
    )
    cnf_files: List[TestCase] = converter.convert_all()
   
    for file in config.without_converter:
        cnf_files.append(TestCase(name=file.name, path=file.path))

    solver_configs = []
    for s in config.solvers:
        if s.get('enabled', True):
            if isinstance(s, dict):
                solver_configs.append(SolverConfig(name=s['name'], path=Path(s['path']), options=s.get('options', []), enabled=True))
            else:
                solver_configs.append(s)
    
    logical_cpus = os.cpu_count()
    if (config.max_threads > logical_cpus):
        print(f"Warning: Configured max_threads {config.max_threads} exceeds logical CPU count {logical_cpus}. Using {logical_cpus} instead.")
        config.max_threads = logical_cpus

    manager = MultiSolverManager(
        solvers=solver_configs,
        cnf_files=cnf_files,
        timeout=config.timeout,
        maxthreads=config.max_threads
    )

    if config.symmetry_breaking.enabled:
        manager.set_symmetry_breaker(
            break_symmetry=True,
            symmetry_breaker_path=config.symmetry_breaking.breaker_path,
            use_temp_files=config.symmetry_breaking.use_temp_files
        )
    
    results = manager.run_all()
    
    fieldnames = []
    for metric, enabled in config.metrics_measured.items():
        if enabled:
            fieldnames.append(metric)
    
    manager.log_results(results, fieldnames, config.results_csv)


if __name__ == "__main__":
    main()