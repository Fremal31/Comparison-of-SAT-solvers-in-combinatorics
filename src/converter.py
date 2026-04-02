from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict, TYPE_CHECKING
import subprocess
import tempfile
import sys
import os

if TYPE_CHECKING:
    from custom_types import *


class Converter:
    def __init__(self, converter_cfg: FormulatorConfig, metadata: FormatMetadata, use_temp: bool = True) -> None:
        self.converter_cfg = converter_cfg
        self.use_temp = use_temp
        self.formulator_type = metadata.format_type
        self.suffix = metadata.suffix
        self._options = converter_cfg.options if converter_cfg.options else []
        self._cmd = converter_cfg.cmd
        

        self._modes = {
            "stdout": self._handle_stdout,
            #"path_list": self._handle_path_list, TODO
            #"directory": self._handle_directory_output
        }

    
    def convert(self, problem: FileConfig, output_path: Path = None) -> Optional[List[TestCase]]:
        mode = self.converter_cfg.output_mode
        handler = self._modes.get(mode)
        if handler is None:
            raise ConversionError(f"Unsupported output mode: {mode}")
        
        problem_name = problem.name if problem.name else output_path.stem
        problem_path = problem.path if problem.path else None
        if problem_path is None:
            raise ConversionError(f"Problem {problem_name} does not have a valid path for conversion.")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            return handler(problem=problem, output_path=output_path)
           # output_path.parent.mkdir(parents=True, exist_ok=True)
            
        except subprocess.CalledProcessError as e:
            raise ConversionError(f"Converter {self.converter_cfg.name} failed (Exit {e.returncode}): {e.stderr}")
        except Exception as e:
            if isinstance(e, ConversionError):
                raise e
            raise ConversionError(f"Unexpected error converting {problem.name}: {str(e)}")
        
        return None
    
    def _handle_stdout(self, problem: FileConfig, output_path: Path) -> Optional[List[TestCase]]:
        if output_path is None:
            raise ConversionError(f"Output path must be provided for {self.converter_cfg.output_mode}.")
        tmp_path: Path = output_path.with_suffix(output_path.suffix + ".tmp")
        cmd, use_stdin, use_stdout = self._build_cmd(problem, tmp_path)

        self._run_process(cmd, use_stdin, use_stdout, problem.path, tmp_path)
        
        tmp_path.replace(output_path)
        tc: TestCase = self._make_tc(problem=problem, path=output_path)
        return [tc]

    def _run_process(self, cmd: List[str], use_stdin: bool, use_stdout: bool, 
                     input_path: Path, output_path: Path) -> subprocess.CompletedProcess:
        
        in_stream = open(input_path, 'r') if use_stdin else None
        out_stream = open(output_path, 'w') if use_stdout else subprocess.PIPE

        try:
            return subprocess.run(
                cmd,
                stdin=in_stream,
                stdout=out_stream,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
        finally:
            if in_stream:
                in_stream.close()
            if hasattr(out_stream, 'close'): out_stream.close()

    def _build_cmd(self, problem: FileConfig, output_path: Path) -> tuple[List[str], bool, bool]:
        contains_input: bool = any("{input}" in opt for opt in self._options)

        raw_args = self._options if contains_input else self._options + ["{input}"]
        
        final_args: List[str] = []
        use_stdin_h: bool = False
        use_stdout_h: bool = False
        output_present: bool = False

        i: int = 0
        while i < len(raw_args):
            arg = raw_args[i]

            if arg == "<":
                use_stdin_h = True
                if i + 1 < len(raw_args) and "{input}" in raw_args[i+1]:
                    i += 1
                i += 1
                continue
            if arg == ">":
                use_stdout_h = True

                if i + 1 < len(raw_args) and "{output}" in raw_args[i+1]:
                    output_present = True
                    i += 1
                i += 1
                continue

            if "{output}" in arg:
                output_present = True

            processed = arg.replace("{input}", str(problem.path))
            processed = processed.replace("{output}", str(output_path))
            final_args.append(processed)
            i += 1


        cmd: List[str] = [str(self._cmd)] + final_args

        # if used ">" - pipe
        # if used "{output}" - file
        # if used both - prefer file, but allow pipe if file is not present
        use_stdout_h = use_stdout_h or not output_present

        return cmd, use_stdin_h, use_stdout_h
    
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
