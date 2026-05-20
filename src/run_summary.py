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

import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from custom_types import NULL_BREAKER, NULL_FORMULATOR, Result, Status
from utils import format_parameters_tag


def method_label(result: Result) -> str:
    """Identifier for one solving method: the solver, its formulation
    (formulator), and its symmetry breaker if any. Including the formulator
    means different encodings of the same problem (e.g. a SAT CNF and a
    CP-SAT model) rank as distinct methods, which is what answers
    'which formulation was best'."""
    label = result.solver or "?"
    if result.formulator and result.formulator != NULL_FORMULATOR:
        label += f" [{result.formulator}]"
    if result.breaker and result.breaker != NULL_BREAKER:
        label += f" +{result.breaker}"
    return label


@dataclass
class InstanceSummary:
    """Consensus over all solver runs for one (problem, parameters) instance.

    problem        — parent problem name (encoding-independent)
    params_tag     — stable parameter tag, e.g. "p=9,q=2", or "" if none
    verdict        — "SAT" | "UNSAT" | "CONFLICT" | "UNKNOWN"
    sat_solvers    — sorted "solver [formulator]" labels that returned SAT
    unsat_solvers  — sorted labels that returned UNSAT
    inconclusive   — count of runs that timed out, errored, or returned UNKNOWN
    fastest_method — method with the smallest solve time on this instance, or
                     None if no run solved it
    fastest_time   — that smallest solve time in seconds, or None
    """
    problem: str
    params_tag: str
    verdict: str
    sat_solvers: list[str] = field(default_factory=list)
    unsat_solvers: list[str] = field(default_factory=list)
    inconclusive: int = 0
    fastest_method: Optional[str] = None
    fastest_time: Optional[float] = None


@dataclass
class SolverStats:
    """Aggregate performance of one method (solver, optionally + symmetry
    breaker) across every run it participated in.

    method      — method label (solver, formulation, optional breaker)
    solved      — runs that returned SAT or UNSAT
    timeouts    — runs that timed out
    errors      — runs that errored or returned UNKNOWN
    runs        — total runs
    par2        — PAR-2: penalised average runtime, factor 2. Mean over all
                  runs of (total_time if solved, else 2*timeout). Lower is
                  better. The SAT Competition ranking metric. total_time
                  includes conversion + symmetry breaking + solve.
    median_time — median total_time over the solved runs (0 if none)
    """
    method: str
    solved: int
    timeouts: int
    errors: int
    runs: int
    par2: float
    median_time: float


@dataclass
class RunSummary:
    """Aggregated view of a run: one InstanceSummary per (problem, parameters),
    plus an optional per-method leaderboard (populated when a timeout is known)."""
    instances: list[InstanceSummary] = field(default_factory=list)
    solver_stats: list[SolverStats] = field(default_factory=list)

    @property
    def conflicts(self) -> list[InstanceSummary]:
        return [i for i in self.instances if i.verdict == "CONFLICT"]

    @property
    def verdict_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.instances:
            counts[i.verdict] = counts.get(i.verdict, 0) + 1
        return counts


def _build_solver_stats(results: list[Result], timeout: float) -> list[SolverStats]:
    """Per-method leaderboard. A method is a solver plus its symmetry breaker
    if any, so plain / breakid / satsuma variants of one solver rank
    separately. Sorted by PAR-2 ascending (best first)."""
    by_method: dict[str, dict[str, Any]] = {}
    for r in results:
        method = method_label(r)
        m = by_method.setdefault(method, {"solved_times": [], "timeouts": 0, "errors": 0, "runs": 0})
        m["runs"] += 1
        # total_time = conversion + symmetry breaking + solve, so a method
        # using a symmetry breaker is charged for the breaker's cost and a
        # formulation is charged for its encoding cost.
        if r.status in (Status.SAT, Status.UNSAT):
            m["solved_times"].append(float(r.total_time))
        elif r.status == Status.TIMEOUT:
            m["timeouts"] += 1
        else:
            m["errors"] += 1

    stats: list[SolverStats] = []
    for method, m in by_method.items():
        solved_times: list[float] = m["solved_times"]
        unsolved = m["timeouts"] + m["errors"]
        runs = m["runs"]
        # PAR-2: penalised average runtime, factor 2 (the SAT Competition
        # ranking metric). Average over all runs, unsolved runs penalised at
        # 2*timeout.
        par2 = (sum(solved_times) + unsolved * 2.0 * float(timeout)) / runs if runs else 0.0
        median = statistics.median(solved_times) if solved_times else 0.0
        stats.append(SolverStats(
            method=method, solved=len(solved_times), timeouts=m["timeouts"],
            errors=m["errors"], runs=runs, par2=par2, median_time=median,
        ))
    stats.sort(key=lambda s: (s.par2, -s.solved))
    return stats


