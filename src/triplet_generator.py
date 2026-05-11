import logging
from typing import Any

from custom_types import NULL_FORMULATOR, Config, ExecConfig, ExecutionTriplet, FileConfig, FormulatorConfig, TestCase

logger = logging.getLogger(__name__)

def create_dummy_problem_formulator_from_testcase(tc: TestCase) -> tuple[FileConfig, FormulatorConfig]:
    """Creates placeholder FileConfig and FormulatorConfig for pre-encoded files that skip conversion."""
    dummy_prob_cfg = FileConfig(name=tc.name, path=str(tc.path))
    dummy_formulator = FormulatorConfig(
        name=NULL_FORMULATOR, 
        formulator_type=tc.tc_type,
        cmd="", 
        enabled=True
    )
    return dummy_prob_cfg, dummy_formulator

def build_triplets(
    config: Config,
    problems: list[FileConfig],
    formulators: list[FormulatorConfig],
    solvers: list[ExecConfig],
    breakers: list[ExecConfig],
) -> tuple[list[TestCase], list[ExecutionTriplet]]:
    """Generates the full list of execution triplets and pre-encoded test cases from config."""
    test_cases: list[TestCase] = []

    if config.triplet_mode:
        for triplet in config.triplets:
            if triplet.test_case:
                test_cases.append(triplet.test_case)
                problem_cfg, formulator_cfg = create_dummy_problem_formulator_from_testcase(triplet.test_case)
                triplet.problem = problem_cfg
                triplet.formulator = formulator_cfg
        triplets: list[ExecutionTriplet] = _expand_triplets(triplets=config.triplets, solvers=solvers)
        logger.info("Triplet mode enabled: Using %d triplets (after expansion)", len(triplets))
        return test_cases, triplets

    for file_wo_converter in config.without_converter:
        if file_wo_converter.enabled:
            test_cases.append(TestCase(
                name=file_wo_converter.name,
                path=file_wo_converter.path,
                problem_cfg=None,
                formulator_cfg=None,
                tc_type=file_wo_converter.tc_type
            ))
    triplets = _generate_triplets(
        problems=problems, formulators=formulators,
        test_cases=test_cases, solvers=solvers, breakers=breakers
    )
    logger.info("Generated %d triplets from config", len(triplets))
    return test_cases, triplets

def _expand_triplets(triplets: list[ExecutionTriplet], solvers: list[ExecConfig]) -> list[ExecutionTriplet]:
    """
    Expands triplets that have no solver set into one triplet per compatible
    enabled solver. Triplets with a solver set are passed through unchanged.
    """
    expanded: list[ExecutionTriplet] = []
    for t in triplets:
        if t.solver is not None:
            expanded.append(t)
            continue

        target_type = t.formulator.formulator_type if t.formulator else None
        compatible = [s for s in solvers if s.solver_type == target_type]
        if not compatible:
            logger.warning("No compatible enabled solvers for type '%s' — skipping triplet.", target_type)
            continue

        for solver in compatible:
            expanded.append(ExecutionTriplet(
                problem=t.problem,
                formulator=t.formulator,
                solver=solver,
                breaker=t.breaker,
                test_case=t.test_case,
                parameters=dict(t.parameters),
            ))
    return expanded

def _triplets_with_breakers(
    problem: FileConfig,
    formulator: FormulatorConfig,
    solver: ExecConfig,
    breakers: list[ExecConfig],
    parameters: dict[str, Any],
) -> list[ExecutionTriplet]:
    result = [ExecutionTriplet(problem=problem, formulator=formulator, solver=solver, parameters=dict(parameters))]
    result += [
        ExecutionTriplet(problem=problem, formulator=formulator, solver=solver, breaker=b, parameters=dict(parameters))
        for b in breakers
        if b.solver_type == solver.solver_type
    ]
    return result


def _problem_parameter_sweep(problem: FileConfig) -> list[dict[str, Any]]:
    """Returns the per-instance parameter dicts to expand a problem into.
    A FileConfig with no declared parameters yields a single empty dict so the
    rest of the pipeline behaves as it did before parameter sweeps existed."""
    return list(problem.parameters) if problem.parameters else [{}]


def _generate_triplets(
    problems: list[FileConfig],
    formulators: list[FormulatorConfig],
    test_cases: list[TestCase],
    solvers: list[ExecConfig],
    breakers: list[ExecConfig],
) -> list[ExecutionTriplet]:
    """
    Generates the full cross-product of compatible execution combinations.

    Solver type must match formulator type for a pair to be included.
    For each valid (problem, parameters, formulator, solver) combination, one
    triplet without a breaker is added, plus one additional triplet per
    compatible breaker. A problem with no declared *parameters* contributes
    a single (empty-parameters) instance.
    """
    all_triplets: list[ExecutionTriplet] = []

    for problem in problems:
        for params in _problem_parameter_sweep(problem):
            for formulator in formulators:
                for solver in [s for s in solvers if s.solver_type == formulator.formulator_type]:
                    all_triplets += _triplets_with_breakers(problem, formulator, solver, breakers, params)

    for tc in test_cases:
        dummy_prob_cfg, dummy_formulator = create_dummy_problem_formulator_from_testcase(tc=tc)
        for solver in [s for s in solvers if s.solver_type == tc.tc_type]:
            all_triplets += _triplets_with_breakers(dummy_prob_cfg, dummy_formulator, solver, breakers, {})

    return all_triplets
    