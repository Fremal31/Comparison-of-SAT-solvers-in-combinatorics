import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional

from breaker import SymmetryBreaker
from core_allocator import CoreAllocator
from custom_types import (
    ExecConfig, ExecutionTriplet, Result, RunnerError, TestCase,
    Status, CRITICAL_STATUSES, NULL_BREAKER, NULL_FORMULATOR,
)
from factory import get_runner
from format_types import ExperimentContext, SolvingTask
from generic_executor import GenericExecutor
from runner import Runner
from utils import make_error_result

logger = logging.getLogger(__name__)


def shuffle_tasks(tasks: List[SolvingTask]) -> List[SolvingTask]:
    """
    Reorders tasks round-robin by problem name to minimise L3 cache and memory
    bandwidth contention by spacing identical problems as far apart as possible.
    """
    tasks_by_problem: Dict[str, List[SolvingTask]] = defaultdict(list)
    for task in tasks:
        tasks_by_problem[task.test_case.name].append(task)

    interleaved: List[SolvingTask] = []
    problem_names = sorted(tasks_by_problem.keys())
    while tasks_by_problem:
        for name in problem_names:
            if name in tasks_by_problem:
                interleaved.append(tasks_by_problem[name].pop(0))
                if not tasks_by_problem[name]:
                    del tasks_by_problem[name]
    return interleaved


class SolvingPhase:
    """
    Phase 2 of the benchmark pipeline: runs solvers (with optional symmetry
    breaking) on converted test cases in parallel.
    """

    def __init__(
        self,
        executor: GenericExecutor,
        breaker: SymmetryBreaker,
        core_allocator: Optional[CoreAllocator],
    ) -> None:
        self.executor = executor
        self.breaker = breaker
        self.core_allocator = core_allocator

    def run(
        self,
        tasks: List[SolvingTask],
        max_threads: int,
        call_on_result: Optional[Callable[[Result], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> List[Result]:
        """
        Runs all solving tasks in parallel.

        Calls *call_on_result* for each Result as it completes (main thread,
        no locking needed). Calls *on_complete* in the finally block regardless
        of success or failure (used for file cleanup).
        """
        results: List[Result] = []
        if not tasks:
            if on_complete:
                on_complete()
            return results

        with ThreadPoolExecutor(max_workers=max_threads) as pool:
            try:
                futures: Dict[Future[Result], SolvingTask] = {
                    pool.submit(self._worker_solve, task): task for task in tasks
                }
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    if call_on_result:
                        call_on_result(result)
                    cores_str = f"Cores {result.cores_used}" if result.cores_used else "No Pinning"
                    breaker_tag = "_" + result.breaker if result.breaker != NULL_BREAKER else ""
                    logger.info(
                        "[%d/%d] Done: %s%s on %s",
                        len(results), len(tasks), result.solver, breaker_tag, result.problem,
                    )
                    logger.info(
                        "Result: Solver %s%s, Problem %s, Status %s, Time %.2fs, %s, Error: %s",
                        result.solver, breaker_tag, result.problem, result.status,
                        result.total_time, cores_str, result.error or "None",
                    )
            except KeyboardInterrupt:
                logger.error("Interrupted. Cancelling remaining tasks...")
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            finally:
                if on_complete:
                    on_complete()
                logger.info("Completed %d/%d solver runs.", len(results), len(tasks))

        return results

    def _worker_solve(self, task: SolvingTask) -> Result:
        """
        Optionally applies symmetry breaking then runs the solver.
        Returns the solver Result, or a BREAKER_ERROR Result if breaking fails.
        """
        triplet: ExecutionTriplet = task.triplet
        if not triplet.solver:
            raise ValueError("Solver is None")
        solver_cfg: ExecConfig = triplet.solver
        breaker_cfg: Optional[ExecConfig] = triplet.breaker

        test_case: TestCase = task.test_case
        work_dir: ExperimentContext = task.work_dir

        p_type: str = (
            task.test_case.tc_type
            if task.test_case.tc_type and task.test_case.tc_type != "UNKNOWN"
            else (triplet.formulator.formulator_type if triplet.formulator else "UNKNOWN")
        )
        breaker_name: str = breaker_cfg.name if breaker_cfg else NULL_BREAKER
        log_name = (
            f"{test_case.name}.{solver_cfg.name}_{breaker_cfg.name}.out"
            if breaker_cfg else
            f"{test_case.name}.{solver_cfg.name}.out"
        )
        path_out: Path = work_dir.log_dir / log_name

        assigned_cores: List[int] = []
        if self.core_allocator:
            req = solver_cfg.threads
            if task.triplet.breaker:
                req = max(req, task.triplet.breaker.threads)
            assigned_cores = self.core_allocator.request(count=req)

        try:
            if breaker_cfg:
                processed_tc, breaker_result = self.breaker.apply(task=task, core_ids=assigned_cores)
                if processed_tc is None or breaker_result.status in CRITICAL_STATUSES:
                    return breaker_result
                test_case = processed_tc
                breaker_metrics: Optional[Result] = breaker_result
            else:
                breaker_metrics = None

            break_time: float = breaker_metrics.time if breaker_metrics else 0.0
            remaining_timeout: float = max(0.0, task.timeout - break_time)
            if remaining_timeout <= 0.0:
                return make_error_result(
                    triplet, test_case, breaker_name, Status.TIMEOUT,
                    "No time remaining after symmetry breaking.", break_time,
                )

            try:
                runner: Runner = get_runner(
                    problem_type=p_type, solv_cfg=solver_cfg, executor=self.executor
                )
                result: Result = runner.run(
                    input_file=test_case, timeout=remaining_timeout,
                    output_path=path_out, core_ids=assigned_cores,
                )
                result.solver = solver_cfg.name
                result.problem = test_case.name
                if not triplet.problem:
                    raise ValueError("Problem is None.")
                result.parent_problem = triplet.problem.name
                result.breaker = breaker_name
                result.formulator = (
                    test_case.formulator_cfg.name if test_case.formulator_cfg else NULL_FORMULATOR
                )
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
                    triplet, test_case, breaker_name, Status.ERROR,
                    f"Runner Failure: {e}", break_time,
                )
            except Exception as e:
                return make_error_result(
                    triplet, test_case, breaker_name, Status.ERROR, str(e), break_time,
                )
        finally:
            if self.core_allocator:
                self.core_allocator.release(cores=assigned_cores)
