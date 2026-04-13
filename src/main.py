from pathlib import Path
import argparse
import logging
import sys
import traceback
import time

from config_loader import load_config
from graph import log_results_to_json, generate_plots, create_all_writers, validate_status
from solver_manager import MultiSolverManager

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = Path(__file__).parent.resolve() / "config.json"


def parse_args() -> argparse.Namespace:
    """Parses CLI arguments and returns the namespace with config path and verbosity."""
    parser = argparse.ArgumentParser(description="SAT/ILP solver benchmarking framework")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config JSON (default: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose (DEBUG) logging"
    )
    return parser.parse_args()


def main() -> None:
    """
    Entry point. Loads config, runs the benchmark pipeline, and saves results
    to CSV and JSON. Generates plots if visualization is enabled. Exits with
    code 1 if an unhandled exception occurs during execution.
    """
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    config = load_config(args.config)

    manager = MultiSolverManager(config=config)

    had_error = False
    fieldnames = [metric for metric, enabled in config.metrics_measured.items() if enabled]
    close_writers, append_result = create_all_writers(fieldnames, config.results_csv, config.results_jsonl)

    start_time: float = time.perf_counter()
    try:
        manager.run_all_experiments_parallel_separate(call_on_result=append_result)
    except KeyboardInterrupt:
        logger.warning("Experiment execution interrupted by user. Ending all processes and saving data")
    except Exception as e:
        logger.error("Error during experiment execution: %s", e)
        logger.debug(traceback.format_exc())
        had_error = True
    finally:
        close_writers()
        logger.info("Incremental results saved to %s and %s (%d results)", config.results_csv, config.results_jsonl, len(manager.results))

        log_results_to_json(manager.results, config.results_json)
        logger.info("Structured JSON saved to %s", config.results_json)

        final_time: float = time.perf_counter() - start_time
        logger.info("Total time of experiment: %.2f seconds", final_time)

        conflicts = validate_status(manager.results)
        if conflicts:
            logger.error("STATUS CONFLICT DETECTED (%d):", len(conflicts))
            for c in conflicts:
                logger.error("  %s", c)

        if config.visualization.enabled:
            try:
                generate_plots(manager.results, config.visualization.output_dir, timeout=config.timeout)
                logger.info("Plots saved to %s", config.visualization.output_dir)
            except Exception as e:
                logger.error("Failed to generate plots: %s", e)
                
    if had_error:
        sys.exit(1)

if __name__ == "__main__":
    main()
