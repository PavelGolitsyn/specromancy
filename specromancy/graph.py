"""Generic directed-graph validation for configured pipelines."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Sequence
from typing import Any


GraphFailure = Callable[..., None]


def reachable_from(start: str, edges: dict[str, set[str]]) -> frozenset[str]:
    """Return all vertices reachable from *start*, including *start*."""

    seen: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(edges.get(current, set()) - seen)
    return frozenset(seen)


def strongly_connected_components(
    vertices: Iterable[str], edges: dict[str, set[str]]
) -> tuple[frozenset[str], ...]:
    """Return Tarjan strongly connected components in deterministic order."""

    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[frozenset[str]] = []

    def visit(vertex: str) -> None:
        nonlocal index
        indices[vertex] = index
        lowlinks[vertex] = index
        index += 1
        stack.append(vertex)
        on_stack.add(vertex)

        for target in sorted(edges.get(vertex, set())):
            if target not in indices:
                visit(target)
                lowlinks[vertex] = min(lowlinks[vertex], lowlinks[target])
            elif target in on_stack:
                lowlinks[vertex] = min(lowlinks[vertex], indices[target])

        if lowlinks[vertex] == indices[vertex]:
            component: set[str] = set()
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.add(member)
                if member == vertex:
                    break
            components.append(frozenset(component))

    for vertex in sorted(vertices):
        if vertex not in indices:
            visit(vertex)
    return tuple(components)


def _cyclic_components(
    vertices: Iterable[str], edges: dict[str, set[str]]
) -> tuple[frozenset[str], ...]:
    return tuple(
        component
        for component in strongly_connected_components(vertices, edges)
        if len(component) > 1
        or any(vertex in edges.get(vertex, set()) for vertex in component)
    )


def _producer_is_guaranteed(
    start: str,
    consumer: str,
    producer: str,
    edges: dict[str, set[str]],
) -> bool:
    """Whether every first route completes *producer* before *consumer*."""

    # Search for a counterexample route while treating arrival at the producer
    # as completion only when traversing an edge away from it. An immediate
    # arrival at a consumer cannot consume that visit's not-yet-written output.
    pending = [start]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if current == consumer:
            return False
        if current == producer:
            continue
        pending.extend(edges.get(current, set()))
    return True


def _visit_is_guaranteed(
    start: str, consumer: str, ordinal: int, edges: dict[str, set[str]]
) -> bool:
    """Whether at least *ordinal* outputs exist on every route to *consumer*."""

    pending = deque([(start, 0)])
    seen: set[str] = set()
    while pending:
        current, completed = pending.popleft()
        if current in seen:
            continue
        seen.add(current)
        if current == consumer:
            return completed >= ordinal
        after_current = completed + 1
        pending.extend(
            (target, after_current)
            for target in sorted(edges.get(current, set()))
        )
    return True


def validate_graph(
    phases: Sequence[Any],
    start: str,
    terminal_outcomes: frozenset[str] | set[str],
    fail: GraphFailure,
) -> None:
    """Validate phase connectivity, bounded cycles, and input producers.

    ``fail`` is supplied by the configuration layer so this module remains
    independent of diagnostic and domain-model implementation details.
    """

    phase_by_id: dict[str, Any] = {}
    for phase in phases:
        if phase.id in phase_by_id:
            fail(
                "duplicate-phase",
                f"phase id {phase.id!r} is declared more than once",
                phase=phase.id,
                field="id",
                value=phase.id,
                remediation="give every phase a unique id",
            )
        phase_by_id[phase.id] = phase

    if start not in phase_by_id:
        fail(
            "missing-start-phase",
            f"start phase {start!r} is not declared",
            field="start",
            value=start,
            remediation="set start to the id of a declared phase",
        )

    edges: dict[str, set[str]] = {phase.id: set() for phase in phases}
    bounded_edges: set[tuple[str, str]] = set()
    unbounded_edges: set[tuple[str, str]] = set()
    for phase in phases:
        seen_outcomes: set[str] = set()
        if not phase.transitions:
            fail(
                "missing-transition",
                f"phase {phase.id!r} has no possible outcome",
                phase=phase.id,
                field="transitions",
                value=[],
                remediation="declare at least one phase or terminal transition",
            )
        for transition in phase.transitions:
            if transition.outcome in seen_outcomes:
                fail(
                    "duplicate-outcome",
                    f"phase {phase.id!r} declares outcome {transition.outcome!r} more than once",
                    phase=phase.id,
                    field="transitions.outcome",
                    value=transition.outcome,
                    remediation="make transition outcomes unique within the phase",
                )
            seen_outcomes.add(transition.outcome)
            is_terminal = transition.outcome in terminal_outcomes
            if is_terminal:
                if transition.target is not None:
                    fail(
                        "terminal-outcome-target",
                        f"terminal outcome {transition.outcome!r} cannot target a phase",
                        phase=phase.id,
                        field="transitions.target",
                        value=transition.target,
                        remediation="remove target from the terminal transition",
                    )
                continue
            if transition.target is None:
                fail(
                    "missing-transition-target",
                    f"non-terminal outcome {transition.outcome!r} needs a target",
                    phase=phase.id,
                    field="transitions.target",
                    value=None,
                    remediation="name a declared phase or use a terminal outcome",
                )
            if transition.target not in phase_by_id:
                fail(
                    "unknown-transition-target",
                    f"outcome {transition.outcome!r} targets unknown phase {transition.target!r}",
                    phase=phase.id,
                    field="transitions.target",
                    value=transition.target,
                    remediation="target a declared phase",
                )
            edges[phase.id].add(transition.target)
            if transition.max_traversals is not None:
                bounded_edges.add((phase.id, transition.target))
            else:
                unbounded_edges.add((phase.id, transition.target))

    # Parallel outcomes are distinct runtime edges. Collapsing them for graph
    # traversal is safe only when every outcome between the pair is bounded.
    bounded_edges -= unbounded_edges

    reachable = reachable_from(start, edges)
    unreachable = sorted(set(phase_by_id) - reachable)
    if unreachable:
        fail(
            "unreachable-phase",
            f"phases are unreachable from {start!r}: {', '.join(unreachable)}",
            field="phases",
            value=unreachable,
            remediation="add transitions from the reachable graph or remove the phases",
        )

    # A collection of bounds is mechanically sufficient only if removing the
    # bounded phases and edges leaves no cycle. This is stronger than merely
    # finding one bound somewhere in a large strongly connected component.
    unbounded_vertices = {
        phase.id for phase in phases if phase.max_visits is None
    }
    unbounded_edges = {
        source: {
            target
            for target in targets
            if target in unbounded_vertices
            and (source, target) not in bounded_edges
        }
        for source, targets in edges.items()
        if source in unbounded_vertices
    }
    unbounded_cycles = _cyclic_components(unbounded_vertices, unbounded_edges)
    if unbounded_cycles:
        members = sorted(set().union(*unbounded_cycles))
        fail(
            "unbounded-cycle",
            f"cycle has no finite visit or traversal bound: {', '.join(members)}",
            field="phases.transitions",
            value=members,
            remediation="set max_visits on a phase or max_traversals on an edge in every cycle",
        )

    for phase in phases:
        for reference in phase.inputs:
            if reference == "request":
                continue
            if reference.startswith("visit:"):
                ordinal = int(reference.removeprefix("visit:"))
                if not _visit_is_guaranteed(start, phase.id, ordinal, edges):
                    fail(
                        "unavailable-input",
                        f"input {reference!r} cannot exist before phase {phase.id!r}",
                        phase=phase.id,
                        field="inputs",
                        value=reference,
                        remediation="reference an earlier visit or change the incoming graph",
                    )
                continue
            if not reference.startswith("latest:"):
                fail(
                    "invalid-input-reference",
                    f"phase {phase.id!r} has invalid input reference {reference!r}",
                    phase=phase.id,
                    field="inputs",
                    value=reference,
                    remediation="use request, latest:<phase>, or visit:<positive-number>",
                )
            producer = reference.removeprefix("latest:")
            if producer not in phase_by_id:
                fail(
                    "unknown-input-producer",
                    f"input {reference!r} names unknown phase {producer!r}",
                    phase=phase.id,
                    field="inputs",
                    value=reference,
                    remediation="name a phase that can produce an earlier artifact",
                )
            if not _producer_is_guaranteed(start, phase.id, producer, edges):
                fail(
                    "unavailable-input",
                    f"input {reference!r} is not produced on every route to phase {phase.id!r}",
                    phase=phase.id,
                    field="inputs",
                    value=reference,
                    remediation=(
                        "make the producer precede every incoming route or "
                        "remove the input"
                    ),
                )
