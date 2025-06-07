import subprocess
import os
import psutil
from pathlib import Path
import time
import tempfile
import re

#TODO: add Docstrings

class CNFSymmetryBreaker:
    def __init__(self, breakid_path:str='./breakid/breakid', use_temp:bool = False, options:list = None, timeout:int|None = None):
        self.breakid_path = breakid_path
        if not os.path.isfile(self.breakid_path):
            raise FileNotFoundError(f"BreakID not found {self.breakid_path}")
        self.use_temp = use_temp
        self.options = options
        self.timeout = timeout

    def break_symmetries(self, input_cnf:str, output_file:str=None):
        input_path = Path(input_cnf)
        if self.use_temp:
            if output_file is not None:
                raise RuntimeWarning("Output file specified when using temp files.")
            temp_file = tempfile.NamedTemporaryFile(suffix='.cnf', delete=True)
            output_path = temp_file.name
            temp_file.close()
        else:
            if output_file is None:
                output_file = input_path.parent / f"{input_path.stem}_sb{input_path.suffix}"
            output_path = Path(output_file)
            #if os.path.exists(output_path):
            #    return output_path, "EXISTS"
        
        
        #output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.options is None:
            cmd = [self.breakid_path, input_cnf, output_path]
        else:
            cmd = [self.breakid_path, *self.options, input_cnf, output_path]
        try:
            if self.timeout is not None:
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True
                )
            else:
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
            processing_time = self.parse_output(process.stdout)
            return output_path, processing_time

        except subprocess.TimeoutExpired:
            return "TIMEOUT", -1
        except subprocess.CalledProcessError as e:
            if not self.use_temp and output_file is not None and os.path.exists(output_file):
                os.unlink(output_file)
            raise RuntimeError(f"BreakID failed: {e.stderr}") from e

    def parse_output(self, breakid_output):
        total_time = 0.0
        time_pattern = re.compile(r'.*T:.*?(\d+\.\d+).*')

        for line in breakid_output.splitlines():
            match = time_pattern.search(line)
            if match:
                try:
                    total_time += float(match.group(1))
                except ValueError:
                    continue

        return total_time
