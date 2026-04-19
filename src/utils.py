from custom_types import Result, ExecutionTriplet, TestCase, Status, NULL_FORMULATOR, NULL_BREAKER, NULL_SOLVER


def make_error_result(triplet: ExecutionTriplet, test_case: TestCase,
                           breaker_name: str, status: Status, error: str,
                           break_time: float = 0.0) -> Result:
    """Creates a Result for error/timeout cases with common fields pre-filled."""
    return Result(
        solver=triplet.solver.name if triplet.solver else NULL_SOLVER,
        problem=test_case.name,
        parent_problem=triplet.problem.name if triplet.problem else test_case.name,
        breaker=breaker_name,
        formulator=triplet.formulator.name if triplet.formulator else NULL_FORMULATOR,
        status=status,
        error=error,
        time=-1.0,
        break_time=break_time
    )