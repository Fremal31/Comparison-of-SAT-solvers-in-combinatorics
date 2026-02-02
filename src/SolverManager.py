import json
from pathlib import Path
from .Runner import *
from .CNFSymmetryBreaker import CNFSymmetryBreaker
import threading
import queue
import os
from typing import List, Dict, Optional, Tuple, Union, Final
from typing_extensions import Literal
from dataclasses import asdict



class MultiSolverManager:
    """
    Manages running multiple SAT solvers on CNF files, optionally applying symmetry breaking.

    Attributes:
        solvers (List[ExecConfig]): List of solver configurations.
        cnf_files (List[TestCase]): List of CNF files or directories.
        maxthreads (int): Maximum number of concurrent solver threads.
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

    def __init__(
        self,
        solvers: List[ExecConfig],
        cnf_files: List[TestCase],
        timeout: Optional[float] = None,
        maxthreads: Optional[int] = None,
    ) -> None:
        """
        Initializes MultiSolverManager with solvers and CNF files.

        Args:
            solvers (List[ExecConfig]): List of solver configurations.
            cnf_files (List[TestCase]): List of CNF files or directories, each with "name" and "path".
            timeout (float, optional): Timeout for solver runs in seconds. Defaults to None.
            maxthreads (int, optional): Maximum concurrent solver threads. Defaults to 1 if None.
        """
        self.solvers: List[ExecConfig] = []
        for solver in solvers:
            if isinstance(solver, ExecConfig):
                self.solvers.append(solver)
            else:
                self.solvers.append(ExecConfig(**solver))
        
        self.cnf_files: List[TestCase] = []
        for cnf in cnf_files:
            if isinstance(cnf, TestCase):
                self.cnf_files.append(cnf)
            else:
                self.cnf_files.append(TestCase(**cnf))
    
        self.directory_iterator()
        self.maxthreads: int = maxthreads or 1
        self.break_symmetry: bool = False
        self.symmetry_path: Optional[str] = None
        self.use_temp_files: bool = False
        self.timeout: Optional[float] = timeout
        self.breaker: Optional[CNFSymmetryBreaker] = None
        self.lock: threading.Lock = threading.Lock()
        self.temp_files: List[TestCase] = []
        self.results: List[Result] = []
        self.task_queue: queue.Queue = queue.Queue()
        self.threads: List[threading.Thread] = []

    def directory_iterator(self) -> None:
        """
        Expands directories in cnf_files to individual CNF files.

        Updates:
            self.cnf_files (List[TestCase]): Flattened list with each CNF file as a dictionary {"name", "path"}.
        """
        new_files: List[TestCase] = []
        for cnf_file in self.cnf_files:
            cnf_path: Path = Path(cnf_file.path)
            cnf_name: Optional[str] = cnf_file.name or None
            if cnf_path.is_dir():
                files = [f for f in cnf_path.iterdir() if f.is_file()]
                counter = 0
                for f in files:
                    counter += 1
                    file_from_dir: TestCase = TestCase(name=f"{cnf_name}_{counter}", path=f)
                    new_files.append(file_from_dir)
            else:
                file: TestCase = TestCase(name=cnf_name, path=cnf_path)
                new_files.append(file)

        self.cnf_files = new_files

    def load_config(self, config_path: str) -> List[ExecConfig]:
        """
        Loads solver configuration from a JSON file.

        Args:
            config_path (str): Path to the JSON config file.

        Returns:
            List[ExecConfig]: List of solver configurations.
        """
        with open(config_path, "r") as file:
            return json.load(file)

    def set_symmetry_breaker(
        self,
        break_symmetry: bool,
        symmetry_breaker_path: str,
        use_temp_files: bool = False,
    ) -> None:
        """
        Configures symmetry breaking for solver runs.

        Args:
            break_symmetry (bool): Whether to enable symmetry breaking.
            symmetry_breaker_path (str): Path to the symmetry breaker executable.
            use_temp_files (bool, optional): Whether to use temporary files for symmetry breaking output. Defaults to False.
        """
        self.break_symmetry = break_symmetry
        self.use_temp_files = use_temp_files
        if break_symmetry:
            self.symmetry_path = symmetry_breaker_path
            self.breaker = CNFSymmetryBreaker(
                symmetry_breaker_path, use_temp_files, None, self.timeout
            )

    def run_one(
        self,
        solver_runner: Runner,
        solver: ExecConfig,
        cnf_file: TestCase,
        break_time: Optional[float] = None,
    ) -> Result:
        """
        Runs a single solver instance on a CNF file, optionally considering symmetry breaking time.

        Args:
            solver_runner (Runner): The solver runner instance.
            solver (ExecConfig): Solver configuration dictionary.
            cnf_file (TestCase): CNF file dictionary with "name" and "path".
            break_time (float, optional): Time spent on symmetry breaking. Defaults to 0.0.

        Returns:
            Result: Result dictionary containing solver run information and status.
        """
        cnf_name: str = cnf_file.name or str(cnf_file.path)
        break_time = break_time or 0.0
        remaining_time: Optional[float] = (
            self.timeout - break_time if self.timeout is not None else None
        )

        results: Result = Result(
            solver=solver.name,
            original_cnf=cnf_name,
            break_time=break_time,
            status="ERROR",
            error="",
        )

        print(f"Running {solver.name} on {cnf_file.name}...")

        try:
            #solver_runner.execConfig()
            solver_results = solver_runner.run(input_file=cnf_file, timeout=remaining_time)
            if isinstance(solver_results, Result):
                results = solver_results
            results.status = solver_results.status if isinstance(solver_results, Result) else solver_results.get("status", "UNKNOWN")
        except Exception as e:
            import traceback
            results.stderr = f"{str(e)}\n{traceback.format_exc()}"
            results.status = "ERROR"

        return results

    def thread(self) -> None:
        """
        Worker thread function to process tasks from the queue.

        Each task is a tuple (solver, cnf_file, timeout). Runs solver on CNF and handles symmetry breaking if enabled.
        """
        while True:
            try:
                task: Tuple[ExecConfig, TestCase, Optional[float]] = self.task_queue.get()
                if task is None:
                    break
                solver, cnf_file, timeout = task
                solver_runner = Runner()
                solver_runner.setConfig(solver)
                self.process_task(solver_runner, solver, cnf_file)
            except queue.Empty:
                continue
            finally:
                self.task_queue.task_done()

    def process_task(self, solver_runner: Runner, solver: ExecConfig, cnf_file: TestCase) -> None:
        """
        Processes a single solver run task including symmetry breaking if enabled.

        Args:
            solver_runner (Runner): Instance to run the solver.
            solver (ExecConfig): Solver configuration.
            cnf_file (TestCase): CNF file dictionary with "name" and "path".
        """
        result: Result = self.run_one(solver_runner, solver, cnf_file)
        with self.lock:
            self.results.append(result)

        if self.break_symmetry:
            if self.breaker is None:
                raise RuntimeError(f"Symmetry breaker path not set but symmetry breaking is on.")
            sb_cnf: str = cnf_file.name + "_sb" if cnf_file.name else str(cnf_file.path) + "_sb"
            modified_cnf: Optional[TestCase] = None
            try:
                symmetry_result, modified_cnf = self.breaker.symmetry_results(TestCase(name=sb_cnf, path=cnf_file.path)) 
                if self.use_temp_files and modified_cnf and modified_cnf.name and modified_cnf.name.startswith("__TEMP__"):
                    with self.lock:
                        self.temp_files.append(modified_cnf)

                result = self.run_one(solver_runner, solver, modified_cnf, break_time=symmetry_result.break_time)
                result.break_time = symmetry_result.break_time
                with self.lock:
                    self.results.append(result)
            except Exception as e:
                error_result: Result = Result(
                    solver=solver.name,
                    original_cnf=sb_cnf,
                    break_time=-1.0,
                    status="SYM_BREAK_ERROR",
                    error=str(e),
                )
                with self.lock:
                    self.results.append(error_result)

    def run_all(self) -> List[Result]:
        """
        Runs all configured solvers on all CNF files, possibly with symmetry breaking,
        using multiple threads as configured.

        Returns:
            List[Result]: List of all result dictionaries from solver runs.
        """
        self.results = []
        self.temp_files = []
        self.threads = []

        for _ in range(self.maxthreads):
            worker: threading.Thread = threading.Thread(target=self.thread)
            worker.daemon = True
            worker.start()
            self.threads.append(worker)

        for cnf_file in self.cnf_files:
            for solver in self.solvers:
                self.task_queue.put((solver, cnf_file, self.timeout))

        self.task_queue.join()

        for _ in range(self.maxthreads):
            self.task_queue.put(None)
        for worker in self.threads:
            worker.join()

        self.cleanup_temp_files()
        return self.results

    def cleanup_temp_files(self) -> None:
        """
        Deletes all temporary files created during symmetry breaking runs.
        Only deletes files marked with __TEMP__ prefix in the name.
        """
        for temp_file in self.temp_files:
            try:
                if temp_file.name and temp_file.name.startswith("__TEMP__"):
                    if os.path.exists(temp_file.path):
                        os.unlink(temp_file.path)
            except Exception as e:
                print(f"Failed to delete temp file {temp_file.path}: {str(e)}")
        self.temp_files = []

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
                row: dict[str, str] = {}
                for field in fieldnames:
                    row[field] = res_dict.get(field, "")
                
                writer.writerow(row)
