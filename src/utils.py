from custom_types import Result, ExecutionTriplet, TestCase


def make_error_result(triplet: ExecutionTriplet, test_case: TestCase,
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