from pathlib import Path
from typing import Optional, Tuple, List
import copy

from factory import get_runner
from generic_executor import GenericExecutor
from custom_types import (TestCase, Result, ExecutionTriplet, 
    STATUS_BREAKER_ERROR, STATUS_ERROR, STATUS_TIMEOUT, CRITICAL_STATUSES, NULL_FORMULATOR, NULL_BREAKER)
from format_types import ExperimentContext, SolvingTask
from runner import Runner
from utils import make_error_result
import logging

logger = logging.getLogger(__name__)

class SymmetryBreaker:
    def __init__(self, executor: GenericExecutor):
        self.executor: GenericExecutor = executor

    def apply(self, task: SolvingTask, core_ids: List[int]) -> Tuple[Optional[TestCase], Result]:
        triplet: ExecutionTriplet = task.triplet
        test_case: TestCase = task.test_case
        work_dir: ExperimentContext = task.work_dir

        sym_filename: str = f"{test_case.name}.{triplet.solver.name}.{triplet.breaker.name}.sym{work_dir.format_info.suffix}"
        
        sym_path: Path = work_dir.base_path / sym_filename


        runner: Runner = get_runner(
            problem_type=task.triplet.breaker.solver_type,
            solv_cfg=task.triplet.breaker,
            executor=self.executor
        )

        try:
            br_res: Result = runner.run(
                input_file=test_case, 
                timeout=task.timeout, 
                output_path=sym_path, 
                core_ids=core_ids
            )

            if br_res.status != STATUS_TIMEOUT and br_res.status in CRITICAL_STATUSES:
                logger.error("[BREAKER] Error for %s: %s %s", test_case.name, br_res.stderr, br_res.error)
                return None, make_error_result(triplet=triplet, test_case=test_case, breaker_name=triplet.breaker.name, status=STATUS_BREAKER_ERROR, error=f"Breaker error: {br_res.error}", break_time=br_res.time)

            if not sym_path.exists() or sym_path.stat().st_size == 0:
                logger.error("[BREAKER] Did not produce a valid file at %s", sym_path)
                br_res.status = STATUS_BREAKER_ERROR
                br_res.error = "Empty or missing output file."
                return None, make_error_result(triplet=triplet, test_case=test_case, breaker_name=triplet.breaker.name, status=STATUS_BREAKER_ERROR, error="Empty or missing output file.", break_time=br_res.time)

            symmetry_test_case: TestCase = copy.deepcopy(test_case)
            symmetry_test_case.path = str(sym_path)
            #test_case.generated_files.append(sym_path) 
            
            return symmetry_test_case, br_res

        except Exception as e:
            logger.error("[BREAKER] Critical failure: %s", e)
            error_res = Result(
                solver=triplet.solver.name,
                problem=test_case.name,
                status=STATUS_BREAKER_ERROR,
                error=f"Breaker exception: {str(e)}",
                breaker=triplet.breaker.name
            )
            return None, make_error_result(triplet=triplet, test_case=test_case, breaker_name=triplet.breaker.name, status=STATUS_BREAKER_ERROR, error=f"Breaker exception: {str(e)}", break_time=0)

