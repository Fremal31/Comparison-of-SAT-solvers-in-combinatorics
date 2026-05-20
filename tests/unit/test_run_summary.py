from typing import List

from custom_types import Result
from run_summary import validate_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(solver: str = "kissat", problem: str = "test", status: str = "SAT",
                time: float = 1.0, conflicts: int = 42) -> Result:
    return Result(solver=solver, problem=problem, status=status, time=time,
                  metrics={"conflicts": conflicts})


def make_results() -> List[Result]:
    return [
        make_result(solver="kissat", problem="p1", status="SAT", time=1.0, conflicts=10),
        make_result(solver="cadical", problem="p1", status="UNSAT", time=2.0, conflicts=20),
    ]


# ---------------------------------------------------------------------------
# validate_status
# ---------------------------------------------------------------------------

class TestValidateStatus:
    def test_conflict_present(self):
        conflicts = validate_status(make_results())
        assert len(conflicts) == 1

    def test_conflict_not_present(self):
        conflicts = validate_status([make_result(), make_result()])
        assert len(conflicts) == 0

    def test_different_parameters_are_not_a_conflict(self):
        """SAT for one (p,q) and UNSAT for another on the same graph is the
        whole point of a parameter sweep — must not be flagged."""
        r_sat = make_result(solver="kissat", problem="p1", status="SAT")
        r_sat.parameters = {"p": 4, "q": 1}
        r_unsat = make_result(solver="kissat", problem="p1", status="UNSAT")
        r_unsat.parameters = {"p": 3, "q": 1}
        conflicts = validate_status([r_sat, r_unsat])
        assert conflicts == []

    def test_conflict_within_same_parameters_still_detected(self):
        r_sat = make_result(solver="kissat", problem="p1", status="SAT")
        r_sat.parameters = {"p": 4, "q": 1}
        r_unsat = make_result(solver="cadical", problem="p1", status="UNSAT")
        r_unsat.parameters = {"p": 4, "q": 1}
        conflicts = validate_status([r_sat, r_unsat])
        assert len(conflicts) == 1
        assert "p=4,q=1" in conflicts[0]

    def test_different_encodings_of_same_parent_problem_are_compared(self):
        """Two encodings of the same underlying instance produce different
        test-case names but share parent_problem. They must still be
        grouped so that a SAT/UNSAT disagreement is caught."""
        r_sat = make_result(solver="circular_cpsat", problem="petersen.g6", status="SAT")
        r_sat.parent_problem = "petersen"
        r_sat.parameters = {"p": 9, "q": 2}
        r_unsat = make_result(solver="kissat", problem="petersen_circ_e_p9_q2.cnf", status="UNSAT")
        r_unsat.parent_problem = "petersen"
        r_unsat.parameters = {"p": 9, "q": 2}
        conflicts = validate_status([r_sat, r_unsat])
        assert len(conflicts) == 1
        assert "petersen" in conflicts[0]
        assert "p=9,q=2" in conflicts[0]
