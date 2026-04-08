from pathlib import Path
from typing import List, Optional, Tuple

from custom_types import FileConfig, FormulatorConfig, TestCase, RawResult, ConversionError
from format_types import FormatMetadata
from cmd_builder import build_cmd
from generic_executor import GenericExecutor


class Converter:
    """
    Runs a formulator subprocess to convert a problem file into a solver-ready
    formula, writing the result to a temporary file before atomically replacing
    the output path.
    """

    def __init__(self, converter_cfg: FormulatorConfig, metadata: FormatMetadata,
                 executor: Optional[GenericExecutor] = None) -> None:
        self.converter_cfg = converter_cfg
        self.formulator_type = metadata.format_type
        self.suffix = metadata.suffix
        self._options = converter_cfg.options if converter_cfg.options else []
        self._cmd = converter_cfg.cmd
        self._executor = executor or GenericExecutor()

        self._modes = {
            "stdout": self._handle_stdout,
            #"path_list": self._handle_path_list, TODO
            #"directory": self._handle_directory_output
        }

    
    def convert(self, problem: FileConfig, output_path: Path) -> Tuple[List[TestCase], RawResult]:
        """
        Converts *problem* to a formula file at *output_path* using the configured
        formulator. Dispatches to the appropriate handler based on *output_mode*.

        Returns (test_cases, raw_result) where raw_result contains the execution
        metrics for the entire conversion subprocess.

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
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(f"Unexpected error converting {problem.name}: {str(e)}")
        
        
    
    def _handle_stdout(self, problem: FileConfig, output_path: Optional[Path] = None) -> Tuple[List[TestCase], RawResult]:
        """
        Runs the formulator and captures its stdout into a temp file, then
        atomically replaces *output_path*. Returns a single-element TestCase list
        paired with the RawResult from the conversion subprocess.
        """
        if output_path is None:
            raise ConversionError(f"Output path must be provided for {self.converter_cfg.output_mode}.")
        tmp_path: Path = output_path.with_suffix(output_path.suffix + ".tmp")
        result_cmd = build_cmd(self._cmd, self._options, problem.path, tmp_path)
        cmd = result_cmd.cmd
        stdin_path = str(problem.path) if result_cmd.use_stdin else None
        stdout_path = str(tmp_path) if result_cmd.use_stdout_pipe else None

        raw: RawResult = self._executor.execute(
            cmd=cmd, timeout=None,
            stdin_path=stdin_path, stdout_path=stdout_path
        )

        if raw.launch_failed:
            raise ConversionError(f"Converter {self.converter_cfg.name} failed to launch: {raw.error}")
        if raw.exit_code != 0:
            raise ConversionError(f"Converter {self.converter_cfg.name} failed (Exit {raw.exit_code}): {raw.stderr}")

        # If stdout was captured in memory (not piped to file), write it to tmp_path
        if stdout_path is None and raw.stdout:
            tmp_path.write_text(raw.stdout)

        tmp_path.replace(output_path)
        tc: TestCase = self._make_tc(problem=problem, path=output_path)
        return [tc], raw


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
