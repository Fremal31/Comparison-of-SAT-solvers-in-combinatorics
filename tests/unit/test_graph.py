import pytest
import json
import csv
from pathlib import Path
from typing import List

from custom_types import Result
from graph import (
    _flatten_result,
    create_csv_writer,
    create_jsonl_writer,
    create_all_writers,
    log_results_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(solver: str = "kissat", problem: str = "test", status: str = "SAT",
                time: float = 1.0, conflicts: int = 42) -> Result:
    return Result(solver=solver, problem=problem, status=status, time=time,
                  metrics={"conflicts": conflicts})


def make_results() -> List[Result]:
    return [
        make_result(solver="kissat", problem="p1", status="SAT", time=1.0, conflicts=10),
        make_result(solver="cadical", problem="p1", status="UNSAT", time=2.0, conflicts=20),
    ]


# ---------------------------------------------------------------------------
# _flatten_result
# ---------------------------------------------------------------------------

class TestFlattenResult:
    def test_metrics_merged_into_top_level(self):
        res = make_result(conflicts=99)
        flat = _flatten_result(res)
        assert flat["conflicts"] == 99
        assert "metrics" not in flat

    def test_standard_fields_preserved(self):
        res = make_result(solver="kissat", status="SAT", time=1.5)
        flat = _flatten_result(res)
        assert flat["solver"] == "kissat"
        assert flat["status"] == "SAT"
        assert flat["time"] == 1.5

    def test_empty_metrics(self):
        res = Result(solver="test", problem="test")
        flat = _flatten_result(res)
        assert "metrics" not in flat


# ---------------------------------------------------------------------------
# create_csv_writer
# ---------------------------------------------------------------------------

class TestCreateCsvWriter:
    def test_creates_file_with_header(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        f, append = create_csv_writer(["solver", "status"], str(path))
        f.close()
        content = path.read_text()
        assert "solver,status" in content

    def test_append_writes_row(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        f, append = create_csv_writer(["solver", "status", "conflicts"], str(path))
        append(make_result())
        f.close()
        rows = list(csv.DictReader(open(path)))
        assert len(rows) == 1
        assert rows[0]["solver"] == "kissat"
        assert rows[0]["status"] == "SAT"

    def test_multiple_appends(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        f, append = create_csv_writer(["solver", "status"], str(path))
        for res in make_results():
            append(res)
        f.close()
        rows = list(csv.DictReader(open(path)))
        assert len(rows) == 2

    def test_missing_field_written_as_empty(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        f, append = create_csv_writer(["solver", "nonexistent_field"], str(path))
        append(make_result())
        f.close()
        rows = list(csv.DictReader(open(path)))
        assert rows[0]["nonexistent_field"] == ""

    def test_flush_makes_data_available_immediately(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        f, append = create_csv_writer(["solver", "status"], str(path))
        append(make_result())
        # read without closing — data should be flushed
        content = path.read_text()
        assert "kissat" in content
        f.close()

    def test_append_does_not_crash_on_closed_file(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        f, append = create_csv_writer(["solver"], str(path))
        f.close()
        append(make_result())  # should warn, not crash


# ---------------------------------------------------------------------------
# create_jsonl_writer
# ---------------------------------------------------------------------------

class TestCreateJsonlWriter:
    def test_creates_file(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        f.close()
        assert path.exists()

    def test_append_writes_json_line(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        append(make_result())
        f.close()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["solver"] == "kissat"
        assert obj["status"] == "SAT"

    def test_multiple_appends_one_line_each(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        for res in make_results():
            append(res)
        f.close()
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        for res in make_results():
            append(res)
        f.close()
        for line in path.read_text().strip().splitlines():
            json.loads(line)  # should not raise

    def test_metrics_flattened_in_jsonl(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        append(make_result(conflicts=77))
        f.close()
        obj = json.loads(path.read_text().strip())
        assert obj["conflicts"] == 77
        assert "metrics" not in obj

    def test_flush_makes_data_available_immediately(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        append(make_result())
        content = path.read_text()
        assert "kissat" in content
        f.close()

    def test_append_does_not_crash_on_closed_file(self, tmp_path: Path):
        path = tmp_path / "results.jsonl"
        f, append = create_jsonl_writer(str(path))
        f.close()
        append(make_result())  # should warn, not crash


# ---------------------------------------------------------------------------
# create_all_writers
# ---------------------------------------------------------------------------

class TestCreateAllWriters:
    def test_writes_to_both_files(self, tmp_path: Path):
        csv_path = tmp_path / "results.csv"
        jsonl_path = tmp_path / "results.jsonl"
        close, append = create_all_writers(["solver", "status"], str(csv_path), str(jsonl_path))
        append(make_result())
        close()
        assert csv_path.exists()
        assert jsonl_path.exists()
        assert "kissat" in csv_path.read_text()
        assert "kissat" in jsonl_path.read_text()

    def test_close_closes_both_files(self, tmp_path: Path):
        csv_path = tmp_path / "results.csv"
        jsonl_path = tmp_path / "results.jsonl"
        close, append = create_all_writers(["solver"], str(csv_path), str(jsonl_path))
        append(make_result())
        close()
        # appending after close should warn, not crash
        append(make_result())

    def test_csv_failure_does_not_block_jsonl(self, tmp_path: Path):
        bad_csv = tmp_path / "nonexistent_dir" / "results.csv"
        jsonl_path = tmp_path / "results.jsonl"
        close, append = create_all_writers(["solver"], str(bad_csv), str(jsonl_path))
        append(make_result())
        close()
        assert jsonl_path.exists()
        assert "kissat" in jsonl_path.read_text()

    def test_jsonl_failure_does_not_block_csv(self, tmp_path: Path):
        csv_path = tmp_path / "results.csv"
        bad_jsonl = tmp_path / "nonexistent_dir" / "results.jsonl"
        close, append = create_all_writers(["solver"], str(csv_path), str(bad_jsonl))
        append(make_result())
        close()
        assert csv_path.exists()
        assert "kissat" in csv_path.read_text()

    def test_multiple_results(self, tmp_path: Path):
        csv_path = tmp_path / "results.csv"
        jsonl_path = tmp_path / "results.jsonl"
        close, append = create_all_writers(["solver", "status"], str(csv_path), str(jsonl_path))
        for res in make_results():
            append(res)
        close()
        csv_rows = list(csv.DictReader(open(csv_path)))
        jsonl_lines = jsonl_path.read_text().strip().splitlines()
        assert len(csv_rows) == 2
        assert len(jsonl_lines) == 2


# ---------------------------------------------------------------------------
# log_results_to_json
# ---------------------------------------------------------------------------

class TestLogResultsToJson:
    def test_creates_structured_json(self, tmp_path: Path):
        path = tmp_path / "results.json"
        log_results_to_json(make_results(), str(path))
        data = json.loads(path.read_text())
        assert "p1" in data
        assert "kissat" in data["p1"]["None"]
        assert "cadical" in data["p1"]["None"]

    def test_nested_structure(self, tmp_path: Path):
        path = tmp_path / "results.json"
        res = make_result(solver="kissat", problem="p1")
        res.formulator = "form1"
        res.breaker = "breakid"
        log_results_to_json([res], str(path))
        data = json.loads(path.read_text())
        assert data["p1"]["form1"]["kissat"]["breakid"]["status"] == "SAT"

    def test_empty_results(self, tmp_path: Path):
        path = tmp_path / "results.json"
        log_results_to_json([], str(path))
        data = json.loads(path.read_text())
        assert data == {}

    def test_none_values_become_none_string(self, tmp_path: Path):
        path = tmp_path / "results.json"
        res = Result(solver="kissat", problem="p1")
        log_results_to_json([res], str(path))
        data = json.loads(path.read_text())
        assert "None" in data["p1"]  # formulator key is "None"

    def test_metrics_flattened_in_json(self, tmp_path: Path):
        path = tmp_path / "results.json"
        log_results_to_json([make_result(conflicts=55)], str(path))
        data = json.loads(path.read_text())
        leaf = data["test"]["None"]["kissat"]["None"]
        assert leaf["conflicts"] == 55
        assert "metrics" not in leaf
