import pytest
from typing import Any, Dict, List

from custom_types import ExecConfig, FileConfig, FormulatorConfig
from utils import format_parameters_tag, instance_dir_name
from triplet_generator import (
    _generate_triplets, _expand_triplets, _problem_parameter_sweep,
)


def make_problem(name: str, parameters: List[Dict[str, Any]] = None) -> FileConfig:
    return FileConfig(name=name, path=f"/tmp/{name}.g6", parameters=parameters or [])


def make_formulator(name: str = "f", t: str = "SAT") -> FormulatorConfig:
    return FormulatorConfig(name=name, formulator_type=t, cmd="echo", enabled=True)


def make_solver(name: str = "s", t: str = "SAT") -> ExecConfig:
    return ExecConfig(name=name, solver_type=t, cmd="echo", enabled=True)


# ---------------------------------------------------------------------------
# _problem_parameter_sweep
# ---------------------------------------------------------------------------

class TestProblemParameterSweep:
    def test_no_parameters_returns_single_empty_dict(self):
        result = _problem_parameter_sweep(make_problem("p"))
        assert result == [{}]

    def test_with_parameters_returns_list(self):
        prob = make_problem("p", parameters=[{"k": 1}, {"k": 2}])
        assert _problem_parameter_sweep(prob) == [{"k": 1}, {"k": 2}]


# ---------------------------------------------------------------------------
# _generate_triplets — parameter expansion in cross-product mode
# ---------------------------------------------------------------------------

class TestGenerateTripletsParameters:
    def test_single_problem_no_parameters_yields_one_triplet(self):
        triplets = _generate_triplets(
            problems=[make_problem("p")],
            formulators=[make_formulator()],
            test_cases=[],
            solvers=[make_solver()],
            breakers=[],
        )
        assert len(triplets) == 1
        assert triplets[0].parameters == {}

    def test_single_problem_two_parameter_sets_yields_two_triplets(self):
        triplets = _generate_triplets(
            problems=[make_problem("p", parameters=[{"k": 1}, {"k": 2}])],
            formulators=[make_formulator()],
            test_cases=[],
            solvers=[make_solver()],
            breakers=[],
        )
        assert len(triplets) == 2
        assert {format_parameters_tag(t.parameters) for t in triplets} == {"k=1", "k=2"}

    def test_parameters_x_solvers_full_cross_product(self):
        triplets = _generate_triplets(
            problems=[make_problem("p", parameters=[{"k": 1}, {"k": 2}])],
            formulators=[make_formulator()],
            test_cases=[],
            solvers=[make_solver("s1"), make_solver("s2")],
            breakers=[],
        )
        # 2 params x 2 solvers
        assert len(triplets) == 4

    def test_parameters_x_breakers_full_cross_product(self):
        triplets = _generate_triplets(
            problems=[make_problem("p", parameters=[{"k": 1}])],
            formulators=[make_formulator()],
            test_cases=[],
            solvers=[make_solver()],
            breakers=[make_solver("b1")],
        )
        # 1 param × 1 solver × (no-breaker + 1 breaker) = 2
        assert len(triplets) == 2

    def test_parameters_dict_is_independent_per_triplet(self):
        triplets = _generate_triplets(
            problems=[make_problem("p", parameters=[{"k": 1}])],
            formulators=[make_formulator()],
            test_cases=[],
            solvers=[make_solver()],
            breakers=[],
        )
        triplets[0].parameters["k"] = 99
        # subsequent regeneration must not see the mutation
        again = _generate_triplets(
            problems=[make_problem("p", parameters=[{"k": 1}])],
            formulators=[make_formulator()],
            test_cases=[],
            solvers=[make_solver()],
            breakers=[],
        )
        assert again[0].parameters == {"k": 1}


# ---------------------------------------------------------------------------
# _expand_triplets preserves parameters across solver expansion
# ---------------------------------------------------------------------------

class TestExpandTripletsParameters:
    def test_preserves_parameters(self):
        from custom_types import ExecutionTriplet
        t = ExecutionTriplet(
            problem=make_problem("p"),
            formulator=make_formulator(),
            solver=None,
            parameters={"p": 5, "q": 2},
        )
        expanded = _expand_triplets([t], [make_solver("s1"), make_solver("s2")])
        assert len(expanded) == 2
        for e in expanded:
            assert e.parameters == {"p": 5, "q": 2}


# ---------------------------------------------------------------------------
# format_parameters_tag and instance_dir_name
# ---------------------------------------------------------------------------

class TestFormatParametersTag:
    def test_empty_dict_returns_empty_string(self):
        assert format_parameters_tag({}) == ""

    def test_single_param(self):
        assert format_parameters_tag({"p": 5}) == "p=5"

    def test_keys_sorted_alphabetically(self):
        assert format_parameters_tag({"q": 2, "p": 5}) == "p=5,q=2"

    def test_stable_ordering(self):
        a = format_parameters_tag({"a": 1, "b": 2, "c": 3})
        b = format_parameters_tag({"c": 3, "b": 2, "a": 1})
        assert a == b


class TestInstanceDirName:
    def test_no_params_falls_back_to_problem_name(self):
        assert instance_dir_name("graph", {}) == "graph"

    def test_with_params_uses_at_separator(self):
        assert instance_dir_name("graph", {"p": 5, "q": 2}) == "graph@p=5,q=2"
