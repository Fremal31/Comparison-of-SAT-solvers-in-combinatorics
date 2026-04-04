from pathlib import Path
from typing import List, Optional, Union
from contextlib import ExitStack
import subprocess


from custom_types import FileConfig, FormulatorConfig, TestCase, ConversionError
from format_types import FormatMetadata
from cmd_builder import build_cmd

class Converter:
    """
    Runs a formulator subprocess to convert a problem file into a solver-ready
    formula, writing the result to a temporary file before atomically replacing
    the output path.
    """

    def __init__(self, converter_cfg: FormulatorConfig, metadata: FormatMetadata) -> None:
        self.converter_cfg = converter_cfg
        self.formulator_type = metadata.format_type
        self.suffix = metadata.suffix
        self._options = converter_cfg.options if converter_cfg.options else []
        self._cmd = converter_cfg.cmd
        

        self._modes = {
            "stdout": self._handle_stdout,
            #"path_list": self._handle_path_list, TODO
            #"directory": self._handle_directory_output
        }

    
    def convert(self, problem: FileConfig, output_path: Path) -> Optional[List[TestCase]]:
        """
        Converts *problem* to a formula file at *output_path* using the configured
        formulator. Dispatches to the appropriate handler based on *output_mode*.

        Raises ConversionError if the output mode is unsupported, the problem path
        is missing, or the formulator subprocess fails.
        """
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
        except subprocess.CalledProcessError as e:
            raise ConversionError(f"Converter {self.converter_cfg.name} failed (Exit {e.returncode}): {e.stderr}")
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(f"Unexpected error converting {problem.name}: {str(e)}")
        
        
    
    def _handle_stdout(self, problem: FileConfig, output_path: Optional[Path] = None) -> Optional[List[TestCase]]:
        """
        Runs the formulator and captures its stdout into a temp file, then
        atomically replaces *output_path*. Returns a single-element TestCase list.
        """
        if output_path is None:
            raise ConversionError(f"Output path must be provided for {self.converter_cfg.output_mode}.")
        tmp_path: Path = output_path.with_suffix(output_path.suffix + ".tmp")
        result_cmd = build_cmd(self._cmd, self._options, problem.path, tmp_path)
        cmd, use_stdin, use_stdout = result_cmd.cmd, result_cmd.use_stdin, result_cmd.use_stdout_pipe

        self._run_process(cmd, use_stdin, use_stdout, problem.path, tmp_path)
        
        tmp_path.replace(output_path)
        tc: TestCase = self._make_tc(problem=problem, path=output_path)
        return [tc]

    def _run_process(self, cmd: List[str], use_stdin: bool, use_stdout: bool,
                     input_path: Union[str, Path], output_path: Path) -> subprocess.CompletedProcess[str]:
        """Runs *cmd* as a subprocess, optionally feeding *input_path* via stdin
        and redirecting stdout to *output_path*. Raises CalledProcessError on non-zero exit."""
        with ExitStack() as stack:
            in_stream = stack.enter_context(open(input_path, 'r')) if use_stdin else None
            out_stream = stack.enter_context(open(output_path, 'w')) if use_stdout else subprocess.PIPE

            return subprocess.run(
                cmd,
                stdin=in_stream,
                stdout=out_stream,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )


    def _make_tc(self, problem: FileConfig, path: Path, index: Optional[int] = None) -> TestCase:
        """Constructs a TestCase for a converted file, linking it back to its source *problem*."""
        index_suffix = f"_{index}" if index is not None else ""
        problem_name = problem.name if problem.name else path.stem
        unique_name = f"{problem_name}{index_suffix}"

        tc = TestCase(
            name=f"{unique_name}",
            path=path,
            problem_cfg=problem,
            formulator_cfg=self.converter_cfg,
            tc_type=self.formulator_type,
        )
        tc.generated_files.append(path)
        return tc
