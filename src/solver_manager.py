import json
from pathlib import Path
import shutil
import copy
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from src.custom_types import ExecConfig, FileConfig, FormulatorConfig
from .runner import *
import threading
import queue
import os
import sys
from typing import List, Dict, Optional, Tuple, Union, Final
from typing_extensions import Literal
from dataclasses import asdict
from .custom_types import *
from .factory import *
from functools import partial
from .registry import resolve_format_metadata

class MultiSolverManager:
    """
    Manages running multiple SAT solvers on CNF files, optionally applying symmetry breaking.

    Attributes:
        solvers (List[ExecConfig]): List of solver configurations.
        test_case (List[TestCase]): List of CNF files or directories.
        max_threads (int): Maximum number of concurrent solver threads.
        break_symmetry (bool): Flag to enable symmetry breaking.
        symmetry_path (Optional[str]): Path to the symmetry breaker executable.
        use_temp_files (bool): Flag to use temporary files for symmetry breaking output.
        timeout (Optional[float]): Timeout in seconds for solver runs.
        breaker (Optional[CNFSymmetryBreaker]): Symmetry breaker instance.
        lock (threading.Lock): Lock to protect shared data.
        temp_files (List[TestCase]): List of temporary CNF files to clean up.
        results (List[Result]): List of solver run results.
        task_queue (queue.Queue): Queue of tasks for threads.
        threads (List[threading.Thread]): List of worker threads.
    """
    
    def __init__(self, config: Config) -> None:
        """
        Initializes MultiSolverManager with solvers and CNF files.

        Args:
            solvers (List[ExecConfig]): List of solver configurations.
            test_case (List[TestCase]): List of CNF files or directories, each with "name" and "path".
            timeout (float, optional): Timeout for solver runs in seconds. Defaults to None.
            max_threads (int, optional): Maximum concurrent solver threads. Defaults to 1 if None.
        """
        if config.working_dir:
            self.work_dir = Path(config.working_dir)

        if self.work_dir.exists():
            input(f"By continuing this working directory: {self.work_dir} will be deleted.. ")
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
            print(self.all_triplets)
        else:
           for file_wo_converter in config.without_converter:
            if file_wo_converter.enabled:
                self.test_case.append(TestCase(name=file_wo_converter.name, 
                                           path=file_wo_converter.path, 
                                           problem_cfg=None,
                                           formulator_cfg=None,
                                           tc_type=file_wo_converter.tc_type))

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
        # results/Graph1/FormulatorA/
        f_metadata = resolve_format_metadata(format_type=formulator_cfg.formulator_type)

        base_path = self.work_dir / problem_cfg.name / formulator_cfg.name
        #base_path = self.work_dir
        log_dir = base_path / "logs"
        
        log_dir.mkdir(parents=True, exist_ok=True)
        context = ExperimentContext(
            base_path=base_path,
            log_dir=log_dir,
            format_info=f_metadata
        )
        return context

    def _add_solver_tasks(self, triplet: ExecutionTriplet, test_cases: List[TestCase]) -> List[SolvingTask]:
        solver_tasks: List[SolvingTask] = []
        problem_cfg: FileConfig | None = triplet.problem
        formulator_cfg: FormulatorConfig | None = triplet.formulator
        solver_cfg: ExecConfig = triplet.solver
        breaker_cfg: ExecConfig | None = triplet.breaker

        context = self._get_experiment_paths(problem_cfg, formulator_cfg)
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
        dummy_prob_cfg = FileConfig(name=tc.name, path=tc.path)
        dummy_formulator = FormulatorConfig(
            name="None", 
            formulator_type=tc.tc_type, 
            cmd="", 
            enabled=True
        )
        return dummy_prob_cfg, dummy_formulator
    
    def _generate_triplets(self, problems, formulators, test_cases, solvers, breakers) -> List[ExecutionTriplet]:
        all_triplets: List[ExecutionTriplet] = []
        for problem in problems:
            for formulator in formulators:
                compatible_solvers = [solver for solver in solvers if solver.solver_type == formulator.formulator_type]
                for solver in compatible_solvers:
                    all_triplets.append(ExecutionTriplet(problem, formulator, solver))
                    compatible_breakers = [breaker for breaker in breakers if breaker.solver_type == solver.solver_type]
                    for breaker in compatible_breakers:
                        all_triplets.append(ExecutionTriplet(problem, formulator, solver, breaker))

        for tc in test_cases:
            dummy_prob_cfg, dummy_formulator = self._create_dummy_problem_formulator_from_testcase(tc)
            
            compatible_solvers = [solver for solver in solvers if solver.solver_type == tc.tc_type]
            for solver in compatible_solvers:
                all_triplets.append(ExecutionTriplet(dummy_prob_cfg, dummy_formulator, solver))
                for breaker in breakers:
                    if breaker.solver_type == tc.tc_type:
                        all_triplets.append(ExecutionTriplet(dummy_prob_cfg, dummy_formulator, solver, breaker))
        return all_triplets
    
    def run_all_experiments_parallel_separate(self) -> List[Result]:
        #PHASE 1: For each unique (problem, formulator) pair, convert the problem and store the resulting test cases
        # only convert each (Prob, Form) pair once
        unique_conversions: Dict[Tuple[FileConfig, FormulatorConfig], ConversionTask] = {}

        for t in self.all_triplets:
            if t.formulator.name == "None":
                continue # skip conversion for test cases without a formulator
            key = (t.problem.name, t.formulator.name)
            if key not in unique_conversions:
                context = self._get_experiment_paths(t.problem, t.formulator)
                conversion_task = ConversionTask(
                    problem=t.problem,
                    config=t.formulator,
                    work_dir=context
                )
                unique_conversions[key] = conversion_task
        
        problem_formulator_pairs_to_testcases_map: Dict[Tuple[str, str], List[TestCase]] = {}

        for test_case in self.test_case:
            key = (test_case.problem_cfg.name if test_case.problem_cfg else test_case.name, 
                   test_case.formulator_cfg.name if test_case.formulator_cfg else "None")
            problem_formulator_pairs_to_testcases_map[key] = [test_case]
        
        if unique_conversions:
            print(f"--- Converting {len(unique_conversions)} (problem, formulator) pairs ---")
            unique_conversions_tuples = list(unique_conversions.values())
            with ProcessPoolExecutor(max_workers=self.max_threads) as executor:
                batch_results = list(executor.map(self._worker_convert, unique_conversions_tuples))
                for problem_formulator_pair, test_cases in zip(unique_conversions.keys(), batch_results):
                    problem_formulator_pairs_to_testcases_map[problem_formulator_pair] = test_cases
                    self.test_case.extend(test_cases)

        # done converting - now we have a mapping of (problem, formulator) -> list of test cases
        #PHASE 2: Create a list of all solver tasks to run, using the converted test cases from Phase 2 and the original test cases without conversion

        solver_tasks: List[SolvingTask] = []

        for t in self.all_triplets:
            test_cases = problem_formulator_pairs_to_testcases_map.get((t.problem.name, t.formulator.name), [])
            solver_tasks.extend(self._add_solver_tasks(triplet=t, test_cases=test_cases))

        print(f"--- Solving {len(solver_tasks)} runs ---")
        self.results = []

        if solver_tasks:
            with ProcessPoolExecutor(max_workers=self.max_threads) as executor:
                try:
                    futures = {executor.submit(self._worker_solve, task): task for task in solver_tasks}
                    from concurrent.futures import as_completed
                    for future in as_completed(futures):
                        result = future.result()
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
        context = task.work_dir
        output_path: Path = context.base_path / f"{task.problem.name}{context.format_info.suffix}"
        converter = get_converter(task.config)
        results = converter.convert(problem=task.problem, output_path=output_path)
        return results

    @staticmethod
    def _apply_symmetry_breaking(triplet: ExecutionTriplet, test_case: TestCase, timeout: float, work_dir: ExperimentContext) -> Tuple[Optional[TestCase], Result]:
        orig_path = Path(test_case.path)
        solver_cfg: ExecConfig = triplet.solver
        breaker_cfg: ExecConfig = triplet.breaker
        symmetry_test_case: TestCase = copy.deepcopy(test_case)

        if breaker_cfg is None:
            raise ValueError(f"Breaker configuration is None for triplet with solver {solver_cfg.name} and problem {test_case.name}")
        else:
            breaker_name = breaker_cfg.name
        sym_path = work_dir.base_path / f"{test_case.name}.{solver_cfg.name}.{breaker_name}.sym.cnf"
        br_runner = Runner(strategy=GenericBreaker())
        br_runner.setConfig(breaker_cfg)
        
        try:
            br_res = br_runner.run(input_file=test_case, timeout=timeout, output_path=sym_path)

            if br_res is None or br_res.status == "ERROR":
                print(f"Error during symmetry breaking for {test_case.name}: Runner returned None instead of Result object")
                status = "BREAKER_ERROR"
                error_msg = "Breaker returned None instead of Result object"

                return test_case, Result(
                    solver=solver_cfg.name,
                    problem=test_case.name,
                    breaker=breaker_name,
                    formulator=test_case.formulator_cfg.name if test_case.formulator_cfg else "None",
                    status=status,
                    error=error_msg
                )
            
            symmetry_test_case.path = str(sym_path)
            test_case.generated_files.append(sym_path)
            return symmetry_test_case, br_res
            

            return symmetry_test_case, br_res

        except Exception as e:
            print(f"Error during symmetry breaking for {test_case.name}: {e}")
            err_tc = TestCase(
                name=test_case.name,
                path=test_case.path,
                problem_cfg=test_case.problem_cfg,
                formulator_cfg=test_case.formulator_cfg,
                tc_type=test_case.tc_type
            )
            br_err_result: Result = Result(
                solver=triplet.solver.name,
                problem=test_case.name,
                status="BREAKER_ERROR",
                error=str(e)
            )
            return err_tc, br_err_result
        


    @staticmethod
    def _worker_solve(task: SolvingTask) -> Result:
        triplet: ExecutionTriplet = task.triplet
        solver_cfg: ExecConfig = triplet.solver
        breaker_cfg: Optional[ExecConfig] = triplet.breaker
    
        test_case: TestCase = task.test_case
        timeout: float = task.timeout
        breaker_name = triplet.breaker.name if triplet.breaker else "None"
        work_dir = task.work_dir
        
        p_type = task.test_case.tc_type if task.test_case.tc_type != "UNKNOWN" else triplet.formulator.formulator_type
        
        log_name = f"{test_case.name}.{solver_cfg.name}_{breaker_name}.out"
        path_out = work_dir.log_dir / log_name

        break_time = 0.0
        
        if triplet.breaker:
            tc = TestCase(
                path=Path(test_case.path),
                name=test_case.name,
                problem_cfg=triplet.problem,
                formulator_cfg=triplet.formulator,
                tc_type=p_type,
            )
            processed_tc, breaker_result = MultiSolverManager._apply_symmetry_breaking(triplet, test_case, timeout, work_dir)
            if processed_tc is None or breaker_result is None or "ERROR" in breaker_result.status or "TIMEOUT" in breaker_result.status:
                print(f"Error during symmetry breaking for {tc.name}: No test case returned from breaker")
                return breaker_result
            test_case = processed_tc
            break_time = breaker_result.time
        else:
            break_time = 0.0


        try:
            runner: Runner = get_runner(p_type, solver_cfg)
            result: Result = runner.run(input_file=test_case, timeout=timeout - break_time, output_path=path_out)
            result.solver = solver_cfg.name
            result.problem = test_case.name
            result.parent_problem = triplet.problem.name
            result.breaker = breaker_name
            result.break_time = break_time
            result.formulator = test_case.formulator_cfg.name if test_case.formulator_cfg else "None"
            return result

        except Exception as e:
            print(f"DEBUG: Solver {solver_cfg.name} failed on {test_case.path}: {e}")
            return Result(
                solver=solver_cfg.name,
                problem=test_case.name,
                breaker=breaker_name,
                formulator=getattr(test_case, 'formulator_name', "None"),
                status="ERROR",
                error=str(e),
                time=-1.0
            )
            
    def log_results(self, results: List[Result], fieldnames: List[str], output_path: str = "multi_solver_results.csv") -> None:
        """
        Logs solver run results to a CSV file.

        Args:
            results (List[Result]): List of result dictionaries to log.
            fieldnames (List[str]): CSV field names to write.
            output_path (str, optional): Output CSV file path. Defaults to "multi_solver_results.csv".
        """
        import csv
        print()
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for res in results:
                res_dict: dict[str, str] = asdict(res) if isinstance(res, Result) else res
                if 'metrics' in res_dict:
                    metrics = res_dict.pop('metrics')
                    res_dict.update(metrics)
                    
                row: dict[str, str] = {}
                for field in fieldnames:
                    row[field] = res_dict.get(field, "")
                
                writer.writerow(row)
