from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

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

    _ConvertResult = Tuple[List[TestCase], RawResult]
    _Handler = Callable[[FileConfig, Optional[Path]], _ConvertResult]

    def __init__(self, converter_cfg: FormulatorConfig, metadata: FormatMetadata,
                 executor: Optional[GenericExecutor] = None) -> None:
        self.converter_cfg: FormulatorConfig = converter_cfg
        self.formulator_type: str = metadata.format_type
        self.suffix: str = metadata.suffix
        self._options: List[str] = converter_cfg.options if converter_cfg.options else []
        self._cmd: str = converter_cfg.cmd
        self._executor: GenericExecutor = executor or GenericExecutor()

        self._modes: Dict[str, Converter._Handler] = {
            "stdout": self._handle_stdout,
            "stdout_multi": self._handle_stdout_multi,
            "directory": self._handle_directory,
        }
        self._handler: Optional[Converter._Handler] = self._modes.get(converter_cfg.output_mode)
        if self._handler is None:
            raise ConversionError(
                f"Unsupported output mode '{converter_cfg.output_mode}' for formulator '{converter_cfg.name}'. "
                f"Valid modes: {list(self._modes.keys())}"
            )

    
    def convert(self, problem: FileConfig, output_path: Path, timeout: Optional[float] = None) -> Tuple[List[TestCase], RawResult]:
        """
        Converts *problem* to a formula file at *output_path* using the configured
        formulator. Dispatches to the appropriate handler based on *output_mode*.

        *timeout* limits the formulator subprocess execution time in seconds.
        If None, the formulator runs without a time limit.

        Returns (test_cases, raw_result) where raw_result contains the execution
        metrics for the entire conversion subprocess.

        Raises ConversionError if the output mode is unsupported, the problem path
        is missing, or the formulator subprocess fails.
        """
        self._timeout = timeout
        try:
            problem_name = problem.name if problem.name else output_path.stem
            if not problem.path:
                raise ConversionError(f"Problem {problem_name} does not have a valid path for conversion.")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if self._handler is None:
                raise ConversionError("Converter handler not initialized.")
            return self._handler(problem, output_path)
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(f"Unexpected error converting {problem.name}: {str(e)}")

    def _run_formulator(self, problem: FileConfig, output_path: Path) -> RawResult:
        """Runs the formulator subprocess and returns the RawResult.

        Raises ConversionError if the process fails to launch or exits non-zero.
        """
        result_cmd = build_cmd(self._cmd, self._options, problem.path, output_path)
        cmd = result_cmd.cmd
        stdin_path = str(problem.path) if result_cmd.use_stdin else None
        stdout_path = str(output_path) if result_cmd.use_stdout_pipe else None

        raw: RawResult = self._executor.execute(
            cmd=cmd, timeout=self._timeout,
            stdin_path=stdin_path, stdout_path=stdout_path
        )

        if raw.launch_failed:
            raise ConversionError(f"Converter {self.converter_cfg.name} failed to launch: {raw.error}")
        if raw.timed_out:
            raise ConversionError(f"Converter {self.converter_cfg.name} timed out after {self._timeout}s for {problem.name}")
        if raw.exit_code != 0:
            raise ConversionError(f"Converter {self.converter_cfg.name} failed (Exit {raw.exit_code}): {raw.stderr}")

        return raw

    def _handle_stdout(self, problem: FileConfig, output_path: Optional[Path] = None) -> Tuple[List[TestCase], RawResult]:
        """
        Runs the formulator and captures its stdout into a single output file.
        Returns a single-element TestCase list paired with the RawResult.
        """
        if output_path is None:
            raise ConversionError(f"Output path must be provided for {self.converter_cfg.output_mode}.")
        tmp_path: Path = output_path.with_suffix(output_path.suffix + ".tmp")

        raw = self._run_formulator(problem, tmp_path)

        if not tmp_path.exists() and raw.stdout:
            tmp_path.write_text(raw.stdout)

        tmp_path.replace(output_path)
        tc: TestCase = self._make_tc(problem=problem, path=output_path)
        return [tc], raw

    def _handle_stdout_multi(self, problem: FileConfig, output_path: Optional[Path] = None) -> Tuple[List[TestCase], RawResult]:
        """
        Runs the formulator once and splits its stdout into multiple formula files.
        Formulas are separated by blank lines. Each formula becomes a separate TestCase.

        Output files are named: {problem}_{index}{suffix}
        """
        if output_path is None:
            raise ConversionError(f"Output path must be provided for {self.converter_cfg.output_mode}.")
        tmp_path: Path = output_path.with_suffix(output_path.suffix + ".tmp")

        raw = self._run_formulator(problem, tmp_path)

        content = ""
        if tmp_path.exists():
            content = tmp_path.read_text()
            tmp_path.unlink()
        elif raw.stdout:
            content = raw.stdout

        if not content.strip():
            raise ConversionError(f"Converter {self.converter_cfg.name} produced empty output for {problem.name}.")

        formulas = self._split_formulas(content)
        if not formulas:
            raise ConversionError(f"Converter {self.converter_cfg.name} produced no formulas for {problem.name}.")

        test_cases: List[TestCase] = []
        out_dir = output_path.parent
        for i, formula in enumerate(formulas):
            file_path = out_dir / f"{problem.name}_{i}{self.suffix}"
            file_path.write_text(formula)
            tc = self._make_tc(problem=problem, path=file_path, index=i)
            test_cases.append(tc)

        return test_cases, raw

    def _handle_directory(self, problem: FileConfig, output_path: Optional[Path] = None) -> Tuple[List[TestCase], RawResult]:
        """
        Runs the formulator which writes output files to a directory.
        The {output} token in options is resolved to the output directory path.
        Each file with the correct suffix in the directory becomes a TestCase.
        """
        if output_path is None:
            raise ConversionError(f"Output path must be provided for {self.converter_cfg.output_mode}.")

        out_dir = output_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        raw = self._run_formulator(problem, out_dir)

        output_files = sorted(out_dir.glob(f"*{self.suffix}"))
        if not output_files:
            raise ConversionError(
                f"Converter {self.converter_cfg.name} produced no {self.suffix} files in {out_dir} for {problem.name}."
            )

        test_cases: List[TestCase] = []
        for i, file_path in enumerate(output_files):
            tc = self._make_tc(problem=problem, path=file_path, index=i)
            test_cases.append(tc)

        return test_cases, raw

    @staticmethod
    def _split_formulas(content: str) -> List[str]:
        """Splits concatenated formulas separated by blank lines.
        Each formula must be non-empty after stripping."""
        chunks = content.split("\n\n")
        return [chunk.strip() for chunk in chunks if chunk.strip()]

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
        #tc.generated_files.append(path)
        return tc
