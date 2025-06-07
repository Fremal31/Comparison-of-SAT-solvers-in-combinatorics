import unittest
import tempfile
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from SolverRunner import SolverRunner

class TestSolverRunner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # SAT dummy solver (exit 10)
        self.solver_path = os.path.join(self.temp_dir, "dummy_solver.sh")
        with open(self.solver_path, "w") as f:
            f.write("#!/bin/bash\necho 'SAT'\nexit 10")
        os.chmod(self.solver_path, 0o755)

        # CNF file (simple)
        self.cnf_path = os.path.join(self.temp_dir, "test.cnf")
        with open(self.cnf_path, "w") as f:
            f.write("p cnf 1 1\n1 0\n")

        self.runner = SolverRunner(self.solver_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_solver_runs_successfully(self):
        result = self.runner.run_solver(self.cnf_path, timeout=5)
        self.assertEqual(result["status"], "SAT")
        self.assertEqual(result["exit_code"], 10)
        self.assertIn("ans", result)
        self.assertIn("memory_peak_mb", result)
        self.assertGreaterEqual(result["time"], 0)

    def test_solver_unsat(self):
        # UNSAT dummy solver (exit 20)
        unsat_solver = os.path.join(self.temp_dir, "unsat_solver.sh")
        with open(unsat_solver, "w") as f:
            f.write("#!/bin/bash\necho 'UNSAT'\nexit 20")
        os.chmod(unsat_solver, 0o755)
        runner = SolverRunner(unsat_solver)

        result = runner.run_solver(self.cnf_path, timeout=5)
        self.assertEqual(result["status"], "UNSAT")
        self.assertEqual(result["exit_code"], 20)
        self.assertIn("ans", result)
        self.assertIn("memory_peak_mb", result)

    def test_solver_timeout(self):
        sleep_solver = os.path.join(self.temp_dir, "sleep_solver.sh")
        with open(sleep_solver, "w") as f:
            f.write("#!/bin/bash\nsleep 10\nexit 10")
        os.chmod(sleep_solver, 0o755)
        runner = SolverRunner(sleep_solver)

        result = runner.run_solver(self.cnf_path, timeout=1)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertEqual(result["exit_code"], -1)

    def test_solver_path_not_found(self):
        with self.assertRaises(FileNotFoundError):
            SolverRunner("/nonexistent/solver")

    def test_cnf_path_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.runner.run_solver("/nonexistent/file.cnf", timeout=1)

if __name__ == "__main__":
    unittest.main()
