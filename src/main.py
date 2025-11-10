from pathlib import Path
import json
from SolverManager import *
from GraphToCNF import *

def load_config(config_path: Path):
    """Load and validate configuration"""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with config_path.open() as f:
        config = json.load(f)
        
    required = ['solvers', 'test_cases']
    for field in required:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")
    
    return config

def main():
    config = load_config(Path("./src/config.json"))

    converter_config = config.get('g6')
    converter = Converter(
        Path(converter_config.get('path_to_converters')[0].get('path')),
        Path(converter_config.get('path_to_g6')),
        converter_config.get('use_temp', True)
        )
    cnf_files = converter.run_converter()
    
    manager = MultiSolverManager(
        solvers=config['solvers'],
        cnf_files=cnf_files,
        timeout=config.get('timeout'),
        maxthreads=config.get('max_threads', 1)
    )
    
    if config.get('symmetry_breaking', {}).get('enabled', False):
        sb_config = config['symmetry_breaking']
        manager.set_symmetry_breaker(
            break_symmetry=True,
            symmetry_breaker_path=sb_config['breaker_path'],
            use_temp_files=sb_config.get('use_temp_files', False)
        )
    
    results = manager.run_all()
    metrics = config.get('metrics_measured')
    fieldnames = []
    for metric, enabled in metrics.items():
        if enabled:
            fieldnames.append(metric)
    manager.log_results(results, fieldnames, config.get('results_csv'))
    

if __name__ == "__main__":
    main()