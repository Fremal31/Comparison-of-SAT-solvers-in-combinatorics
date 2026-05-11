from typing import Any

from custom_types import NULL_FORMULATOR, NULL_SOLVER, ExecutionTriplet, Result, Status, TestCase


def make_error_result(triplet: ExecutionTriplet, test_case: TestCase,
                           breaker_name: str, status: Status, error: str,
                           break_time: float = 0.0) -> Result:
    """Creates a Result for error/timeout cases with common fields pre-filled."""
    return Result(
        solver=triplet.solver.name if triplet.solver else NULL_SOLVER,
        problem=test_case.name,
        parent_problem=triplet.problem.name if triplet.problem else test_case.name,
        parameters=dict(triplet.parameters),
        breaker=breaker_name,
        formulator=triplet.formulator.name if triplet.formulator else NULL_FORMULATOR,
        status=status,
        error=error,
        time=0.0,
        break_time=break_time
    )


def format_parameters_tag(params: dict[str, Any]) -> str:
    """
    Stable, filesystem-safe string representation of a parameter dict.

    Used as a directory-name suffix and as the join key between phases. Keys
    are sorted alphabetically; values are str()-converted. Empty params -> "".

        format_parameters_tag({"q": 2, "p": 5}) == "p=5,q=2"
    """
    if not params:
        return ""
    return ",".join(f"{k}={params[k]}" for k in sorted(params))


def instance_dir_name(problem_name: str, params: dict[str, Any]) -> str:
    """Returns the working_dir subdirectory name for one (problem, parameters)
    instance. Falls back to *problem_name* alone when *params* is empty so
    parameter-free runs keep their existing layout."""
    tag = format_parameters_tag(params)
    return f"{problem_name}@{tag}" if tag else problem_name