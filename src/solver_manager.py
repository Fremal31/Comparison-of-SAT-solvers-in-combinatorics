from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path
import shutil
import copy
import logging
import os
import sys
import queue

from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Callable
from utils import make_error_result


from custom_types import (
    Config, Result, RawResult, FileConfig, FormulatorConfig, ExecConfig, TestCase,
    ExecutionTriplet, RunnerError, ConversionError, ThreadConfig,
    STATUS_BREAKER_ERROR, STATUS_ERROR, STATUS_TIMEOUT, CRITICAL_STATUSES, NULL_FORMULATOR, NULL_BREAKER
)
from factory import get_converter, get_runner
from metadata_registry import resolve_format_metadata
from format_types import ExperimentContext, ConversionTask, SolvingTask
from converter import Converter
from runner import Runner
from generic_executor import GenericExecutor
from core_allocator import CoreAllocator
from triplet_generator import build_triplets
from breaker import SymmetryBreaker

logger = logging.getLogger(__name__)


class MultiSolverManager:
    """
    Orchestrates the two-phase benchmark pipeline: parallel conversion of
    (problem, formulator) pairs followed by parallel solver execution.
    """

    def __init__(self, config: Config) -> None:
        """
        Sets up the working directory, filters enabled components from *config*,
        and generates the full list of execution triplets.

        Raises ValueError if *working_dir* is non-empty and *delete_working_dir* is False.
        """
        self.work_dir = self._setup_working_dir(config)
        self.use_hardlink: bool = config.use_hardlink
        logger.debug("Use hardlink is set to %s", self.use_hardlink)
        self.timeout: float = float(config.timeout)
        #self.max_threads: int = config.max_threads

        self.thread_cfg: ThreadConfig = config.thread_config

        #self.core_pool: Optional[queue.Queue] = self._setup_cpu_resources()
        self.core_allocator: CoreAllocator = self._setup_cpu_resources()

        self.ensure_cleanup_on_crash: bool = self.thread_cfg.ensure_cleanup_on_crash
        #print(self.ensure_cleanup_on_crash)
        self.executor: GenericExecutor = GenericExecutor(cleanup_on_crash=self.ensure_cleanup_on_crash)

        self.breaker: SymmetryBreaker = SymmetryBreaker(executor=self.executor)

        self.results: List[Result] = []

        self.enabled_problems: List[FileConfig] = []
        for f in config.files:
            if f.enabled:
                self.enabled_problems.append(f)

        self.enabled_formulators: List[FormulatorConfig] = []
        for f in config.formulators:
            if f.enabled:
                self.enabled_formulators.append(f)

        self.enabled_breakers: List[ExecConfig] = []
        for b in config.breakers:
            if b.enabled:
                self.enabled_breakers.append(b)

        self.enabled_solvers: List[ExecConfig] = []
        for s in config.solvers:
            if s.enabled:
                self.enabled_solvers.append(s)

        self.test_case: List[TestCase] = []
        self.all_triplets: List[ExecutionTriplet] = []
        self.test_case, self.all_triplets = build_triplets(config=config, problems=self.enabled_problems, formulators=self.enabled_formulators, solvers=self.enabled_solvers, breakers=self.enabled_breakers)
        if logger.isEnabledFor(logging.DEBUG):
            triplets_str = "\n".join([
                f"  [{t.problem.name}, "
                f"{t.formulator.name if t.formulator else 'None'}, "
                f"{t.breaker.name if t.breaker else 'None'}, "
                f"{t.solver.name}]" 
                for t in self.all_triplets
            ])
            logger.debug("Triplets expanded:\n%s", triplets_str)
            test_case_str = triplets_str = "\n".join([
                f"  [{tc.name}, "
                f"{tc.path}, "
                f"{tc.tc_type}, "
                f"{tc.generated_files}]" 
                for tc in self.test_case
            ])
            logger.debug("TestCases expanded:\n%s", test_case_str)


    def _setup_cpu_resources(self) -> Optional[CoreAllocator]:
        """Pins the Boss process and prepares the core pool for solvers."""
        if not self.thread_cfg.allowed_cores:
            return None

        available_cores: List[int] = list(self.thread_cfg.allowed_cores)

        if not available_cores:
            return None

        core_allocator: CoreAllocator = CoreAllocator(core_ids=available_cores)
        
        logger.debug("Core allocator initialized with %d cores: %s", len(available_cores), available_cores)
        return core_allocator

    @staticmethod
    def _setup_working_dir(config: Config) -> Path:
        """Validates, optionally clears, and creates the working directory. Returns the resolved Path."""
        if not config.working_dir:
            raise ValueError("Working directory must be specified in config")
        work_dir = Path(config.working_dir)
        if work_dir.exists() and not config.delete_working_dir:
            if any(work_dir.iterdir()):
                raise ValueError(f"Working directory {work_dir} already exists and is not empty. Set 'delete_working_dir' to true in config to automatically clear it before running.")
        if work_dir.exists() and config.delete_working_dir:
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def _get_experiment_paths(self, problem_cfg: FileConfig, formulator_cfg: FormulatorConfig) -> ExperimentContext:
        """Builds and returns the working directory structure for a (problem, formulator) pair."""
        f_metadata = resolve_format_metadata(format_type=formulator_cfg.formulator_type)
        base_path = self.work_dir / problem_cfg.name / formulator_cfg.name
        log_dir: Path = base_path / "logs"
        
        log_dir.mkdir(parents=True, exist_ok=True)
        return ExperimentContext(
            base_path=base_path,
            log_dir=log_dir,
            format_info=f_metadata
        )


    def _prepare_task_file(self, source_path: Path, target_path: Path) -> None:
        """
        Prepares a file for a task by either hardlinking or copying it.
        If hardlinking is enabled but fails, it automatically falls back to copying.
        """
        if target_path.exists():
            return
        if self.use_hardlink:
            try:
                os.link(source_path, target_path)
                return
            except Exception as e:
                logger.warning(
                    f"Hardlink failed for {source_path.name}, falling back to copy. Reason: {e}"
                )
        shutil.copy2(source_path, target_path)

    def _add_solver_tasks(self, triplet: ExecutionTriplet, test_cases: List[TestCase], conversion_metrics: Optional[RawResult] = None) -> List[SolvingTask]:
        """Creates a SolvingTask for each test case in the given triplet."""
        solver_tasks: List[SolvingTask] = []
        problem_cfg: Optional[FileConfig] = triplet.problem
        formulator_cfg: Optional[FormulatorConfig] = triplet.formulator

        if problem_cfg is None or formulator_cfg is None:
            return solver_tasks

        context: ExperimentContext = self._get_experiment_paths(problem_cfg=problem_cfg, formulator_cfg=formulator_cfg)
        for tc in test_cases:
            orig_path: Path = Path(tc.path)
            #output_path: Path = context.base_path / f"{task.problem.name}{context.format_info.suffix}"
            unique_filename = f"{orig_path.stem}.{triplet.solver.name}{orig_path.suffix}"
            unique_path: Path = orig_path.parent / unique_filename
            #unique_path: Path = context.base_path / unique_filename

            self._prepare_task_file(source_path=orig_path, target_path=unique_path)

            tc.generated_files.append(unique_path)
            
            unique_tc = TestCase(
            name=tc.name,
            path=unique_path,
            problem_cfg=tc.problem_cfg,
            formulator_cfg=tc.formulator_cfg,
            tc_type=tc.tc_type,
            generated_files=[unique_path],
            enabled=tc.enabled
        )

            solver_task: SolvingTask = SolvingTask(
                triplet=triplet,
                test_case=unique_tc,
                work_dir=context,
                timeout=self.timeout,
                conversion_metrics=conversion_metrics
            )
            solver_tasks.append(solver_task)
        return solver_tasks
    
    @staticmethod
    def _shuffle_tasks(tasks: List[SolvingTask]) -> List[SolvingTask]:
        """
        Reorders tasks using a round-robin approach based on the problem name.
        
        This minimizes hardware resource contention (L3 cache/Memory bandwidth) 
        by ensuring that identical problems are spaced as far apart in the 
        execution queue as possible.
        """
        tasks_by_problem: Dict[str, List[SolvingTask]] = defaultdict(list)
        for task in tasks:
            tasks_by_problem[task.test_case.name].append(task)

        interleaved_tasks: List[SolvingTask] = []
        problem_names: List[str] = sorted(tasks_by_problem.keys()) # deterministic sorting - ensure reproducability
        
        while tasks_by_problem:
            for name in problem_names:
                if name in tasks_by_problem:
                    interleaved_tasks.append(tasks_by_problem[name].pop(0))
                    
                    if not tasks_by_problem[name]:
                        del tasks_by_problem[name]
        
        return interleaved_tasks

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

    def run_all_experiments_parallel_separate(self, call_on_result: Optional[Callable[[Result], None]] = None) -> List[Result]:
        """
        Runs the full two-phase benchmark pipeline. 
        
        In Phase 1, each unique
        (problem, formulator) pair is converted exactly once in parallel and the
        results cached. 
        
        In Phase 2, all solver tasks run in parallel reusing the
        cached converted files.

        *on_result* is a function, which is called with each Result as it completes,
        before the next result is processed. This runs in the main thread so no
        locking is needed.

        Returns one Result per solver task.
        """  
        unique_conversions: Dict[Tuple[FileConfig, FormulatorConfig], ConversionTask] = {}

        for t in self.all_triplets:
            if t.formulator.name == NULL_FORMULATOR:
                continue
            key = (t.problem.name, t.formulator.name)
            if key not in unique_conversions:
                context: ExperimentContext = self._get_experiment_paths(problem_cfg=t.problem, formulator_cfg=t.formulator)
                conversion_task = ConversionTask(
                    problem=t.problem,
                    config=t.formulator,
                    work_dir=context,
                    timeout=self.timeout
                )
                unique_conversions[key] = conversion_task
        
        problem_formulator_results: Dict[Tuple[str, str], Tuple[List[TestCase], Optional[RawResult]]] = {}

        for test_case in self.test_case:
            key = (test_case.problem_cfg.name if test_case.problem_cfg else test_case.name, test_case.formulator_cfg.name if test_case.formulator_cfg else NULL_FORMULATOR)
            problem_formulator_results[key] = ([test_case], None)
        
        if unique_conversions:
            logger.info("--- Converting %d (problem, formulator) pairs ---", len(unique_conversions))
            unique_conversions_tuples: List[ConversionTask] = list(unique_conversions.values())
            with ThreadPoolExecutor(max_workers=self.thread_cfg.max_threads) as executor:
                batch_results: List[Tuple[List[TestCase], Optional[RawResult]]] = list(executor.map(self._worker_convert, unique_conversions_tuples))
                for problem_formulator_pair, (test_cases, raw) in zip(unique_conversions.keys(), batch_results):
                    problem_formulator_results[problem_formulator_pair] = (test_cases, raw)
                    self.test_case.extend(test_cases)

        solver_tasks: List[SolvingTask] = []

        for t in self.all_triplets:
            entry = problem_formulator_results.get((t.problem.name, t.formulator.name))
            test_cases = entry[0] if entry else []
            conv_raw = entry[1] if entry else None
            solver_tasks.extend(self._add_solver_tasks(triplet=t, test_cases=test_cases, conversion_metrics=conv_raw))

        solver_tasks = self._shuffle_tasks(solver_tasks)

        logger.info("--- Solving %d runs ---", len(solver_tasks))
        self.results = []

        if solver_tasks:
            with ThreadPoolExecutor(max_workers=self.thread_cfg.max_threads) as executor:
                try:
                    futures: Dict[Future[Result], SolvingTask] = {executor.submit(self._worker_solve, task): task for task in solver_tasks}
                    for future in as_completed(futures):
                        result: Result = future.result()
                        self.results.append(result)
                        if call_on_result:
                            call_on_result(result)

                        cores_str: str = f"Cores {result.cores_used}" if result.cores_used else "No Pinning"
                        breaker: str = "_" + result.breaker if result.breaker != NULL_BREAKER else ""
                        logger.info("[%d/%d] Done: %s%s on %s", len(self.results), len(solver_tasks), result.solver, breaker, result.problem)
                        logger.info("Result: Solver %s%s, Problem %s, Status %s, Time %.2fs, %s, Error: %s", result.solver, breaker, result.problem, result.status, result.total_time, cores_str, result.error if result.error else 'None')
                        
                except KeyboardInterrupt:
                    logger.error("Interrupted by user. Attempting to cancel remaining tasks and shutting down executor...")
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                finally:
                    self._delete_test_case_generated_files()
                    logger.info("Completed %d/%d solver runs.", len(self.results), len(solver_tasks))
        return self.results

    @staticmethod
    def _worker_convert(task: ConversionTask) -> Tuple[List[TestCase], Optional[RawResult]]:
        """
        Phase 1 worker that converts a single (problem, formulator) pair.

        Returns (test_cases, raw_result) on success, or ([], None) on failure.
        """
        context: ExperimentContext = task.work_dir
        output_path: Path = context.base_path / f"{task.problem.name}{context.format_info.suffix}"
        try:
            converter: Converter = get_converter(form_cfg=task.config)
            test_cases, raw = converter.convert(problem=task.problem, output_path=output_path, timeout=task.timeout)
            logger.info("[CONVERT] %s using %s: %.2fs, peak mem %.1fMB",
                        task.problem.name, task.config.name, raw.time, raw.memory_peak_mb)
            return test_cases, raw
        except ConversionError as e:
            logger.error("[CONVERT] Failed: %s using %s. Error: %s", task.problem.name, task.config.name, e)
            return [], None
        except Exception as e:
            logger.error("[CONVERT] Critical Error: %s: %s", task.problem.name, e)
            return [], None


    def _worker_solve(self, task: SolvingTask) -> Result:
        """
        Phase 2 worker that optionally applies symmetry breaking before running
        the solver.

        If breaking fails the breaker error Result is returned directly without
        invoking the solver.
        """
        triplet: ExecutionTriplet = task.triplet
        solver_cfg: ExecConfig = triplet.solver
        breaker_cfg: Optional[ExecConfig] = triplet.breaker
    
        test_case: TestCase = task.test_case
        timeout: float = task.timeout
        work_dir: ExperimentContext = task.work_dir
        
        p_type: str = task.test_case.tc_type if task.test_case.tc_type and task.test_case.tc_type != "UNKNOWN" else (triplet.formulator.formulator_type if triplet.formulator else "UNKNOWN")
        breaker_name: str = breaker_cfg.name if breaker_cfg is not None else NULL_BREAKER
        if breaker_cfg is not None:
            log_name = f"{test_case.name}.{solver_cfg.name}_{breaker_cfg.name}.out"
        else:
            log_name = f"{test_case.name}.{solver_cfg.name}.out"
        path_out = work_dir.log_dir / log_name
        breaker_result: Optional[Result] = None
        
        assigned_cores: List[int] = []
        if self.core_allocator:
            req = task.triplet.solver.threads
            if task.triplet.breaker:
                req = max(req, task.triplet.breaker.threads)
                #print(req)
            assigned_cores = self.core_allocator.request(count=req)
        try:
            if breaker_cfg:            
                processed_tc, breaker_result = self.breaker.apply(task=task, core_ids=assigned_cores)
                if processed_tc is None or breaker_result.status in CRITICAL_STATUSES:
                    return breaker_result
                
                test_case = processed_tc
                breaker_metrics: Result = breaker_result
            else:
                breaker_metrics = None
            
            break_time: float = breaker_metrics.time if breaker_metrics else 0.0
            remaining_timeout: float = max(0.0, timeout - break_time)
            if remaining_timeout <= 0.0:
                return make_error_result(
                    triplet, test_case, breaker_name, STATUS_TIMEOUT,
                    "No time remaining after symmetry breaking.", break_time
                )

            try:
                runner: Runner = get_runner(problem_type=p_type, solv_cfg=solver_cfg, executor=self.executor)
                result: Result = runner.run(input_file=test_case, timeout=remaining_timeout, output_path=path_out, core_ids=assigned_cores)

                result.solver = solver_cfg.name
                result.problem = test_case.name
                result.parent_problem = triplet.problem.name
                result.breaker = breaker_name
                
                result.formulator = test_case.formulator_cfg.name if test_case.formulator_cfg else None
                #result.cores_used = assigned_cores
                if task.conversion_metrics:
                    result.conversion_time = task.conversion_metrics.time
                    result.conversion_cpu_time = task.conversion_metrics.cpu_time
                    result.conversion_memory_mb = task.conversion_metrics.memory_peak_mb

                if breaker_metrics:
                    result.break_time = breaker_metrics.time
                    result.break_cpu_time = breaker_metrics.cpu_time
                    result.break_memory_mb = breaker_metrics.memory_peak_mb
                return result

            except RunnerError as e:
                return make_error_result(
                    triplet, test_case, breaker_name, STATUS_ERROR,
                    f"Runner Failure: {e}", break_time
                )
            except Exception as e:
                return make_error_result(
                    triplet, test_case, breaker_name, STATUS_ERROR,
                    str(e), break_time
                )
        finally:
            if self.core_allocator:
                self.core_allocator.release(cores=assigned_cores)
            