import unittest
import tempfile
import os
import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from SolverManager import MultiSolverManager

class TestMultiSolverManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cnf_file = os.path.join(self.temp_dir, "test.cnf")
        with open(self.cnf_file, "w") as f:
            f.write("p cnf 1 1\n1 0\n")

        self.config_path = os.path.join(self.temp_dir, "config.json")
        self.solver_path = os.path.join(self.temp_dir, "dummy_solver.sh")
        with open(self.solver_path, "w") as f:
            f.write("#!/bin/bash\nexit 0")
        os.chmod(self.solver_path, 0o755)

        with open(self.config_path, "w") as f:
            json.dump([{"name": "DummySolver", "path": self.solver_path}], f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_initialization_and_directory_handling(self):
        subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(subdir)
        subfile = os.path.join(subdir, "test2.cnf")
        with open(subfile, "w") as f:
            f.write("p cnf 2 2\n1 0\n2 0\n")

        mgr = MultiSolverManager(self.config_path, [self.cnf_file, subdir])
        mgr_paths = set(Path(p).resolve() for p in mgr.cnf_files)
        expected_paths = set(p.resolve() for p in Path(subdir).glob("*"))
        self.assertTrue(expected_paths.issubset(mgr_paths))


    @patch("SolverRunner.SolverRunner.run_solver")
    def test_run_all_no_symmetry(self, mock_run_solver):
        mock_run_solver.return_value = {
            "exit_code": 0,
            "time": 0.1,
            "cpu_time": 0.1,
            "cpu_usage_avg": 10.0,
            "cpu_usage_max": 12.0,
            "memory_peak_mb": 15.0,
            "stderr": "",
            "status": "OK"
        }

        mgr = MultiSolverManager(self.config_path, [self.cnf_file], timeout=10, maxthreads=1)
        results = mgr.run_all()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "OK")
        self.assertEqual(results[0]["solver"], "DummySolver")
        self.assertEqual(results[0]["original_cnf"], Path(self.cnf_file))


    def test_set_symmetry_breaker(self):
        mgr = MultiSolverManager(self.config_path, [self.cnf_file])
        mgr.set_symmetry_breaker(True, self.solver_path, use_temp_files=True)
        self.assertTrue(mgr.break_symmetry)
        self.assertTrue(mgr.use_temp_files)
        self.assertEqual(mgr.symmetry_path, self.solver_path)
        self.assertIsNotNone(mgr.breaker)

    @patch("CNFSymmetryBreaker.CNFSymmetryBreaker.break_symmetries")
    @patch("SolverRunner.SolverRunner.run_solver")
    def test_run_all_with_symmetry_breaking(self, mock_run_solver, mock_break_symmetries):
        mock_run_solver.return_value = {
            "exit_code": 0,
            "time": 0.1,
            "cpu_time": 0.1,
            "cpu_usage_avg": 10.0,
            "cpu_usage_max": 12.0,
            "memory_peak_mb": 15.0,
            "stderr": "",
            "status": "OK"
        }

        modified_cnf = self.cnf_file + "_sb"
        mock_break_symmetries.return_value = (modified_cnf, 0.5)

        mgr = MultiSolverManager(self.config_path, [self.cnf_file], timeout=10, maxthreads=1)
        mgr.set_symmetry_breaker(True, self.solver_path)

        results = mgr.run_all()

        original_runs = [r for r in results if str(r["original_cnf"]) == self.cnf_file]
        symmetry_runs = [r for r in results if str(r["original_cnf"]) == modified_cnf]

        self.assertEqual(len(original_runs), 1)
        self.assertEqual(len(symmetry_runs), 1)
        self.assertTrue(all(r["status"] == "OK" for r in original_runs + symmetry_runs))
        self.assertEqual(symmetry_runs[0]["break_time"], 0.5)

    @patch("CNFSymmetryBreaker.CNFSymmetryBreaker.break_symmetries")
    @patch("SolverRunner.SolverRunner.run_solver")
    def test_symmetry_breaker_timeout(self, mock_run_solver, mock_break_symmetries):
        mock_run_solver.return_value = {
            "exit_code": 0,
            "time": 0.1,
            "cpu_time": 0.1,
            "cpu_usage_avg": 10.0,
            "cpu_usage_max": 12.0,
            "memory_peak_mb": 15.0,
            "stderr": "",
            "status": "OK"
        }
        
        mock_break_symmetries.return_value = ("TIMEOUT", -1.0)

        mgr = MultiSolverManager(self.config_path, [self.cnf_file], timeout=10, maxthreads=1)
        mgr.set_symmetry_breaker(True, self.solver_path)

        results = mgr.run_all()
        timeout_results = [r for r in results if str(r["status"]) == "TIMEOUT"]
        original_runs = [r for r in results if str(r["original_cnf"]) == self.cnf_file]

        self.assertEqual(len(original_runs), 1)
        self.assertEqual(len(timeout_results), 1)
        self.assertEqual(timeout_results[0]["original_cnf"], self.cnf_file + "_sb")

    @patch("CNFSymmetryBreaker.CNFSymmetryBreaker.break_symmetries")
    @patch("SolverRunner.SolverRunner.run_solver")
    def test_symmetry_breaker_exception(self, mock_run_solver, mock_break_symmetries):
        mock_run_solver.return_value = {
            "exit_code": 0,
            "time": 0.1,
            "cpu_time": 0.1,
            "cpu_usage_avg": 10.0,
            "cpu_usage_max": 12.0,
            "memory_peak_mb": 15.0,
            "stderr": "",
            "status": "OK"
        }
        mock_break_symmetries.side_effect = Exception("Symmetry breaker error")

        mgr = MultiSolverManager(self.config_path, [self.cnf_file], timeout=10, maxthreads=1)
        mgr.set_symmetry_breaker(True, self.solver_path)

        results = mgr.run_all()

        error_results = [r for r in results if str(r["status"]) == "SYM_BREAK_ERROR"]
        original_runs = [r for r in results if str(r["original_cnf"]) == self.cnf_file]

        self.assertEqual(len(original_runs), 1)
        self.assertEqual(len(error_results), 1)
        self.assertIn("Symmetry breaker error", error_results[0]["error"])

    def test_cleanup_temp_files(self):
        mgr = MultiSolverManager(self.config_path, [self.cnf_file])
        tmp_file = os.path.join(self.temp_dir, "tmp.cnf")
        open(tmp_file, 'a').close()
        mgr.temp_files = [tmp_file]
        mgr.cleanup_temp_files()
        self.assertFalse(os.path.exists(tmp_file))


if __name__ == "__main__":
    unittest.main()
