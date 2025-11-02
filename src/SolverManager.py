import json
from pathlib import Path
from SolverRunner import SolverRunner
from CNFSymmetryBreaker import CNFSymmetryBreaker
import threading
import queue
import os
from typing import List, Dict, Optional, Tuple, Union
from typing_extensions import TypedDict, Literal


class CNFFile(TypedDict):
    name: Optional[str]
    path: Union[str, Path]


class SolverConfig(TypedDict):
    name: str
    path: str


class SolverResult(TypedDict):
    solver: str
    original_cnf: str
    break_time: float
    status: Literal["ERROR", "UNKNOWN", "TIMEOUT", "SYM_BREAK_ERROR", "OK"]
    error: str


class MultiSolverManager:
    """
    Manages running multiple SAT solvers on CNF files, optionally applying symmetry breaking.

    Attributes:
        solvers (List[SolverConfig]): List of solver configurations.
        cnf_files (List[CNFFile]): List of CNF files or directories.
        maxthreads (int): Maximum number of concurrent solver threads.
        break_symmetry (bool): Flag to enable symmetry breaking.
        symmetry_path (Optional[str]): Path to the symmetry breaker executable.
        use_temp_files (bool): Flag to use temporary files for symmetry breaking output.
        timeout (Optional[float]): Timeout in seconds for solver runs.
        breaker (Optional[CNFSymmetryBreaker]): Symmetry breaker instance.
        lock (threading.Lock): Lock to protect shared data.
        temp_files (List[CNFFile]): List of temporary CNF files to clean up.
        results (List[SolverResult]): List of solver run results.
        task_queue (queue.Queue): Queue of tasks for threads.
        threads (List[threading.Thread]): List of worker threads.
    """

    def __init__(
        self,
        solvers: List[SolverConfig],
        cnf_files: List[CNFFile],
        timeout: Optional[float] = None,
        maxthreads: Optional[int] = None,
    ) -> None:
        """
        Initializes MultiSolverManager with solvers and CNF files.

        Args:
            solvers (List[SolverConfig]): List of solver configurations.
            cnf_files (List[CNFFile]): List of CNF files or directories, each with "name" and "path".
            timeout (float, optional): Timeout for solver runs in seconds. Defaults to None.
            maxthreads (int, optional): Maximum concurrent solver threads. Defaults to 1 if None.
        """
        self.solvers: List[SolverConfig] = solvers
        self.cnf_files: List[CNFFile] = cnf_files
        self.directory_iterator()
        self.maxthreads: int = maxthreads or 1
        self.break_symmetry: bool = False
        self.symmetry_path: Optional[str] = None
        self.use_temp_files: bool = False
        self.timeout: Optional[float] = timeout
        self.breaker: Optional[CNFSymmetryBreaker] = None
        self.lock: threading.Lock = threading.Lock()
        self.temp_files: List[CNFFile] = []
        self.results: List[SolverResult] = []
        self.task_queue: queue.Queue = queue.Queue()
        self.threads: List[threading.Thread] = []

    def directory_iterator(self) -> None:
        """
        Expands directories in cnf_files to individual CNF files.

        Updates:
            self.cnf_files (List[CNFFile]): Flattened list with each CNF file as a dictionary {"name", "path"}.
        """
        new_files: List[CNFFile] = []
        for cnf_file in self.cnf_files:
            cnf_path: Path = Path(cnf_file["path"])
            cnf_name: Optional[str] = cnf_file["name"] or None
            if cnf_path.is_dir():
                files = [f for f in cnf_path.iterdir() if f.is_file()]
                counter = 0
                for f in files:
                    counter += 1
                    new_files.append({"name": f"{cnf_name}_{counter}", "path": f})
            else:
                new_files.append({"name": cnf_name, "path": cnf_path})
        self.cnf_files = new_files

    def load_config(self, config_path: str) -> List[SolverConfig]:
        """
        Loads solver configuration from a JSON file.

        Args:
            config_path (str): Path to the JSON config file.

        Returns:
            List[SolverConfig]: List of solver configurations.
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
        solver_runner: SolverRunner,
        solver: SolverConfig,
        cnf_file: CNFFile,
        break_time: Optional[float] = None,
    ) -> SolverResult:
        """
        Runs a single solver instance on a CNF file, optionally considering symmetry breaking time.

        Args:
            solver_runner (SolverRunner): The solver runner instance.
            solver (SolverConfig): Solver configuration dictionary.
            cnf_file (CNFFile): CNF file dictionary with "name" and "path".
            break_time (float, optional): Time spent on symmetry breaking. Defaults to 0.0.

        Returns:
            SolverResult: Result dictionary containing solver run information and status.
        """
        cnf_name: str = cnf_file["name"] or str(cnf_file["path"])
        break_time = break_time or 0.0
        remaining_time: Optional[float] = (
            self.timeout - break_time if self.timeout is not None else None
        )

        results: SolverResult = {
            "solver": solver["name"],
            "original_cnf": cnf_name,
            "break_time": break_time,
            "status": "ERROR",
            "error": "",
        }

        print(f"Running {solver['name']} on {cnf_file['name']}...")

        try:
            solver_results = solver_runner.run_solver(cnf_file=cnf_file, timeout=remaining_time)
            results.update(solver_results)
            results["status"] = solver_results.get("status", "UNKNOWN")
        except Exception as e:
            import traceback
            results["error"] = f"{str(e)}\n{traceback.format_exc()}"
            results["status"] = "ERROR"

        return results

    def thread(self) -> None:
        """
        Worker thread function to process tasks from the queue.

        Each task is a tuple (solver, cnf_file, timeout). Runs solver on CNF and handles symmetry breaking if enabled.
        """
        while True:
            try:
                task: Tuple[SolverConfig, CNFFile, Optional[float]] = self.task_queue.get()
                if task is None:
                    break
                solver, cnf_file, timeout = task
                solver_runner = SolverRunner(solver["path"])
                self.process_task(solver_runner, solver, cnf_file)
            except queue.Empty:
                continue
            finally:
                self.task_queue.task_done()

    def process_task(self, solver_runner: SolverRunner, solver: SolverConfig, cnf_file: CNFFile) -> None:
        """
        Processes a single solver run task including symmetry breaking if enabled.

        Args:
            solver_runner (SolverRunner): Instance to run the solver.
            solver (SolverConfig): Solver configuration.
            cnf_file (CNFFile): CNF file dictionary with "name" and "path".
        """
        result = self.run_one(solver_runner, solver, cnf_file)
        with self.lock:
            self.results.append(result)

        if self.break_symmetry:
            sb_cnf: str = str(cnf_file["path"].name) + "_sb"
            try:
                modified_cnf, break_time = self.breaker.break_symmetries({"name": sb_cnf, "path": cnf_file["path"]})
                if modified_cnf["name"] == "TIMEOUT" and break_time == -1.0:
                    timeout_result: SolverResult = {
                        "solver": solver["name"],
                        "original_cnf": sb_cnf,
                        "break_time": break_time,
                        "status": "TIMEOUT",
                        "error": "",
                    }
                    with self.lock:
                        self.results.append(timeout_result)
                    return
                if self.use_temp_files:
                    with self.lock:
                        self.temp_files.append(modified_cnf)

                result = self.run_one(solver_runner, solver, modified_cnf, break_time=break_time)
                with self.lock:
                    self.results.append(result)
            except Exception as e:
                error_result: SolverResult = {
                    "solver": solver["name"],
                    "original_cnf": sb_cnf,
                    "break_time": -1.0,
                    "status": "SYM_BREAK_ERROR",
                    "error": str(e),
                }
                with self.lock:
                    self.results.append(error_result)

    def run_all(self) -> List[SolverResult]:
        """
        Runs all configured solvers on all CNF files, possibly with symmetry breaking,
        using multiple threads as configured.

        Returns:
            List[SolverResult]: List of all result dictionaries from solver runs.
        """
        self.results = []
        self.temp_files = []
        self.threads = []

        for _ in range(self.maxthreads):
            worker = threading.Thread(target=self.thread)
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
        """
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file["path"]):
                    os.unlink(temp_file["path"])
            except Exception as e:
                print(f"Failed to delete temp file {temp_file['path']}: {str(e)}")
        self.temp_files = []

    def log_results(self, results: List[SolverResult], fieldnames: List[str], output_path: str = "multi_solver_results.csv") -> None:
        """
        Logs solver run results to a CSV file.

        Args:
            results (List[SolverResult]): List of result dictionaries to log.
            fieldnames (List[str]): CSV field names to write.
            output_path (str, optional): Output CSV file path. Defaults to "multi_solver_results.csv".
        """
        import csv
        print()
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for res in results:
                row = {field: res.get(field, "") for field in fieldnames}
                writer.writerow(row)
