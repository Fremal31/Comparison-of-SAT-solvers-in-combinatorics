import unittest
import tempfile
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from CNFSymmetryBreaker import CNFSymmetryBreaker

class TestCNFSymmetryBreaker(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cnf_file = os.path.join(self.temp_dir, "test.cnf")
        with open(self.cnf_file, "w") as f:
            f.write("p cnf 1 1\n1 0\n")

        # Working dummy BreakID script
        self.breakid_path = os.path.join(self.temp_dir, "breakid")
        with open(self.breakid_path, "w") as f:
            f.write("""#!/bin/bash
                    echo 'T: 0.01 seconds'
                    echo 'p cnf 1 1\\n1 0' > "$2"
                    exit 0"""
                    )
        os.chmod(self.breakid_path, 0o755)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_init_with_invalid_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            CNFSymmetryBreaker(breakid_path="/nonexistent/path")

    def test_break_symmetries_creates_output(self):
        breaker = CNFSymmetryBreaker(breakid_path=self.breakid_path)
        output_path, timing = breaker.break_symmetries(self.cnf_file)
        self.assertTrue(Path(output_path).exists())
        self.assertEqual(timing, 0.01)

    def test_break_symmetries_temp_file(self):
        breaker = CNFSymmetryBreaker(breakid_path=self.breakid_path, use_temp=True)
        output_path, timing = breaker.break_symmetries(self.cnf_file)
        self.assertTrue(Path(output_path).exists())
        self.assertEqual(timing, 0.01)

    def test_timeout_returns_expected(self):
        with open(self.breakid_path, "w") as f:
            f.write("#!/bin/bash\nsleep 5\n")
        os.chmod(self.breakid_path, 0o755)

        breaker = CNFSymmetryBreaker(breakid_path=self.breakid_path, timeout=1)
        result, time_taken = breaker.break_symmetries(self.cnf_file)
        self.assertEqual(result, "TIMEOUT")
        self.assertEqual(time_taken, -1)

    def test_called_process_error_cleanup(self):
        # BreakID script that fails and writes to stderr
        with open(self.breakid_path, "w") as f:
            f.write("""#!/bin/bash
                    echo 'error' 1>&2
                    exit 1"""
                    )
        os.chmod(self.breakid_path, 0o755)

        breaker = CNFSymmetryBreaker(breakid_path=self.breakid_path)
        output_file = os.path.join(self.temp_dir, "output.cnf")
        open(output_file, 'a').close()
        self.assertTrue(os.path.exists(output_file))

        with self.assertRaises(RuntimeError):
            breaker.break_symmetries(self.cnf_file, output_file=output_file)

        self.assertFalse(os.path.exists(output_file))

    def test_parse_output(self):
        breaker = CNFSymmetryBreaker(breakid_path=self.breakid_path)
        example_output = """
        log line
        T: 0.42 seconds
        more logging
        """
        result = breaker.parse_output(example_output)
        self.assertAlmostEqual(result, 0.42)

if __name__ == "__main__":
    unittest.main()
