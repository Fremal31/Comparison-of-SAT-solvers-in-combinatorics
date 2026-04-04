import pytest
import os
import sys
import json
from pathlib import Path

from main import (
    _validate_max_threads,
    _validate_timeout,
    _validate_working_dir,
    _validate_data,
    _ensure_results_directory,
    load_config,
)

# ---------------------------------------------------------------------------
# _validate_max_threads
# ---------------------------------------------------------------------------

class TestValidateMaxThreads:
    def test_valid_value(self):
        assert _validate_max_threads(1) == 1

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            _validate_max_threads(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            _validate_max_threads(-1)

    def test_capped_at_cpu_count_minus_one(self):
        result = _validate_max_threads(9999)
        assert result >= 1
        assert result <= max(1, (os.cpu_count() or 1) - 1)

    def test_single_core_machine_returns_one(self, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: 1)
        result = _validate_max_threads(9999)
        assert result == 1

    def test_cpu_count_none_treated_as_one(self, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: None)
        result = _validate_max_threads(9999)
        assert result == 1

    def test_value_equal_to_cap_is_accepted(self, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        result = _validate_max_threads(3)  # cap is max(1, 4-1) = 3
        assert result == 3


# ---------------------------------------------------------------------------
# _validate_timeout
# ---------------------------------------------------------------------------

class TestValidateTimeout:
    def test_valid_value(self):
        assert _validate_timeout(5) == 5

    def test_zero_is_valid(self):
        assert _validate_timeout(0) == 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            _validate_timeout(-1)


# ---------------------------------------------------------------------------
# _validate_working_dir
# ---------------------------------------------------------------------------

class TestValidateWorkingDir:
    def test_nonexistent_dir_is_valid(self, tmp_path: Path):
        new_dir = tmp_path / "new_dir"
        result = _validate_working_dir(str(new_dir), confirm_delete=False)
        assert result == new_dir.resolve()

    def test_empty_existing_dir_is_valid(self, tmp_path: Path):
        result = _validate_working_dir(str(tmp_path), confirm_delete=False)
        assert result == tmp_path.resolve()

    def test_non_empty_dir_without_delete_raises(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("content")
        with pytest.raises(ValueError, match="not empty"):
            _validate_working_dir(str(tmp_path), confirm_delete=False)

    def test_non_empty_dir_with_delete_is_valid(self, tmp_path: Path):
        (tmp_path / "file.txt").write_text("content")
        result = _validate_working_dir(str(tmp_path), confirm_delete=True)
        assert result == tmp_path.resolve()

    def test_path_that_is_a_file_raises(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(ValueError):
            _validate_working_dir(str(f), confirm_delete=False)

    @pytest.mark.skipif(
        sys.platform == "win32" or os.getuid() == 0,
        reason="permission checks not applicable on Windows or when running as root"
    )
    def test_non_writable_dir_raises(self, tmp_path: Path):
        tmp_path.chmod(0o444)
        try:
            with pytest.raises(PermissionError):
                _validate_working_dir(str(tmp_path), confirm_delete=False)
        finally:
            tmp_path.chmod(0o755)  # restore so pytest can clean up


# ---------------------------------------------------------------------------
# _validate_data
# ---------------------------------------------------------------------------

class TestValidateData:
    def test_valid_minimal_config(self):
        _validate_data({"solvers": {"s": {}}})

    def test_missing_solvers_raises(self):
        with pytest.raises(ValueError, match="solvers"):
            _validate_data({})

    def test_empty_solvers_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {}})

    def test_solvers_not_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": ["s1"]})

    def test_formulators_not_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {"s": {}}, "formulators": ["f1"]})

    def test_breakers_not_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {"s": {}}, "breakers": ["b1"]})

    def test_triplets_not_list_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {"s": {}}, "triplets": {}})

    def test_triplet_mode_without_triplets_raises(self):
        with pytest.raises(ValueError, match="triplets"):
            _validate_data({"solvers": {"s": {}}, "triplet_mode": True})

    def test_metrics_measured_not_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {"s": {}}, "metrics_measured": ["m1"]})

    def test_files_not_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {"s": {}}, "files": ["f1"]})

    def test_without_converter_not_dict_raises(self):
        with pytest.raises(ValueError):
            _validate_data({"solvers": {"s": {}}, "without_converter": ["wc1"]})

    def test_triplet_mode_false_with_triplets_is_valid(self):
        _validate_data({"solvers": {"s": {}}, "triplet_mode": False, "triplets": []})

    def test_duplicate_name_across_solvers_and_files_raises(self):
        with pytest.raises(ValueError, match="Duplicate name 'dup'"):
            _validate_data({"solvers": {"dup": {}}, "files": {"dup": {}}})

    def test_duplicate_name_across_solvers_and_formulators_raises(self):
        with pytest.raises(ValueError, match="Duplicate name 'dup'"):
            _validate_data({"solvers": {"dup": {}}, "formulators": {"dup": {}}})

    def test_duplicate_name_across_solvers_and_breakers_raises(self):
        with pytest.raises(ValueError, match="Duplicate name 'dup'"):
            _validate_data({"solvers": {"dup": {}}, "breakers": {"dup": {}}})

    def test_duplicate_name_across_files_and_without_converter_raises(self):
        with pytest.raises(ValueError, match="Duplicate name 'dup'"):
            _validate_data({"solvers": {"s": {}}, "files": {"dup": {}}, "without_converter": {"dup": {}}})

    def test_unique_names_across_all_sections_is_valid(self):
        _validate_data({
            "solvers": {"s1": {}},
            "files": {"f1": {}},
            "formulators": {"form1": {}},
            "breakers": {"b1": {}},
            "without_converter": {"wc1": {}}
        })


# ---------------------------------------------------------------------------
# _ensure_results_directory
# ---------------------------------------------------------------------------

class TestEnsureResultsDirectory:
    def test_creates_parent_directories(self, tmp_path: Path):
        path = tmp_path / "a" / "b" / "results.csv"
        _ensure_results_directory(str(path))
        assert path.parent.exists()

    def test_existing_writable_file_is_valid(self, tmp_path: Path):
        path = tmp_path / "results.csv"
        path.write_text("")
        _ensure_results_directory(str(path))  # should not raise


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_missing_config_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")

    def test_invalid_json_raises(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json {{{")
        with pytest.raises(Exception):
            load_config(config_path)

    def test_defaults_applied_when_optional_fields_omitted(self, tmp_path: Path):
        config_data = {
            "solvers": {"dummy": {"type": "SAT", "cmd": "echo", "enabled": True}},
            "working_dir": str(tmp_path / "work"),
            "results_csv": str(tmp_path / "results.csv"),
            "results_json": str(tmp_path / "results.json"),
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))
        config = load_config(config_path)
        assert config.timeout == 5
        assert config.max_threads >= 1
        assert config.triplet_mode is False
        assert config.delete_working_dir is False
        assert config.visualization.enabled is False

    def test_valid_minimal_config_loads(self, tmp_path: Path):
        config_data = {
            "solvers": {
                "dummy": {
                    "type": "SAT",
                    "cmd": "echo",
                    "enabled": True
                }
            },
            "working_dir": str(tmp_path / "work"),
            "results_csv": str(tmp_path / "results.csv"),
            "results_json": str(tmp_path / "results.json"),
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))
        config = load_config(config_path)
        assert len(config.solvers) == 1
        assert config.solvers[0].name == "dummy"