def build_run_summary(results: list[Result], timeout: Optional[float] = None) -> RunSummary:
    """Single aggregation pass over *results*, grouped by (parent_problem,
    parameters). If *timeout* is given, also builds the per-method PAR-2
    leaderboard (which needs the timeout to penalise unsolved runs)."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in results:
        if not r.solver:
            raise ValueError("solver is None")
        parent = r.parent_problem or r.problem
        if not parent:
            raise ValueError("Problem name is None")
        params_tag = format_parameters_tag(r.parameters) if r.parameters else ""
        g = groups.setdefault(
            (parent, params_tag),
            {"sat": set(), "unsat": set(), "other": 0, "best_t": None, "best_m": None},
        )
        label = f"{r.solver} [{r.formulator}]"
        if r.status == Status.SAT or r.status == Status.UNSAT:
            (g["sat"] if r.status == Status.SAT else g["unsat"]).add(label)
            t = float(r.total_time)  # conversion + breaking + solve
            if g["best_t"] is None or t < g["best_t"]:
                g["best_t"] = t
                g["best_m"] = method_label(r)
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
            fastest_method=g["best_m"], fastest_time=g["best_t"],
        ))

    solver_stats = _build_solver_stats(results, timeout) if timeout is not None else []
    return RunSummary(instances=instances, solver_stats=solver_stats)


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
    lines.append(
        f"{'problem':<{pw}}  {'params':<12}  {'verdict':<8}  {'agree':>5}  "
        f"{'fastest':<24}  {'time_s':>8}"
    )
    for i in instances:
        agree = len(i.sat_solvers) + len(i.unsat_solvers)
        prob = i.problem if len(i.problem) <= pw else i.problem[: pw - 1] + "…"
        fm = i.fastest_method or "-"
        fm = fm if len(fm) <= 24 else fm[:23] + "…"
        ft = f"{i.fastest_time:.3f}" if i.fastest_time is not None else "-"
        lines.append(
            f"{prob:<{pw}}  {(i.params_tag or '-'):<12}  {i.verdict:<8}  {agree:>5}  "
            f"{fm:<24}  {ft:>8}"
        )

    counts = summary.verdict_counts
    if counts:
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        lines.append("-" * 64)
        lines.append(f"verdicts: {breakdown}")

    if summary.solver_stats:
        lines.append("-" * 64)
        lines.append("LEADERBOARD (by PAR-2, lower is better)")
        mw = min(max(len(s.method) for s in summary.solver_stats), 32)
        lines.append(f"{'method':<{mw}}  {'solved':>6}  {'t/o':>4}  {'err':>4}  {'PAR-2':>10}  {'median_s':>8}")
        for s in summary.solver_stats:
            meth = s.method if len(s.method) <= mw else s.method[: mw - 1] + "…"
            lines.append(
                f"{meth:<{mw}}  {s.solved:>6}  {s.timeouts:>4}  {s.errors:>4}  "
                f"{s.par2:>10.3f}  {s.median_time:>8.3f}"
            )

    if conflicts:
        lines.append("-" * 64)
        for c in conflicts:
            lines.append("  " + format_conflict(c))
    lines.append("=" * 64)
    return "\n".join(lines)
