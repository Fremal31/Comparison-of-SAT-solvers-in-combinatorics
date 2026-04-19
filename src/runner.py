from pathlib import Path
from typing import List, Optional
import shutil

from parser_strategy import ResultParser
from custom_types import (
    ExecConfig, TestCase, Result, RawResult, RunnerError,
    Status, EXIT_CODE_TIMEOUT, CRITICAL_STATUSES
)
from cmd_builder import build_cmd
from generic_executor import GenericExecutor



class Runner:
    """
    Executes a solver subprocess via GenericExecutor, maps the raw result
    into a domain Result, and parses the output using the configured strategy.
    """

    def __init__(self, config: ExecConfig, parser: ResultParser,
                 executor: Optional[GenericExecutor] = None) -> None:
        """
        Raises FileNotFoundError if *config.cmd* is not found on PATH or filesystem.
        """
        self._cmd = config.cmd
        if not self._cmd or self._cmd == "":
            raise ValueError(f"Empty cmd for {config.name}: {config.cmd}")
        if not shutil.which(self._cmd) and not Path(self._cmd).is_file():
            raise FileNotFoundError(f"Solver command or path not found: {self._cmd}")
        self._name: str = config.name
        self._options: List[str] = config.options
        self._type: str = config.solver_type
        self._parser: ResultParser = parser
        self._executor: GenericExecutor = executor or GenericExecutor()

    def run(self, input_file: TestCase, timeout: Optional[float],
            output_path: Optional[Path] = None, core_ids: Optional[List[int]] = None) -> Result:
        """
        Runs the solver on *input_file* and returns a populated Result.

        Delegates subprocess execution and resource monitoring to GenericExecutor.
        Maps the RawResult into a domain Result and applies the parser strategy.

        Raises ValueError if *output_path* is None, FileNotFoundError if the input
        file does not exist, and RunnerError on unexpected subprocess failures.
        """
        if output_path is None:
            raise ValueError(f"output_path must be provided for solver '{self._name}'")
        if not Path(input_file.path).exists():
            raise FileNotFoundError(f"Input file not found: {input_file.path}")
        if timeout is not None and timeout < 0:
            raise ValueError(f"Timeout must be positive for solver '{self._name}'")
        
        result_cmd = build_cmd(executable=self._cmd, options=self._options, input_path=input_file.path, output_path=output_path)
        cmd = result_cmd.cmd
        # use_stdout_pipe means "redirect stdout to a file" — pass the path
        # to the executor so it opens the file; otherwise stdout is captured in memory
        stdin_path = str(input_file.path) if result_cmd.use_stdin else None
        stdout_path = str(output_path) if result_cmd.use_stdout_pipe else None

        try:
            raw: RawResult = self._executor.execute(
                cmd=cmd, timeout=timeout,
                stdin_path=stdin_path, stdout_path=stdout_path, core_ids=core_ids
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            raise RunnerError(f"Internal Runner failure: {e}")

        result = self._map_raw_to_result(raw, input_file.name)
        
        if result.status not in CRITICAL_STATUSES and self._parser:
            p_path: Optional[Path] = output_path if output_path.exists() else None
            try:
                result = self._parser.parse(result=result, output_path=p_path)
            except Exception as e:
                result.status = Status.PARSER_ERROR
                result.error += f"\nParser failed: {e}"

        return result

    def _map_raw_to_result(self, raw: RawResult, problem_name: str) -> Result:
        """Maps a RawResult from GenericExecutor into a domain Result."""
        result = Result(
            solver=self._name,
            problem=problem_name,
            exit_code=raw.exit_code,
            time=raw.time,
            cpu_time=raw.cpu_time,
            cpu_usage_avg=raw.cpu_avg,
            cpu_usage_max=raw.cpu_max,
            memory_peak_mb=raw.memory_peak_mb,
            cores_used=raw.cores_used,
            stdout=raw.stdout.strip() if raw.stdout else "",
            stderr=raw.stderr.strip() if raw.stderr else "",
        )

        if raw.launch_failed:
            result.status = Status.ERROR
            result.error = raw.error or "Process failed to launch."
        elif raw.timed_out:
            result.status = Status.TIMEOUT
            result.exit_code = EXIT_CODE_TIMEOUT
            result.error = "Process killed due to timeout."
        elif raw.exit_code < 0:
            result.status = Status.EXIT_ERROR
            result.error = f"Process terminated by SIGNAL {abs(raw.exit_code)}"
        elif raw.error:
            result.error = raw.error

        return result
