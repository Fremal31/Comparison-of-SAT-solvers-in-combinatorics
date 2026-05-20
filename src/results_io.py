"""Serialization of solver results: flattening, streaming CSV/JSONL writers,
the structured JSON dump, and reading a results CSV back.

This is the data layer shared by the HTML report (html_report.py) and the
plot generation (plots.py), both of which import _flatten_result from here.
"""

import csv
import json
import logging
from dataclasses import asdict
from typing import IO, Any, Callable, Optional

from custom_types import NULL_BREAKER, NULL_FORMULATOR, Result
from utils import format_parameters_tag

logger: logging.Logger = logging.getLogger(__name__)

_SENTINELS = {NULL_FORMULATOR, NULL_BREAKER}


def _noop_append(r: Result) -> None:
    """Placeholder result-appender used until a real writer is created."""
    return None


def _flatten_result(res: Result) -> dict[str, Any]:
    """Converts a Result dataclass to a flat dict, merging the nested *metrics*
    dict into the top level so all fields are accessible by key.
    Internal sentinel values (NULL_FORMULATOR, NULL_BREAKER) are replaced with 'None' for display.
    *parameters* is rendered as the canonical 'k=v,k=v' string used elsewhere
    in the pipeline so CSV cells stay grep-friendly."""
    res_dict = asdict(res) if isinstance(res, Result) else dict(res)
    if 'metrics' in res_dict:
        res_dict.update(res_dict.pop('metrics'))
    res_dict['total_time'] = res.total_time if isinstance(res, Result) else 0.0
    for key in ('formulator', 'breaker'):
        if res_dict.get(key) in _SENTINELS:
            res_dict[key] = 'None'
    params = res_dict.get('parameters')
    if isinstance(params, dict):
        res_dict['parameters'] = format_parameters_tag(params)
    return res_dict


def create_csv_writer(fieldnames: list[str], output_path: str) -> tuple[IO[str], Callable[[Result], None]]:
    """
    Opens *output_path* for writing, writes the CSV header, and returns
    (file_handle, append_fn). Call append_fn(result) to write a single row.
    The caller is responsible for closing the file handle.
    """
    f = open(output_path, "w", newline="")  # noqa: SIM115 - caller owns and closes the handle
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    f.flush()

    def append(res: Result) -> None:
        try:
            res_dict = _flatten_result(res)
            writer.writerow({field: res_dict.get(field, "") for field in fieldnames})
            f.flush()
        except Exception as e:
            logger.warning("Failed to write CSV row: %s", e)

    return f, append


def create_jsonl_writer(
    output_path: str, fieldnames: Optional[list[str]] = None
) -> tuple[IO[str], Callable[[Result], None]]:
    """
    Opens *output_path* for writing and returns (file_handle, append_fn).
    Each result is written as a single JSON line (JSONL format) and flushed
    immediately. The caller is responsible for closing the file handle.

    If *fieldnames* is provided, only those keys appear in each JSON line
    (mirrors the CSV writer's column filter so both outputs stay symmetric
    with the user's *metrics_measured* config). None means write the full
    flattened Result.
    """
    f = open(output_path, "w")  # noqa: SIM115 - caller owns and closes the handle

    def append(res: Result) -> None:
        try:
            res_dict = _flatten_result(res)
            if fieldnames is not None:
                res_dict = {k: res_dict[k] for k in fieldnames if k in res_dict}
            f.write(json.dumps(res_dict, default=str) + "\n")
            f.flush()
        except Exception as e:
            logger.warning("Failed to write JSONL row: %s", e)

    return f, append


def create_all_writers(
    fieldnames: list[str], csv_path: str, jsonl_path: str
) -> tuple[Callable[[], None], Callable[[Result], None]]:
    """
    Creates both a CSV and JSONL writer and returns (close_fn, append_fn).
    Each call to append_fn writes one row to both files immediately.
    Call close_fn when done to close both file handles.

    If one file fails to open, the other is still closed properly.
    """
    csv_file: Optional[IO[str]] = None
    jsonl_file: Optional[IO[str]] = None
    csv_append: Callable[[Result], None] = _noop_append
    jsonl_append: Callable[[Result], None] = _noop_append

    try:
        csv_file, csv_append = create_csv_writer(fieldnames, csv_path)
    except OSError as e:
        logger.warning("Could not open CSV file %s: %s", csv_path, e)

    try:
        jsonl_file, jsonl_append = create_jsonl_writer(jsonl_path, fieldnames=fieldnames)
    except OSError as e:
        logger.warning("Could not open JSONL file %s: %s", jsonl_path, e)

    def append(res: Result) -> None:
        csv_append(res)
        jsonl_append(res)

    def close() -> None:
        if csv_file:
            csv_file.close()
        if jsonl_file:
            jsonl_file.close()

    return close, append


def log_results_to_json(results: list[Result], output_path: str) -> None:
    """
    Writes *results* to a JSON file at *output_path* structured as a nested dict
    keyed by problem → formulator → solver → breaker → parameters. The parameter
    level is always present (empty parameter dicts use the key 'none') so
    parameter sweeps don't collide on the same (problem, formulator, solver,
    breaker) tuple.

    Missing values are written as the string 'None'. Duplicate keys are overwritten
    with a warning printed to stdout.
    """
    structured: dict[str, Any] = {}
    for res in results:
        res_dict = _flatten_result(res)
        problem   = res_dict.get('problem')   or 'None'
        formulator = res_dict.get('formulator') or 'None'
        solver    = res_dict.get('solver')    or 'None'
        breaker   = res_dict.get('breaker')   or 'None'
        params    = res_dict.get('parameters') or 'none'

        target = (structured.setdefault(problem, {})
                            .setdefault(formulator, {})
                            .setdefault(solver, {})
                            .setdefault(breaker, {}))
        if params in target:
            logger.warning(
                "Duplicate result for (%s, %s, %s, %s, %s) — overwriting.",
                problem, formulator, solver, breaker, params,
            )
        target[params] = res_dict

    with open(output_path, "w") as f:
        json.dump(structured, f, indent=2, default=str)


def read_results_from_csv(csv_path: str) -> Any:
    """Reads a results CSV from *csv_path* and returns it as a pandas DataFrame."""
    import pandas as pd
    return pd.read_csv(csv_path)
