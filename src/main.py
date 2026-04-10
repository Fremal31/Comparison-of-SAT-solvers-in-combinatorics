from pathlib import Path
import argparse
import sys
import traceback

from config_loader import load_config
from graph import log_results_to_json, generate_plots, create_all_writers, validate_status
from solver_manager import MultiSolverManager


DEFAULT_CONFIG_PATH = Path(__file__).parent.resolve() / "config.json"


def parse_args() -> Path:
    """Parses CLI arguments and returns the resolved config file path."""
    parser = argparse.ArgumentParser(description="SAT/ILP solver benchmarking framework")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config JSON (default: {DEFAULT_CONFIG_PATH})"
    )
    return parser.parse_args().config


def main() -> None:
    """
    Entry point. Loads config, runs the benchmark pipeline, and saves results
    to CSV and JSON. Generates plots if visualization is enabled. Exits with
    code 1 if an unhandled exception occurs during execution.
    """
    config_path = parse_args()
    config = load_config(config_path)

    manager = MultiSolverManager(config=config)

    had_error = False
    fieldnames = [metric for metric, enabled in config.metrics_measured.items() if enabled]
    close_writers, append_result = create_all_writers(fieldnames, config.results_csv, config.results_jsonl)

    try:
        manager.run_all_experiments_parallel_separate(call_on_result=append_result)
    except KeyboardInterrupt:
        print("Experiment execution interrupted by user. Ending all processes and saving data", file=sys.stderr)
    except Exception as e:
        print(f"Error during experiment execution: {str(e)}", file=sys.stderr)
        traceback.print_exc()
        had_error = True
    finally:
        close_writers()
        print(f"Incremental results saved to {config.results_csv} and {config.results_jsonl} ({len(manager.results)} results)")

        log_results_to_json(manager.results, config.results_json)
        print(f"Structured JSON saved to {config.results_json}")

        conflicts = validate_status(manager.results)
        if conflicts:
            print(f"STATUS CONFLICT DETECTED ({len(conflicts)}):", file=sys.stderr)
            for c in conflicts:
                print(f"  {c}", file=sys.stderr)

        if config.visualization.enabled:
            generate_plots(manager.results, config.visualization.output_dir, timeout=config.timeout)
            print(f"Plots saved to {config.visualization.output_dir}")
    if had_error:
        sys.exit(1)

if __name__ == "__main__":
    main()
