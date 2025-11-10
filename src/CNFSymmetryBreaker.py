import subprocess
import os
#import psutil
from pathlib import Path
from SolverRunner import CNFFile, SolverResult
from SolverManager import *
#import time
import tempfile
import re
from typing import Dict, Optional, Union, Final


class CNFSymmetryBreaker:
    """
    A utility class to run BreakID on CNF files for symmetry breaking.
    Attributes:
        breakid_path (str): Path to the BreakID binary.
        use_temp (bool): Whether to use a temporary file for the output.
        options (list): Optional list of command-line options to pass to BreakID.
        timeout (int | None): Maximum allowed time for BreakID execution, in seconds.
    """
    def __init__(
            self, 
            breakid_path:str='./breakid/breakid', 
            use_temp:bool = False, 
            options:list = None, 
            timeout:Optional[int] = None
            ) -> None:
        """
        Initialize the CNFSymmetryBreaker instance.
        Args:
            breakid_path (str): Path to the BreakID binary.
            use_temp (bool): If True, use a temporary file for the output CNF.
            options (list): Optional list of command-line options for BreakID.
            timeout (int | None): Optional timeout for the subprocess in seconds.
        Raises:
            FileNotFoundError: If the BreakID binary is not found at the given path.
        """
        self.breakid_path:str = breakid_path
        if not os.path.isfile(self.breakid_path):
            raise FileNotFoundError(f"BreakID not found {self.breakid_path}")
        self.use_temp:bool = use_temp
        self.options: Optional[list[str]] = options
        self.timeout: Optional[int] = timeout

    def symmetry_results(self, input_cnf:CNFFile, output_file:CNFFile=None) -> tuple[SolverResult, CNFFile]:
        try:
            modified_cnf, break_time = self.break_symmetries({"name": input_cnf["name"], "path": input_cnf["path"]})
            if break_time == TIMEOUT:
                timeout_result: SolverResult = {
                    "original_cnf": input_cnf["name"],
                    "break_time": break_time,
                    "status": "TIMEOUT",
                    "error": "",
                }
                return timeout_result, modified_cnf
            result: SolverResult = {
                "original_cnf": input_cnf["name"],
                "break_time": break_time,
                "error": ""
            }
            return result, modified_cnf
        
        except Exception as e:
            error_result: SolverResult = {
                "original_cnf": input_cnf["name"],
                "break_time": TIMEOUT,
                "status": "SYM_BREAK_ERROR",
                "error": str(e),
            }
            return error_result, modified_cnf


    def break_symmetries(self, input_cnf:CNFFile, output_file:CNFFile=None) -> tuple[CNFFile, float]:
        """
        Runs BreakID on a CNF file to break symmetries.
        Args:
            !input_cnf (str): Path to the input CNF file.
            output_file (str | None): Optional path to save the output CNF. Ignored if use_temp is True.
        Returns:
            tuple: A tuple (output_path, processing_time). If the process times out, returns ("TIMEOUT", -1).
        Raises:
            RuntimeError: If BreakID fails during execution.
            RuntimeWarning: If output_file is provided while using a temp file.
        """
        input_path: Path = Path(input_cnf["path"])
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
            cmd = [self.breakid_path, input_path, output_path]
        else:
            cmd = [self.breakid_path, *self.options, input_path, output_path]
        try:
            if self.timeout is not None:
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True,
                )
            else:
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
            processing_time = self.parse_output(process.stdout)
            return {"name": input_cnf["name"], "path": output_path}, processing_time

        except subprocess.TimeoutExpired:
            return {"name": input_cnf["name"], "path": output_path}, TIMEOUT
        except subprocess.CalledProcessError as e:
            if not self.use_temp and output_file is not None and os.path.exists(output_file):
                os.unlink(output_file)
            raise RuntimeError(f"BreakID failed: {e.stderr}") from e

    def parse_output(self, breakid_output: str) -> float:
        """
        Parses the output of BreakID to extract the total processing time.
        Args:
            breakid_output (str): The standard output from BreakID.
        Returns:
            float: The total processing time parsed from the output. Returns 0.0 if no valid timing found.
        """
        total_time: float = 0.0
        time_pattern = re.compile(r'.*T:.*?(\d+\.\d+).*')

        for line in breakid_output.splitlines():
            match = time_pattern.search(line)
            if match:
                try:
                    total_time += float(match.group(1))
                except ValueError:
                    continue

        return total_time
