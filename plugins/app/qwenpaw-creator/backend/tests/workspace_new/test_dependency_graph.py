from __future__ import annotations

from services.validators.dependency import validate_dependencies
from services.workspace.dependency_graph import DependencyEdge, DependencyGraph, DependencyStrength


def test_hard_components_form_independent_review_groups() -> None:
    graph = DependencyGraph(
        (
            DependencyEdge("unit:u1", "section:s1/sequence", DependencyStrength.HARD, "delete closure"),
            DependencyEdge("section:s1/sequence", "post:final", DependencyStrength.HARD, "compose selection"),
            DependencyEdge("visual:hero", "unit:u2", DependencyStrength.SOFT, "continuity candidate"),
        )
    )
    components = graph.hard_components(("unit:u1", "section:s1/sequence", "post:final", "visual:hero", "unit:u2"))
    assert frozenset({"unit:u1", "section:s1/sequence", "post:final"}) in components
    assert frozenset({"visual:hero"}) in components
    assert frozenset({"unit:u2"}) in components


def test_impact_closure_distinguishes_hard_and_soft_edges() -> None:
    graph = DependencyGraph(
        (
            DependencyEdge("story:b1", "unit:u1", DependencyStrength.HARD, "narrative"),
            DependencyEdge("unit:u1", "artifact:v1", DependencyStrength.HARD, "production"),
            DependencyEdge("story:b1", "visual:hero", DependencyStrength.SOFT, "candidate"),
        )
    )
    assert graph.impact_closure(("story:b1",), include_soft=False) == frozenset(
        {"story:b1", "unit:u1", "artifact:v1"}
    )
    assert "visual:hero" in graph.impact_closure(("story:b1",), include_soft=True)


def test_dangling_dependency_is_reported() -> None:
    graph = DependencyGraph((DependencyEdge("unit:u1", "artifact:missing", DependencyStrength.HARD, "selection"),))
    report = validate_dependencies(graph, ("unit:u1",))
    assert not report.valid
    assert report.issues[0].code == "DANGLING_DEPENDENCY"
