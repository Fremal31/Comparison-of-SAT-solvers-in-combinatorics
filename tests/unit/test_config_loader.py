import pytest
import os
import sys
import json
from pathlib import Path

from config_loader import (
    _validate_max_threads,
    _validate_timeout,
    _validate_working_dir,
    _validate_data,
    _ensure_results_directory,
    _parse_triplets,
    _parse_single_file_config,
    _parse_single_formulator_config,
    _parse_single_exec_config,
    _parse_single_without_converter,
    load_config,
    set_base_dir,
    reset_base_dir,
)

# ---------------------------------------------------------------------------
# _validate_max_threads
# ---------------------------------------------------------------------------

class TestValidateMaxThreads:
    def test_valid_value(self):
        assert _validate_max_threads(1) == 1

    def test_zero_returns_system_default(self):
        result = _validate_max_threads(0)
        assert result >= 1
        assert result <= max(1, (os.cpu_count() or 1) - 1)

    def test_negative_returns_system_default(self):
        result = _validate_max_threads(-1)
        assert result >= 1
        assert result <= max(1, (os.cpu_count() or 1) - 1)

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
        assert config.triplet_mode is False
        assert config.delete_working_dir is False
        assert config.visualization.enabled is False

    def test_config_threading_defaults(self, tmp_path: Path):
        config_data = {
            "solvers": {"dummy": {"type": "SAT", "cmd": "echo", "enabled": True}},
            "working_dir": str(tmp_path / "work")
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data))
        
        config = load_config(config_path)
        
        # Assert ThreadConfig defaults
        assert config.thread_config.max_threads >= 1
        assert config.thread_config.allowed_cores is None
        assert config.thread_config.use_boss_core is False

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


# ---------------------------------------------------------------------------
# _parse_triplets
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "files": {
        "prob1": {"path": "./examples/graph.g6"},
    },
    "formulators": {
        "form1": {"type": "SAT", "cmd": "echo", "enabled": True},
    },
    "solvers": {
        "solver1": {"type": "SAT", "cmd": "echo", "enabled": True},
        "solver2": {"type": "SAT", "cmd": "echo", "enabled": True},
        "ilp_solver": {"type": "ILP", "cmd": "echo", "enabled": True},
    },
    "breakers": {
        "brk1": {"type": "SAT", "cmd": "echo", "enabled": True},
    },
    "without_converter": {
        "wc1": {"path": "./examples/hamilton/hamilton_bigbad.cnf", "type": "SAT"},
    },
}

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestParseTriplets:
    def setup_method(self):
        set_base_dir(PROJECT_ROOT)
        self.files = {}
        for name, data in MINIMAL_CONFIG.get('files', {}).items():
            self.files[name] = _parse_single_file_config(name, data)
        self.formulators = {}
        for name, data in MINIMAL_CONFIG.get('formulators', {}).items():
            self.formulators[name] = _parse_single_formulator_config(name, data)
        self.solvers = {}
        for name, data in MINIMAL_CONFIG.get('solvers', {}).items():
            self.solvers[name] = _parse_single_exec_config(name, data)
        self.breakers = {}
        for name, data in MINIMAL_CONFIG.get('breakers', {}).items():
            self.breakers[name] = _parse_single_exec_config(name, data)
        self.wc = {}
        for name, data in MINIMAL_CONFIG.get('without_converter', {}).items():
            self.wc[name] = _parse_single_without_converter(name, data)

    def teardown_method(self):
        reset_base_dir()

    def _run(self, triplets):
        return _parse_triplets(triplets, self.files, self.formulators, self.solvers, self.breakers, self.wc)

    def test_explicit_solver(self):
        result = self._run([{"problem": "prob1", "formulator": "form1", "solver": "solver1"}])
        assert len(result) == 1
        assert result[0].solver.name == "solver1"

    def test_solver_omitted_produces_none(self):
        result = self._run([{"problem": "prob1", "formulator": "form1"}])
        assert len(result) == 1
        assert result[0].solver is None

    def test_solver_omitted_with_breaker(self):
        result = self._run([{"problem": "prob1", "formulator": "form1", "breaker": "brk1"}])
        assert len(result) == 1
        assert result[0].solver is None
        assert result[0].breaker.name == "brk1"

    def test_without_converter_solver_omitted(self):
        result = self._run([{"without_converter": "wc1"}])
        assert len(result) == 1
        assert result[0].solver is None
        assert result[0].test_case is not None

    def test_without_converter_with_explicit_solver(self):
        result = self._run([{"without_converter": "wc1", "solver": "solver1"}])
        assert len(result) == 1
        assert result[0].solver.name == "solver1"

    def test_missing_problem_and_without_converter_raises(self):
        with pytest.raises(ValueError, match="problem \\+ formulator"):
            self._run([{"solver": "solver1"}])

    def test_problem_without_formulator_raises(self):
        with pytest.raises(ValueError, match="no formulator"):
            self._run([{"problem": "prob1", "solver": "solver1"}])

    def test_formulator_without_problem_raises(self):
        with pytest.raises(ValueError, match="no problem"):
            self._run([{"formulator": "form1", "solver": "solver1"}])

    def test_both_problem_and_without_converter_raises(self):
        with pytest.raises(ValueError, match="not both"):
            self._run([{"problem": "prob1", "formulator": "form1", "without_converter": "wc1", "solver": "solver1"}])

    def test_nonexistent_solver_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            self._run([{"problem": "prob1", "formulator": "form1", "solver": "nonexistent"}])


