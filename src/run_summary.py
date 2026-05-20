"""Aggregation of per-run solver results into a per-instance summary.

This module is the single source of truth for "what did the solvers conclude".
It groups raw Results by (parent_problem, parameters) and produces a verdict
per instance, which is then consumed by:

  - validate_status      : conflict detection (SAT vs UNSAT disagreement)
  - render_summary_text  : console rendering
  - graph.render_summary_html : HTML rendering (lives in graph.py with the rest
                                of the HTML code, but reads RunSummary from here)

Grouping by parent_problem rather than by per-formulator test-case name means
different encodings of the same underlying instance (e.g. a SAT CNF and a
CP-SAT graph6) are compared against each other.
"""

from dataclasses import dataclass, field
from typing import Any

from custom_types import Result, Status
from utils import format_parameters_tag


@dataclass
class InstanceSummary:
    """Consensus over all solver runs for one (problem, parameters) instance.

    problem       — parent problem name (encoding-independent)
    params_tag    — stable parameter tag, e.g. "p=9,q=2", or "" if none
    verdict       — "SAT" | "UNSAT" | "CONFLICT" | "UNKNOWN"
    sat_solvers   — sorted "solver [formulator]" labels that returned SAT
    unsat_solvers — sorted labels that returned UNSAT
    inconclusive  — count of runs that timed out, errored, or returned UNKNOWN
    """
    problem: str
    params_tag: str
    verdict: str
    sat_solvers: list[str] = field(default_factory=list)
    unsat_solvers: list[str] = field(default_factory=list)
    inconclusive: int = 0


@dataclass
class RunSummary:
    """Aggregated view of a run: one InstanceSummary per (problem, parameters)."""
    instances: list[InstanceSummary] = field(default_factory=list)

    @property
    def conflicts(self) -> list[InstanceSummary]:
        return [i for i in self.instances if i.verdict == "CONFLICT"]


def build_run_summary(results: list[Result]) -> RunSummary:
    """Single aggregation pass over *results*, grouped by (parent_problem,
    parameters)."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in results:
        if not r.solver:
            raise ValueError("solver is None")
        parent = r.parent_problem or r.problem
        if not parent:
            raise ValueError("Problem name is None")
        params_tag = format_parameters_tag(r.parameters) if r.parameters else ""
        g = groups.setdefault((parent, params_tag), {"sat": set(), "unsat": set(), "other": 0})
        label = f"{r.solver} [{r.formulator}]"
        if r.status == Status.SAT:
            g["sat"].add(label)
        elif r.status == Status.UNSAT:
            g["unsat"].add(label)
        else:
            g["other"] += 1

    instances: list[InstanceSummary] = []
    for problem, params_tag in sorted(groups):
        g = groups[(problem, params_tag)]
        sat_solvers = sorted(g["sat"])
        unsat_solvers = sorted(g["unsat"])
        if sat_solvers and unsat_solvers:
            verdict = "CONFLICT"
        elif sat_solvers:
            verdict = "SAT"
        elif unsat_solvers:
            verdict = "UNSAT"
        else:
            verdict = "UNKNOWN"
        instances.append(InstanceSummary(
            problem=problem, params_tag=params_tag, verdict=verdict,
            sat_solvers=sat_solvers, unsat_solvers=unsat_solvers,
            inconclusive=g["other"],
        ))
    return RunSummary(instances=instances)


def format_conflict(inst: InstanceSummary) -> str:
    """One-line human-readable description of a SAT/UNSAT disagreement."""
    label = f"{inst.problem} ({inst.params_tag})" if inst.params_tag else inst.problem
    sat = ", ".join(inst.sat_solvers)
    unsat = ", ".join(inst.unsat_solvers)
    return f"CONFLICT on {label}: {Status.SAT} by [{sat}], {Status.UNSAT} by [{unsat}]"


def validate_status(results: list[Result]) -> list[str]:
    """Returns one warning string per (parent_problem, parameters) instance on
    which at least one solver reported SAT and another reported UNSAT. Empty
    list means all solvers and encodings agree. Thin wrapper over
    build_run_summary so the grouping logic lives in exactly one place.
    """
    return [format_conflict(i) for i in build_run_summary(results).conflicts]


def render_summary_text(summary: RunSummary) -> str:
    """Console-friendly rendering: an agreement banner, a one-row-per-instance
    verdict table, and the conflict details if any."""
    instances = summary.instances
    conflicts = summary.conflicts
    lines: list[str] = ["=" * 64, f"RUN SUMMARY: {len(instances)} instance(s)"]
    if conflicts:
        lines.append(f"  WARNING: {len(conflicts)} conflict(s) - solvers disagree")
    else:
        lines.append("  OK: 0 conflicts - all solvers agree on every instance")
    lines.append("-" * 64)

    pw = min(max((len(i.problem) for i in instances), default=7), 40)
    lines.append(f"{'problem':<{pw}}  {'params':<12}  {'verdict':<8}  agree")
    for i in instances:
        agree = len(i.sat_solvers) + len(i.unsat_solvers)
        prob = i.problem if len(i.problem) <= pw else i.problem[: pw - 1] + "…"
        lines.append(f"{prob:<{pw}}  {(i.params_tag or '-'):<12}  {i.verdict:<8}  {agree}")

    if conflicts:
        lines.append("-" * 64)
        for c in conflicts:
            lines.append("  " + format_conflict(c))
    lines.append("=" * 64)
    return "\n".join(lines)
