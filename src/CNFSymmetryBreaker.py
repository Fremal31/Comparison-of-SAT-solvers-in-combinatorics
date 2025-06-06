import subprocess
import os
import psutil
from pathlib import Path
import time
import tempfile

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
            temp_file = tempfile.NamedTemporaryFile(suffix='.cnf', delete=True)
            output_path = temp_file.name
            temp_file.close()
        else:
            delete_output = False
            if output_file is None:
                output_file = input_path.parent / f"{input_path.stem}_sb{input_path.suffix}"
                output_path = Path(output_file)
                if os.path.exists(output_path):
                    return output_path, "EXISTS"
        
        
        #output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.options is None:
            cmd = [self.breakid_path, input_cnf, output_path]
        else:
            cmd = [self.breakid_path, *self.options, input_cnf, output_path]
        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
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
        time = 0.0
        for line in breakid_output.split('\n'):
            #print(line)
            if 'T: ' in line:
                #print(float(line.split(' ')[5]), "ngrs")
                time += float(line.split(' ')[5])
            
        return time