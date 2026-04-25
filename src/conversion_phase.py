import logging
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from custom_types import TestCase, RawResult, ConversionError
from factory import get_converter
from format_types import ConversionTask, ExperimentContext
from converter import Converter
from generic_executor import GlobalMonitor

logger = logging.getLogger(__name__)

ConversionResults = Dict[Tuple[str, str], Tuple[List[TestCase], Optional[RawResult]]]


def run_conversion_phase(
    unique_conversions: Dict[Tuple[str, str], ConversionTask],
    pre_encoded: ConversionResults,
    max_threads: int,
) -> Tuple[ConversionResults, List[TestCase]]:
    """
    Phase 1: converts each unique (problem, formulator) pair in parallel.

    Returns the merged results dict (pre-encoded entries + converted) and the
    list of newly generated TestCases for cleanup tracking.
    """
    results: ConversionResults = dict(pre_encoded)
    new_test_cases: List[TestCase] = []

    if not unique_conversions:
        return results, new_test_cases

    logger.info("--- Converting %d (problem, formulator) pairs ---", len(unique_conversions))
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures: Dict[Future[Tuple[List[TestCase], Optional[RawResult]]], Tuple[str, str]] = {
            executor.submit(_worker_convert, task): key
            for key, task in unique_conversions.items()
        }
        try:
            for future in as_completed(futures):
                key = futures[future]
                test_cases, raw = future.result()
                results[key] = (test_cases, raw)
                new_test_cases.extend(test_cases)
        except KeyboardInterrupt:
            logger.error("Interrupted during conversion phase. Cancelling...")
            GlobalMonitor().kill_all()
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    return results, new_test_cases


def _worker_convert(task: ConversionTask) -> Tuple[List[TestCase], Optional[RawResult]]:
    """
    Converts a single (problem, formulator) pair.

    Returns (test_cases, raw_result) on success, or ([], None) on failure.
    """
    context: ExperimentContext = task.work_dir
    output_path: Path = context.base_path / f"{task.problem.name}{context.format_info.suffix}"
    try:
        converter: Converter = get_converter(form_cfg=task.config)
        test_cases, raw = converter.convert(
            problem=task.problem, output_path=output_path, timeout=task.timeout
        )
        logger.info(
            "[CONVERT] %s using %s: %.2fs, peak mem %.1fMB",
            task.problem.name, task.config.name, raw.time, raw.memory_peak_mb,
        )
        return test_cases, raw
    except ConversionError as e:
        logger.error("[CONVERT] Failed: %s using %s. Error: %s", task.problem.name, task.config.name, e)
        return [], None
    except Exception as e:
        logger.error("[CONVERT] Critical Error: %s: %s", task.problem.name, e)
        return [], None
