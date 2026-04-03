from concurrent.futures._base import Future
from pathlib import Path
import shutil
import copy
from concurrent.futures import ProcessPoolExecutor
import os
import sys
from typing import List, Dict, Optional, Tuple

from custom_types import *
from factory import *
from metadata_registry import resolve_format_metadata
from format_types import ExperimentContext, ConversionTask, SolvingTask

NULL_FORMULATOR: str = "NULL_FORMULATOR"
NULL_BREAKER: str = ""


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
        if config.working_dir:
            self.work_dir = Path(config.working_dir)
        else:
            raise ValueError("Working directory must be specified in config")
        if self.work_dir.exists() and not config.delete_working_dir:
            if any(self.work_dir.iterdir()):
                raise ValueError(f"Working directory {self.work_dir} already exists and is not empty. Set 'delete_working_dir' to true in config to automatically clear it before running.")
            
        if self.work_dir.exists() and config.delete_working_dir:
            shutil.rmtree(self.work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self.timeout: Optional[float] = config.timeout
        self.results: List[Result] = []

        self.max_threads: int = config.max_threads

        #self.directory_iterator() := TODO: do this in main.py

        self.enabled_problems: List[FileConfig] = []
        for file in config.files:
            if file.enabled:
                self.enabled_problems.append(FileConfig(name=file.name, path=file.path))

        self.enabled_formulators: List[FormulatorConfig] = []
        for formulator in config.formulators:
            if formulator.enabled:
                self.enabled_formulators.append(formulator)


        self.enabled_breakers: List[ExecConfig] = []
        for breaker in config.breakers:
            if breaker.enabled:
                self.enabled_breakers.append(breaker)

        self.enabled_solvers: List[ExecConfig] = []
        for solver in config.solvers:
            if solver.enabled:
                self.enabled_solvers.append(solver)

        self.all_triplets: List[ExecutionTriplet] = []
        self.test_case: List[TestCase] = []
        if config.triplet_mode:
            for triplet in config.triplets:
                if triplet.test_case:
                    self.test_case.append(triplet.test_case)
                    problem_cfg, formulator_cfg = self._create_dummy_problem_formulator_from_testcase(triplet.test_case)
                    triplet.problem = problem_cfg
                    triplet.formulator = formulator_cfg
            self.all_triplets = config.triplets
            print(f"Triplet mode enabled: Using {len(self.all_triplets)} triplets directly from config")
            # print(self.all_triplets)
        else:
            for file_wo_converter in config.without_converter:
                if file_wo_converter.enabled:
                    self.test_case.append(TestCase(
                        name=file_wo_converter.name, 
                        path=file_wo_converter.path, 
                        problem_cfg=None,
                        formulator_cfg=None,
                        tc_type=file_wo_converter.tc_type
                        )
                    )

            self.all_triplets = self._generate_triplets(problems=self.enabled_problems, formulators=self.enabled_formulators, test_cases=self.test_case, solvers=self.enabled_solvers, breakers=self.enabled_breakers)
            print(f"Generated {len(self.all_triplets)} triplets from config")

    def _directory_iterator(self) -> None: # := TODO: do this in main.py
        """
        Expands directories in test_case to individual CNF files.

        Updates:
            self.test_case (List[TestCase]): Flattened list with each CNF file as a dictionary {"name", "path"}.
        """
        new_files: List[TestCase] = []
        for cnf_file in self.test_case:
            cnf_path: Path = Path(cnf_file.path)
            cnf_name: Optional[str] = cnf_file.name or None
            if cnf_path.is_dir():
                files = [f for f in cnf_path.iterdir() if f.is_file()]
                counter = 0
                for f in files:
                    counter += 1
                    file_from_dir: TestCase = TestCase(name=f"{cnf_name}_{counter}", path=f, tc_type="")
                    new_files.append(file_from_dir)
            else:
                file: TestCase = TestCase(name=cnf_name, path=cnf_path, tc_type="")
                new_files.append(file)

        self.test_case = new_files
    
    def _get_experiment_paths(self, problem_cfg: FileConfig, formulator_cfg: FormulatorConfig) -> ExperimentContext:
        """Builds and returns the working directory structure for a (problem, formulator) pair."""
        f_metadata = resolve_format_metadata(format_type=formulator_cfg.formulator_type)

        if formulator_cfg.name != NULL_FORMULATOR:
            base_path = self.work_dir / problem_cfg.name / formulator_cfg.name 
        else:
            base_path = self.work_dir / problem_cfg.name 
        #base_path = self.work_dir
        log_dir: Path = base_path / "logs"
        
        log_dir.mkdir(parents=True, exist_ok=True)
        context = ExperimentContext(
            base_path=base_path,
            log_dir=log_dir,
            format_info=f_metadata
        )
        return context

    def _add_solver_tasks(self, triplet: ExecutionTriplet, test_cases: List[TestCase]) -> List[SolvingTask]:
        """Creates a SolvingTask for each test case in the given triplet."""
        solver_tasks: List[SolvingTask] = []
        problem_cfg: FileConfig | None = triplet.problem
        formulator_cfg: FormulatorConfig | None = triplet.formulator
        solver_cfg: ExecConfig = triplet.solver
        breaker_cfg: ExecConfig | None = triplet.breaker

        context: ExperimentContext = self._get_experiment_paths(problem_cfg=problem_cfg, formulator_cfg=formulator_cfg)
        for tc in test_cases:
            solver_task: SolvingTask = SolvingTask(
                triplet=triplet,
                test_case=tc,
                work_dir=context,
                timeout=self.timeout
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
        for problem in problems:
            for formulator in formulators:
                compatible_solvers: List[ExecConfig] = [solver for solver in solvers if solver.solver_type == formulator.formulator_type]
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

        for tc in test_cases:
            dummy_prob_cfg, dummy_formulator = self._create_dummy_problem_formulator_from_testcase(tc=tc)
            
            compatible_solvers: List[ExecConfig] = [solver for solver in solvers if solver.solver_type == tc.tc_type]
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
    
    def run_all_experiments_parallel_separate(self) -> List[Result]:
        """
        Runs the full two-phase benchmark pipeline. 
        
        In Phase 1, each unique
        (problem, formulator) pair is converted exactly once in parallel and the
        results cached. 
        
        In Phase 2, all solver tasks run in parallel reusing the
        cached converted files.

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
                    work_dir=context
                )
                unique_conversions[key] = conversion_task
        
        problem_formulator_pairs_to_testcases_map: Dict[Tuple[str, str], List[TestCase]] = {}

        for test_case in self.test_case:
            key = (test_case.problem_cfg.name if test_case.problem_cfg else test_case.name, 
                   test_case.formulator_cfg.name if test_case.formulator_cfg else NULL_FORMULATOR)
            problem_formulator_pairs_to_testcases_map[key] = [test_case]
        
        if unique_conversions:
            print(f"--- Converting {len(unique_conversions)} (problem, formulator) pairs ---")
            unique_conversions_tuples: List[ConversionTask] = list(unique_conversions.values())
            with ProcessPoolExecutor(max_workers=self.max_threads) as executor:
                batch_results: List[List[TestCase]] = list(executor.map(self._worker_convert, unique_conversions_tuples))
                for problem_formulator_pair, test_cases in zip(unique_conversions.keys(), batch_results):
                    problem_formulator_pairs_to_testcases_map[problem_formulator_pair] = test_cases
                    self.test_case.extend(test_cases)

        solver_tasks: List[SolvingTask] = []

        for t in self.all_triplets:
            test_cases = problem_formulator_pairs_to_testcases_map.get((t.problem.name, t.formulator.name), [])
            solver_tasks.extend(self._add_solver_tasks(triplet=t, test_cases=test_cases))

        print(f"--- Solving {len(solver_tasks)} runs ---")
        self.results = []

        if solver_tasks:
            with ProcessPoolExecutor(max_workers=self.max_threads) as executor:
                try:
                    futures: Dict[Future[Result], SolvingTask] = {executor.submit(self._worker_solve, task): task for task in solver_tasks}
                    from concurrent.futures import as_completed
                    for future in as_completed(futures):
                        result: Result = future.result()
                        self.results.append(result)
                        print(f"[{len(self.results)}/{len(solver_tasks)}] Done: {result.solver} on {result.problem}", end='\r')
                        print(f"\nResult: Solver {result.solver}, Problem {result.problem}, Status {result.status}, Time {result.time:.2f}s, Error: {result.error if result.error else 'None'}")
                        
                except KeyboardInterrupt:
                    print("Interrupted by user. Attempting to cancel remaining tasks and shutting down executor...", file=sys.stderr)
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                finally :
                    print(f"\nCompleted {len(self.results)}/{len(solver_tasks)} solver runs.")
        return self.results

    @staticmethod
    def _worker_convert(task: ConversionTask) -> List[TestCase]:
        """
        Phase 1 worker that converts a single (problem, formulator) pair.

        Returns an empty list rather than raising if conversion fails.
        """
        context: ExperimentContext = task.work_dir
        output_path: Path = context.base_path / f"{task.problem.name}{context.format_info.suffix}"
        try:
            converter: Converter = get_converter(form_cfg=task.config)
            results: List[TestCase] | None = converter.convert(problem=task.problem, output_path=output_path)
            return results
        except ConversionError as e:
            print(f"  [CONVERT] Failed: {task.problem.name} using {task.config.name}. Error: {e}")
            return []
        except Exception as e:
            print(f"  [CONVERT] Critical Error: {task.problem.name}: {e}")
            return []


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
        solver_name = triplet.solver.name
        breaker_cfg = triplet.breaker

        sym_path = work_dir.base_path / f"{test_case.name}.{triplet.solver.name}.{triplet.breaker.name}.sym.cnf"
        symmetry_test_case: TestCase = copy.deepcopy(test_case)
        
        if not breaker_cfg:
            raise ValueError(f"Breaker config missing for {solver_name}")

        br_runner = get_runner(problem_type=triplet.breaker.solver_type, solv_cfg=breaker_cfg)
        
        try:
            br_res = br_runner.run(input_file=test_case, timeout=timeout, output_path=sym_path)
            if br_res.status in CRITICAL_STATUSES:
                print(f"  [BREAKER] Error for {test_case.name}: {br_res.stderr} {br_res.error}")
                br_res.breaker = br_res.solver
                br_res.solver = triplet.solver.name
                br_res.status = STATUS_BREAKER_ERROR
                return None, br_res
            
            if not sym_path.exists() or sym_path.stat().st_size == 0:
                msg = f"Symmetry breaker did not produce a valid output file at {sym_path}"
                print(msg)
                br_res.breaker = br_res.solver
                br_res.solver = triplet.solver.name
                br_res.status = STATUS_BREAKER_ERROR
                return None, br_res
            
            symmetry_test_case.path = sym_path
            test_case.generated_files.append(sym_path)
            return symmetry_test_case, br_res

        except RunnerError as e:
            msg = f"Breaker Process Failure: {str(e)}"
            print(f"Critical error during symmetry breaking: {msg}")
            return None, Result(
                solver=triplet.solver.name,
                problem=test_case.name,
                breaker=breaker_cfg.name,
                status=STATUS_BREAKER_ERROR,
                error=msg,
                time=-1.0
            )
        except Exception as e:
            msg = f"Unexpected exception: {str(e)}"
            print(f"Error during symmetry breaking for {test_case.name}: {msg}")
            err_res = Result(
                breaker=triplet.breaker.name,
                solver=triplet.solver.name,
                problem=test_case.name,
                status=STATUS_BREAKER_ERROR,
                error=msg
            )
            return None, err_res
            


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
        
        # maybe clunky
        p_type = task.test_case.tc_type if task.test_case.tc_type != "UNKNOWN" else triplet.formulator.formulator_type
        breaker_name:str = breaker_cfg.name if triplet.breaker else NULL_BREAKER
        log_name = f"{test_case.name}.{solver_cfg.name}_{breaker_name}.out"
        path_out = work_dir.log_dir / log_name

        break_time = 0.0
        
        
        if triplet.breaker:
            breaker_name = breaker_cfg.name
            
            processed_tc, breaker_result = MultiSolverManager._apply_symmetry_breaking(SolvingTask(triplet, test_case, timeout, work_dir))
            if processed_tc is None or breaker_result.status in CRITICAL_STATUSES:
                print(f"Error/Timeout during symmetry breaking for {test_case.name}: No test case returned from breaker")
                breaker_result.breaker = breaker_name
                return breaker_result
            
            test_case = processed_tc
            break_time: float = breaker_result.time

        try:
            runner: Runner = get_runner(problem_type=p_type, solv_cfg=solver_cfg)
            result: Result = runner.run(input_file=test_case, timeout=timeout - break_time, output_path=path_out)

            result.solver = solver_cfg.name
            result.problem = test_case.name
            result.parent_problem = triplet.problem.name
            result.breaker = breaker_name
            result.break_time = break_time
            result.formulator = test_case.formulator_cfg.name if test_case.formulator_cfg else None
            return result

        except (RunnerError, Exception) as e:
            status = STATUS_ERROR
            error_msg = str(e)
            
            if isinstance(e, RunnerError):
                error_msg = f"Runner Failure: {e}"
            # else: print(f"Critical crash on {test_case.path}: {e}")

            return Result(
                solver=triplet.solver.name,
                problem=test_case.name,
                parent_problem=triplet.problem.name if triplet.problem else test_case.name,
                breaker=breaker_name,
                formulator=triplet.formulator.name if triplet.formulator else None,
                status=status,
                error=error_msg,
                time=-1.0,
                break_time=break_time
            )
            