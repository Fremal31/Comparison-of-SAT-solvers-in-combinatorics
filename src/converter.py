from pathlib import Path
from typing import List, Optional, Dict
import subprocess
import tempfile
import sys
import os
from .custom_types import *


class Converter:
    def __init__(self, converter_cfg: FormulatorConfig, metadata: FormatMetadata, use_temp: bool = True) -> None:
        self.converter_cfg = converter_cfg
        self.use_temp = use_temp
        self.formulator_type = metadata.format_type
        self.suffix = metadata.suffix

        self._modes = {
            "stdout": self._handle_stdout,
            #"path_list": self._handle_path_list, TODO
            #"directory": self._handle_directory_output
        }

    
    def convert(self, problem: FileConfig, output_path: Path = None) -> Optional[List[TestCase]]:
        mode = self.converter_cfg.output_mode
        handler = self._modes.get(mode)
        if handler is None:
            raise ValueError(f"Unsupported output mode: {mode}")

        problem_name = problem.name if problem.name else output_path.stem
        problem_path = problem.path if problem.path else None
        if problem_path is None:
            raise ValueError(f"Problem {problem_name} does not have a valid path for conversion.")

        try:
            return handler(problem, output_path)
           # output_path.parent.mkdir(parents=True, exist_ok=True)
            
        except subprocess.CalledProcessError as e:
            print(f"Error: Converter '{self.converter_cfg.name}' failed (Exit {e.returncode}).", file=sys.stderr)
            if output_path.exists():
                output_path.unlink()
            if e.stderr: print(f"Stderr: {e.stderr}", file=sys.stderr)
        except FileNotFoundError:
            print(f"Error: Executable '{self.converter_cfg.cmd}' not found.", file=sys.stderr)
        except Exception as e:
            print(f"Exception during conversion: {e}", file=sys.stderr)
            if mode == "stdout" and  output_path and output_path.exists():
                output_path.unlink()
            
        return None
    
    def _handle_stdout(self, problem: FileConfig, output_path: Path) -> Optional[List[TestCase]]:
        if output_path is None:
            raise ValueError("Output path must be provided for stdout mode.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = self._build_cmd(problem)
        with open(output_path, "w") as out_file:
            proc = subprocess.run(
                cmd, 
                stdout=out_file, 
                stderr=subprocess.PIPE, 
                text=True,
                check=True
            )
        tc = self._make_tc(problem, output_path)
        return [tc]
    
    def _build_cmd(self, problem: FileConfig) -> List[str]:
        return [self.converter_cfg.cmd] + self.converter_cfg.options + [str(problem.path)]
    
    def _make_tc(self, problem: FileConfig, path: Path, index: Optional[int] = None) -> TestCase:
        index_suffix = f"_{index}" if index is not None else ""
        unique_name = f"{problem.name}{index_suffix}"

        tc = TestCase(
            name=f"{unique_name}",
            path=path,
            problem_cfg=problem,
            formulator_cfg=self.converter_cfg,
            tc_type=self.formulator_type,
        )
        tc.generated_files.append(path)
        return tc
