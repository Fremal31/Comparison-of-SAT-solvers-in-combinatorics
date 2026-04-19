import logging
import os
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from breaker import SymmetryBreaker
from conversion_phase import run_conversion_phase, ConversionResults
from core_allocator import CoreAllocator
from custom_types import (
    Config, ExecConfig, ExecutionTriplet, FileConfig, FormulatorConfig,
    RawResult, Result, TestCase, ThreadConfig,
    Status, NULL_BREAKER, NULL_FORMULATOR, NULL_PROBLEM, NULL_SOLVER,
)
from format_types import ExperimentContext, ConversionTask, SolvingTask
from generic_executor import GenericExecutor
from metadata_registry import resolve_format_metadata
from solving_phase import SolvingPhase, shuffle_tasks
from triplet_generator import build_triplets
from utils import make_error_result

logger = logging.getLogger(__name__)


class MultiSolverManager:
    """
    Orchestrates the two-phase benchmark pipeline: parallel conversion of
    (problem, formulator) pairs followed by parallel solver execution.
    """

    def __init__(self, config: Config) -> None:
        self.work_dir = self._setup_working_dir(config)
        self.use_hardlink: bool = config.use_hardlink
        self.timeout: float = float(config.timeout)
        self.thread_cfg: ThreadConfig = config.thread_config
        self.core_allocator: Optional[CoreAllocator] = self._setup_cpu_resources()
        self.executor: GenericExecutor = GenericExecutor(
            cleanup_on_crash=self.thread_cfg.ensure_cleanup_on_crash
        )
        self.breaker: SymmetryBreaker = SymmetryBreaker(executor=self.executor)
        self.solving_phase = SolvingPhase(self.executor, self.breaker, self.core_allocator)
        self.results: List[Result] = []

        self.enabled_problems: List[FileConfig] = [f for f in config.files if f.enabled]
        self.enabled_formulators: List[FormulatorConfig] = [f for f in config.formulators if f.enabled]
        self.enabled_breakers: List[ExecConfig] = [b for b in config.breakers if b.enabled]
        self.enabled_solvers: List[ExecConfig] = [s for s in config.solvers if s.enabled]

        self.test_case: List[TestCase] = []
        self.all_triplets: List[ExecutionTriplet] = []
        self.test_case, self.all_triplets = build_triplets(
            config=config,
            problems=self.enabled_problems,
            formulators=self.enabled_formulators,
            solvers=self.enabled_solvers,
            breakers=self.enabled_breakers,
        )
        if logger.isEnabledFor(logging.DEBUG):
            triplets_str = "\n".join([
                f"  [{t.problem.name if t.problem else NULL_PROBLEM}, "
                f"{t.formulator.name if t.formulator else NULL_FORMULATOR}, "
                f"{t.breaker.name if t.breaker else NULL_BREAKER}, "
                f"{t.solver.name if t.solver else NULL_SOLVER}]"
                for t in self.all_triplets
            ])
            logger.debug("Triplets expanded:\n%s", triplets_str)
            test_case_str = "\n".join([
                f"  [{tc.name}, {tc.path}, {tc.tc_type}, {tc.generated_files}]"
                for tc in self.test_case
            ])
            logger.debug("TestCases expanded:\n%s", test_case_str)

    # -------------------------------------------------------------------------
    # Setup helpers
    # -------------------------------------------------------------------------

    def _setup_cpu_resources(self) -> Optional[CoreAllocator]:
        """Prepares the core pool for solvers if allowed_cores is configured."""
        if not self.thread_cfg.allowed_cores:
            return None
        available = list(self.thread_cfg.allowed_cores)
        if not available:
            return None
        logger.debug("Core allocator initialized with %d cores: %s", len(available), available)
        return CoreAllocator(core_ids=available)

    @staticmethod
    def _setup_working_dir(config: Config) -> Path:
        """Validates, optionally clears, and creates the working directory."""
        if not config.working_dir:
            raise ValueError("Working directory must be specified in config")
        work_dir = Path(config.working_dir)
        if work_dir.exists() and not config.delete_working_dir:
            if any(work_dir.iterdir()):
                raise ValueError(
                    f"Working directory {work_dir} already exists and is not empty. "
                    "Set 'delete_working_dir' to true in config to automatically clear it."
                )
        if work_dir.exists() and config.delete_working_dir:
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    # -------------------------------------------------------------------------
    # Task-building helpers
    # -------------------------------------------------------------------------

    def _get_experiment_paths(
        self, problem_cfg: FileConfig, formulator_cfg: FormulatorConfig
    ) -> ExperimentContext:
        """Builds working directory structure for a (problem, formulator) pair."""
        f_metadata = resolve_format_metadata(format_type=formulator_cfg.formulator_type)
        base_path = self.work_dir / problem_cfg.name / formulator_cfg.name
        log_dir = base_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return ExperimentContext(base_path=base_path, log_dir=log_dir, format_info=f_metadata)

    def _prepare_task_file(self, source_path: Path, target_path: Path) -> None:
        """Hardlinks or copies *source_path* to *target_path*, skipping if already present."""
        if target_path.exists():
            return
        if self.use_hardlink:
            try:
                os.link(source_path, target_path)
                return
            except Exception as e:
                logger.warning("Hardlink failed for %s, falling back to copy. Reason: %s", source_path.name, e)
        shutil.copy2(source_path, target_path)

    def _add_solver_tasks(
        self,
        triplet: ExecutionTriplet,
        test_cases: List[TestCase],
        conversion_metrics: Optional[RawResult] = None,
    ) -> List[SolvingTask]:
        """Creates a SolvingTask for each test case in the given triplet."""
        solver_tasks: List[SolvingTask] = []
        if triplet.problem is None or triplet.formulator is None:
            return solver_tasks
        if not triplet.solver:
            raise ValueError("Solver is None")

        context = self._get_experiment_paths(triplet.problem, triplet.formulator)
        for tc in test_cases:
            orig_path = Path(tc.path)
            unique_filename = f"{orig_path.stem}.{triplet.solver.name}{orig_path.suffix}"
            unique_path = orig_path.parent / unique_filename
            self._prepare_task_file(source_path=orig_path, target_path=unique_path)
            tc.generated_files.append(unique_path)
            unique_tc = TestCase(
                name=tc.name,
                path=unique_path,
                problem_cfg=tc.problem_cfg,
                formulator_cfg=tc.formulator_cfg,
                tc_type=tc.tc_type,
                generated_files=[unique_path],
                enabled=tc.enabled,
            )
            solver_tasks.append(SolvingTask(
                triplet=triplet,
                test_case=unique_tc,
                work_dir=context,
                timeout=self.timeout,
                conversion_metrics=conversion_metrics,
            ))
        return solver_tasks

    def _delete_test_case_generated_files(self) -> None:
        for tc in self.test_case:
            logger.debug("TestCase %s cleanup: checking %d generated files", tc.name, len(tc.generated_files))
            for generated in tc.generated_files:
                try:
                    p = Path(generated)
                    if p.is_file():
                        p.unlink(missing_ok=True)
                        logger.debug("Deleted: %s", generated)
                except Exception as e:
                    logger.warning("Could not clean up temporary file %s: %s", generated, e)

    # -------------------------------------------------------------------------
    # Pipeline
    # -------------------------------------------------------------------------

    def run_all_experiments_parallel_separate(
        self, call_on_result: Optional[Callable[[Result], None]] = None
    ) -> List[Result]:
        """
        Runs the full two-phase benchmark pipeline.

        Phase 1 converts each unique (problem, formulator) pair exactly once
        in parallel and caches the results. Phase 2 runs all solver tasks in
        parallel, reusing the cached converted files.

        *call_on_result* is called with each Result as it completes (main
        thread, no locking needed). Returns one Result per solver task.
        """
        unique_conversions = self._build_conversion_tasks()
        pre_encoded = self._get_pre_encoded()

        pf_results, new_tcs = run_conversion_phase(
            unique_conversions, pre_encoded, self.thread_cfg.max_threads
        )
        self.test_case.extend(new_tcs)

        solver_tasks, failed_results = self._build_solver_tasks(pf_results)
        solver_tasks = shuffle_tasks(solver_tasks)

        self.results = list(failed_results)
        for err in failed_results:
            if call_on_result:
                call_on_result(err)

        solve_results = self.solving_phase.run(
            solver_tasks,
            self.thread_cfg.max_threads,
            call_on_result,
            on_complete=self._delete_test_case_generated_files,
        )
        self.results.extend(solve_results)
        return self.results

    def _build_conversion_tasks(self) -> Dict[Tuple[str, str], ConversionTask]:
        """Deduplicates conversion work: one task per unique (problem, formulator) pair."""
        unique: Dict[Tuple[str, str], ConversionTask] = {}
        for t in self.all_triplets:
            if not t.formulator:
                raise ValueError("Formulator is None.")
            if t.formulator.name == NULL_FORMULATOR:
                continue
            if not t.problem:
                raise ValueError("Problem is None.")
            key: Tuple[str, str] = (t.problem.name, t.formulator.name)
            if key not in unique:
                unique[key] = ConversionTask(
                    problem=t.problem,
                    config=t.formulator,
                    work_dir=self._get_experiment_paths(t.problem, t.formulator),
                    timeout=self.timeout,
                )
        return unique

    def _get_pre_encoded(self) -> ConversionResults:
        """Returns the initial results dict seeded with pre-encoded test cases."""
        pre: ConversionResults = {}
        for tc in self.test_case:
            key = (
                tc.problem_cfg.name if tc.problem_cfg else tc.name,
                tc.formulator_cfg.name if tc.formulator_cfg else NULL_FORMULATOR,
            )
            pre[key] = ([tc], None)
        return pre

    def _build_solver_tasks(
        self, pf_results: ConversionResults
    ) -> Tuple[List[SolvingTask], List[Result]]:
        """
        Builds SolvingTasks from conversion results. Returns the task list and
        a list of error Results for any triplets whose conversion failed.
        """
        solver_tasks: List[SolvingTask] = []
        failed: List[Result] = []

        for t in self.all_triplets:
            if not t.problem or not t.formulator:
                raise ValueError("Keys problem and formulator are None.")
            entry = pf_results.get((t.problem.name, t.formulator.name))
            test_cases = entry[0] if entry else []
            conv_raw = entry[1] if entry else None

            if entry is not None and not test_cases:
                dummy_tc = TestCase(
                    name=t.problem.name,
                    path=str(t.problem.path),
                    problem_cfg=t.problem,
                    formulator_cfg=t.formulator,
                    tc_type=t.formulator.formulator_type,
                )
                failed.append(make_error_result(
                    triplet=t,
                    test_case=dummy_tc,
                    breaker_name=NULL_BREAKER,
                    status=Status.ERROR,
                    error=f"Conversion failed for '{t.problem.name}' using '{t.formulator.name}'",
                ))
                continue

            solver_tasks.extend(self._add_solver_tasks(t, test_cases, conv_raw))

        return solver_tasks, failed