# ---------------------------------------------------------------------------
# _parse_single_file_config — directory expansion
# ---------------------------------------------------------------------------

class TestParseFileConfigDirectory:
    def teardown_method(self):
        reset_base_dir()

    def test_single_file_returns_one(self, tmp_path: Path):
        set_base_dir(tmp_path)
        f = tmp_path / "graph.g6"
        f.write_text("data")
        result = _parse_single_file_config("prob", {"path": str(f)})
        assert len(result) == 1
        assert result[0].name == "prob"

    def test_directory_expands_to_multiple(self, tmp_path: Path):
        set_base_dir(tmp_path)
        d = tmp_path / "graphs"
        d.mkdir()
        (d / "a.g6").write_text("data")
        (d / "b.g6").write_text("data")
        (d / "c.g6").write_text("data")
        result = _parse_single_file_config("my_graphs", {"path": str(d)})
        assert len(result) == 3

    def test_directory_names_use_config_name_and_stem(self, tmp_path: Path):
        set_base_dir(tmp_path)
        d = tmp_path / "graphs"
        d.mkdir()
        (d / "small.g6").write_text("data")
        (d / "large.g6").write_text("data")
        result = _parse_single_file_config("hamiltons", {"path": str(d)})
        names = [fc.name for fc in result]
        assert "hamiltons_small" in names
        assert "hamiltons_large" in names

    def test_directory_files_sorted(self, tmp_path: Path):
        set_base_dir(tmp_path)
        d = tmp_path / "graphs"
        d.mkdir()
        (d / "z.g6").write_text("data")
        (d / "a.g6").write_text("data")
        result = _parse_single_file_config("prob", {"path": str(d)})
        assert result[0].name == "prob_a"
        assert result[1].name == "prob_z"

    def test_directory_skips_subdirectories(self, tmp_path: Path):
        set_base_dir(tmp_path)
        d = tmp_path / "graphs"
        d.mkdir()
        (d / "good.g6").write_text("data")
        (d / "subdir").mkdir()
        result = _parse_single_file_config("prob", {"path": str(d)})
        assert len(result) == 1

    def test_empty_directory_raises(self, tmp_path: Path):
        set_base_dir(tmp_path)
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(ValueError, match="empty directory"):
            _parse_single_file_config("prob", {"path": str(d)})

    def test_enabled_propagated_to_all(self, tmp_path: Path):
        set_base_dir(tmp_path)
        d = tmp_path / "graphs"
        d.mkdir()
        (d / "a.g6").write_text("data")
        (d / "b.g6").write_text("data")
        result = _parse_single_file_config("prob", {"path": str(d), "enabled": False})
        assert all(not fc.enabled for fc in result)

    def test_missing_path_raises(self, tmp_path: Path):
        set_base_dir(tmp_path)
        with pytest.raises(ValueError, match="missing required 'path'"):
            _parse_single_file_config("prob", {})
