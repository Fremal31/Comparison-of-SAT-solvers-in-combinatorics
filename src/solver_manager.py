from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path
import shutil
import copy
import logging
import os
import sys
from typing import List, Dict, Optional, Tuple, Callable

from custom_types import (
    Config, Result, RawResult, FileConfig, FormulatorConfig, ExecConfig, TestCase,
    ExecutionTriplet, RunnerError, ConversionError,
    STATUS_BREAKER_ERROR, STATUS_ERROR, STATUS_TIMEOUT, CRITICAL_STATUSES, NULL_FORMULATOR, NULL_BREAKER
)
from factory import get_converter, get_runner
from metadata_registry import resolve_format_metadata
from format_types import ExperimentContext, ConversionTask, SolvingTask
from converter import Converter
from runner import Runner

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
        self.timeout: float = float(config.timeout)
        self.max_threads: int = config.max_threads
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
        self.test_case, self.all_triplets = self._build_triplets(config)

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

    def _build_triplets(self, config: Config) -> Tuple[List[TestCase], List[ExecutionTriplet]]:
        """Generates the full list of execution triplets and pre-encoded test cases from config."""
        test_cases: List[TestCase] = []

        if config.triplet_mode:
            for triplet in config.triplets:
                if triplet.test_case:
                    test_cases.append(triplet.test_case)
                    problem_cfg, formulator_cfg = self._create_dummy_problem_formulator_from_testcase(triplet.test_case)
                    triplet.problem = problem_cfg
                    triplet.formulator = formulator_cfg
            triplets = self._expand_triplets(config.triplets)
            logger.info("Triplet mode enabled: Using %d triplets (after expansion)", len(triplets))
            return test_cases, triplets

        for file_wo_converter in config.without_converter:
            if file_wo_converter.enabled:
                test_cases.append(TestCase(
                    name=file_wo_converter.name,
                    path=file_wo_converter.path,
                    problem_cfg=None,
                    formulator_cfg=None,
                    tc_type=file_wo_converter.tc_type
                ))
        triplets = self._generate_triplets(
            problems=self.enabled_problems, formulators=self.enabled_formulators,
            test_cases=test_cases, solvers=self.enabled_solvers, breakers=self.enabled_breakers
        )
        logger.info("Generated %d triplets from config", len(triplets))
        return test_cases, triplets

    def _expand_triplets(self, triplets: List[ExecutionTriplet]) -> List[ExecutionTriplet]:
        """
        Expands triplets that have no solver set into one triplet per compatible
        enabled solver. Triplets with a solver set are passed through unchanged.
        """
        expanded: List[ExecutionTriplet] = []
        for t in triplets:
            if t.solver is not None:
                expanded.append(t)
                continue

            target_type = t.formulator.formulator_type if t.formulator else None
            compatible = [s for s in self.enabled_solvers if s.solver_type == target_type]
            if not compatible:
                logger.warning("No compatible enabled solvers for type '%s' — skipping triplet.", target_type)
                continue

            for solver in compatible:
                expanded.append(ExecutionTriplet(
                    problem=t.problem,
                    formulator=t.formulator,
                    solver=solver,
                    breaker=t.breaker,
                    test_case=t.test_case
                ))
        return expanded

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

    def _add_solver_tasks(self, triplet: ExecutionTriplet, test_cases: List[TestCase], conversion_metrics: Optional[RawResult] = None) -> List[SolvingTask]:
        """Creates a SolvingTask for each test case in the given triplet."""
        solver_tasks: List[SolvingTask] = []
        problem_cfg: Optional[FileConfig] = triplet.problem
        formulator_cfg: Optional[FormulatorConfig] = triplet.formulator

        if problem_cfg is None or formulator_cfg is None:
            return solver_tasks

        context: ExperimentContext = self._get_experiment_paths(problem_cfg=problem_cfg, formulator_cfg=formulator_cfg)
        for tc in test_cases:
            solver_task: SolvingTask = SolvingTask(
                triplet=triplet,
                test_case=tc,
                work_dir=context,
                timeout=self.timeout,
                conversion_metrics=conversion_metrics
            )
            solver_tasks.append(solver_task)
        return solver_tasks

    def _create_dummy_problem_formulator_from_testcase(self, tc: TestCase) -> Tuple[FileConfig, FormulatorConfig]:
        """Creates placeholder FileConfig and FormulatorConfig for pre-encoded files that skip conversion."""
        dummy_prob_cfg = FileConfig(name=tc.name, path=tc.path)
        dummy_formulator = FormulatorConfig(
            name=NULL_FORMULATOR, 
            formulator_type=tc.tc_type, 
            cmd="", 
            enabled=True
        )
        return dummy_prob_cfg, dummy_formulator
    
    def _generate_triplets(self, problems: List[FileConfig], formulators: List[FormulatorConfig], test_cases: List[TestCase], solvers: List[ExecConfig], breakers: List[ExecConfig]) -> List[ExecutionTriplet]:
        """
        Generates the full cross-product of compatible execution combinations.

        Solver type must match formulator type for a pair to be included. 
        
        For each valid (problem, formulator, solver) combination, one triplet without a breaker
        is added, plus one additional triplet per compatible breaker.
        """
        all_triplets: List[ExecutionTriplet] = []
        compatible_solvers: List[ExecConfig] = []
        for problem in problems:
            for formulator in formulators:
                compatible_solvers = [solver for solver in solvers if solver.solver_type == formulator.formulator_type]
                for solver in compatible_solvers:
                    all_triplets.append(ExecutionTriplet(
                        problem=problem, 
                        formulator=formulator, 
                        solver=solver))
                    compatible_breakers: List[ExecConfig] = [breaker for breaker in breakers if breaker.solver_type == solver.solver_type]
                    for breaker in compatible_breakers:
                        all_triplets.append(ExecutionTriplet(
                            problem=problem, 
                            formulator=formulator, 
                            solver=solver, 
                            breaker=breaker))
                        
        compatible_solvers = []
        for tc in test_cases:
            dummy_prob_cfg, dummy_formulator = self._create_dummy_problem_formulator_from_testcase(tc=tc)
            
            compatible_solvers = [solver for solver in solvers if solver.solver_type == tc.tc_type]
            for solver in compatible_solvers:
                all_triplets.append(ExecutionTriplet(
                    problem=dummy_prob_cfg, 
                    formulator=dummy_formulator, 
                    solver=solver))
                for breaker in breakers:
                    if breaker.solver_type == tc.tc_type:
                        all_triplets.append(ExecutionTriplet(
                            problem=dummy_prob_cfg, 
                            formulator=dummy_formulator, 
                            solver=solver, 
                            breaker=breaker))
        return all_triplets
    
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
            key = (test_case.problem_cfg.name if test_case.problem_cfg else test_case.name, 
                   test_case.formulator_cfg.name if test_case.formulator_cfg else NULL_FORMULATOR)
            problem_formulator_results[key] = ([test_case], None)
        
        if unique_conversions:
            logger.info("--- Converting %d (problem, formulator) pairs ---", len(unique_conversions))
            unique_conversions_tuples: List[ConversionTask] = list(unique_conversions.values())
            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
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

        logger.info("--- Solving %d runs ---", len(solver_tasks))
        self.results = []

        if solver_tasks:
            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                try:
                    futures: Dict[Future[Result], SolvingTask] = {executor.submit(self._worker_solve, task): task for task in solver_tasks}
                    for future in as_completed(futures):
                        result: Result = future.result()
                        self.results.append(result)
                        if call_on_result:
                            call_on_result(result)
                        breaker: str = "_" + result.breaker if result.breaker != NULL_BREAKER else ""
                        logger.info("[%d/%d] Done: %s%s on %s", len(self.results), len(solver_tasks), result.solver, breaker, result.problem)
                        logger.info("Result: Solver %s%s, Problem %s, Status %s, Time %.2fs, Error: %s", result.solver, breaker, result.problem, result.status, result.total_time, result.error if result.error else 'None')
                        
                except KeyboardInterrupt:
                    logger.error("Interrupted by user. Attempting to cancel remaining tasks and shutting down executor...")
                    executor.shutdown(wait=False)
                    raise
                finally:
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


    @staticmethod
    def _make_error_result(triplet: ExecutionTriplet, test_case: TestCase,
                           breaker_name: str, status: str, error: str,
                           break_time: float = 0.0) -> Result:
        """Creates a Result for error/timeout cases with common fields pre-filled."""
        return Result(
            solver=triplet.solver.name,
            problem=test_case.name,
            parent_problem=triplet.problem.name if triplet.problem else test_case.name,
            breaker=breaker_name,
            formulator=triplet.formulator.name if triplet.formulator else None,
            status=status,
            error=error,
            time=-1.0,
            break_time=break_time
        )

    @staticmethod
    def _apply_symmetry_breaking(task: SolvingTask) -> Tuple[Optional[TestCase], Result]:
        """
        Runs the symmetry breaker on the test case and returns the modified test
        case along with the breaker result.

        Returns (None, Result with BREAKER_ERROR status) if breaking fails or
        produces an empty output file.
        """
        triplet: ExecutionTriplet = task.triplet
        test_case: TestCase = task.test_case
        timeout: float = task.timeout
        work_dir: ExperimentContext = task.work_dir
        breaker_cfg = triplet.breaker

        sym_path = work_dir.base_path / f"{test_case.name}.{triplet.solver.name}.{triplet.breaker.name}.sym.cnf"
        symmetry_test_case: TestCase = copy.deepcopy(test_case)
        
        if not breaker_cfg:
            raise ValueError(f"Breaker config missing for {triplet.solver.name}")

        br_runner = get_runner(problem_type=triplet.breaker.solver_type, solv_cfg=breaker_cfg)
        
        try:
            br_res = br_runner.run(input_file=test_case, timeout=timeout, output_path=sym_path)
            if br_res.status in CRITICAL_STATUSES:
                logger.error("[BREAKER] Error for %s: %s %s", test_case.name, br_res.stderr, br_res.error)
                br_res.breaker = br_res.solver
                br_res.solver = triplet.solver.name
                br_res.status = STATUS_BREAKER_ERROR
                return None, br_res
            
            if not sym_path.exists() or sym_path.stat().st_size == 0:
                msg = f"Symmetry breaker did not produce a valid output file at {sym_path}"
                logger.error("%s", msg)
                br_res.breaker = br_res.solver
                br_res.solver = triplet.solver.name
                br_res.status = STATUS_BREAKER_ERROR
                return None, br_res
            
            symmetry_test_case.path = sym_path
            test_case.generated_files.append(sym_path)
            return symmetry_test_case, br_res

        except RunnerError as e:
            msg = f"Breaker Process Failure: {str(e)}"
            logger.error("Critical error during symmetry breaking: %s", msg)
            return None, MultiSolverManager._make_error_result(
                triplet, test_case, breaker_cfg.name, STATUS_BREAKER_ERROR, msg
            )
        except Exception as e:
            msg = f"Unexpected exception: {str(e)}"
            logger.error("Error during symmetry breaking for %s: %s", test_case.name, msg)
            return None, MultiSolverManager._make_error_result(
                triplet, test_case, breaker_cfg.name, STATUS_BREAKER_ERROR, msg
            )
            


    @staticmethod
    def _worker_solve(task: SolvingTask) -> Result:
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

        break_time: float = 0.0
        break_cpu_time: float = 0.0
        break_memory_mb: float = 0.0
        
        
        if breaker_cfg:
            breaker_name = breaker_cfg.name
            
            processed_tc, breaker_result = MultiSolverManager._apply_symmetry_breaking(SolvingTask(triplet, test_case, timeout, work_dir))
            if processed_tc is None or breaker_result.status in CRITICAL_STATUSES:
                logger.error("Error/Timeout during symmetry breaking for %s: No test case returned from breaker", test_case.name)
                breaker_result.breaker = breaker_name
                return breaker_result
            
            test_case = processed_tc
            break_time = breaker_result.time
            break_cpu_time = breaker_result.cpu_time
            break_memory_mb = breaker_result.memory_peak_mb

        remaining_timeout: float = max(0.0, timeout - break_time)
        if remaining_timeout == 0.0:
            return MultiSolverManager._make_error_result(
                triplet, test_case, breaker_name, STATUS_TIMEOUT,
                "No time remaining after symmetry breaking.", break_time
            )

        try:
            runner: Runner = get_runner(problem_type=p_type, solv_cfg=solver_cfg)
            result: Result = runner.run(input_file=test_case, timeout=remaining_timeout, output_path=path_out)

            result.solver = solver_cfg.name
            result.problem = test_case.name
            result.parent_problem = triplet.problem.name
            result.breaker = breaker_name
            result.break_time = break_time
            result.break_cpu_time = break_cpu_time
            result.break_memory_mb = break_memory_mb
            result.formulator = test_case.formulator_cfg.name if test_case.formulator_cfg else None
            if task.conversion_metrics:
                result.conversion_time = task.conversion_metrics.time
                result.conversion_cpu_time = task.conversion_metrics.cpu_time
                result.conversion_memory_mb = task.conversion_metrics.memory_peak_mb
            return result

        except RunnerError as e:
            return MultiSolverManager._make_error_result(
                triplet, test_case, breaker_name, STATUS_ERROR,
                f"Runner Failure: {e}", break_time
            )
        except Exception as e:
            return MultiSolverManager._make_error_result(
                triplet, test_case, breaker_name, STATUS_ERROR,
                str(e), break_time
            )
            