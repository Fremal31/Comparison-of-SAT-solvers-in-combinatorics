import json
from pathlib import Path
from SolverRunner import SolverRunner
from CNFSymmetryBreaker import CNFSymmetryBreaker
import threading
import queue
import os

#TODO: add Docstrings and comments

class MultiSolverManager:

    def __init__(self, config_path, cnf_files: list, timeout=None, maxthreads=None):
        self.solvers = self.load_config(config_path)
        self.cnf_files = cnf_files
        self.directory_iterator()
        self.maxthreads = maxthreads or 1
        self.break_symmetry = False
        self.symmetry_path = None
        self.use_temp_files = False
        self.timeout = timeout
        self.breaker = None
        self.lock = threading.Lock()
        self.temp_files = []
        self.results = []
        self.task_queue = queue.Queue()
        self.threads = []

    def directory_iterator(self):
        for cnf_file in self.cnf_files:
            cnf_path = Path(cnf_file)
            if cnf_path.is_dir():
                self.cnf_files.remove(cnf_file)
                files = [f for f in cnf_path.iterdir() if f.is_file()]
                self.cnf_files.extend(files)

    def load_config(self, config_path):
        with open(config_path, "r") as file:
            return json.load(file)
        
    def set_symmetry_breaker(self, break_symmetry, symmetry_breaker_path, use_temp_files=False):
        self.break_symmetry = break_symmetry
        self.use_temp_files = use_temp_files
        if break_symmetry:
            self.symmetry_path = symmetry_breaker_path
            self.breaker = CNFSymmetryBreaker(symmetry_breaker_path, use_temp_files, None, self.timeout)
    
    def run_one(self, solver_runner, solver, cnf_file, break_time=None):
        break_time = break_time if break_time is not None else 0.0
        remaining_time = self.timeout - break_time
        results = {
            "solver": solver["name"],
            "original_cnf": Path(cnf_file).name,
            "break_time": break_time,
            "status": "ERROR",
            "error": ""
        }
                
        print(f"Running {solver['name']} on {cnf_file}...")
        try:
            solver_results = solver_runner.run_solver(cnf_path=cnf_file, timeout=remaining_time)
            
            results.update(solver_results)
            results["status"] = solver_results.get("status", "UNKNOWN")
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            results["error"] = error_msg
            results["status"] = "ERROR"
            
        return results

    def thread(self):
        while True:
            try:
                task = self.task_queue.get()
                if task is None:
                    break
                    
                solver, cnf_file, self.timeout = task
                solver_runner = SolverRunner(solver["path"])
                
                self.process_task(solver_runner, solver, cnf_file)
                
            except queue.Empty:
                continue
            finally:
                self.task_queue.task_done()

    def process_task(self, solver_runner, solver, cnf_file):
        result = self.run_one(solver_runner, solver, cnf_file)
        with self.lock:
            self.results.append(result)

        if self.break_symmetry:
            try:
                modified_cnf, break_time = self.breaker.break_symmetries(cnf_file)
                if modified_cnf == "TIMEOUT" and break_time == -1:
                    timeout_result = {
                        "solver": solver["name"],
                        "original_cnf": Path(cnf_file).name,
                        "break_time": -1.0,
                        "status": "TIMEOUT",
                        "error": ""
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
                error_result = {
                    "solver": solver["name"],
                    "original_cnf": Path(cnf_file).name,
                    "break_time": -1.0,
                    "status": "SYM_BREAK_ERROR",
                    "error": f"{str(e)}"
                }
                with self.lock:
                    self.results.append(error_result)

    def run_all(self):
        self.results = []
        self.temp_files = []
        self.threads = []

        for i in range(self.maxthreads):
            worker = threading.Thread(target=self.thread)
            worker.daemon = True
            worker.start()
            self.threads.append(worker)
        
        for solver in self.solvers:
            for cnf_file in self.cnf_files:
                self.task_queue.put((solver, cnf_file, self.timeout))
       
        self.task_queue.join()
        
        for i in range(self.maxthreads):
            self.task_queue.put(None)
        for worker in self.threads:
            worker.join()
        
        self.cleanup_temp_files()
        
        return self.results

    def cleanup_temp_files(self):
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                print(f"Failed to delete temp file {temp_file}: {str(e)}")
        self.temp_files = []


    def log_results(self, results, output_path="multi_solver_results.csv"):
        import csv
        fieldnames = [
            "solver", "original_cnf", "break_time",
            "status", "exit_code", "time", "process_time", 
            "cpu_usage_avg", "cpu_usage_max", "memory_peak_mb", 
            "stderr", "error"
        ]
        print()
        
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for res in results:
                row = {field: res.get(field, "") for field in fieldnames}
                writer.writerow(row)