from __future__ import annotations

from collections.abc import Iterable

from services.workspace.dependency_graph import DependencyGraph

from .base import ValidationIssue, ValidationReport


def validate_dependencies(graph: DependencyGraph, existing_refs: Iterable[str]) -> ValidationReport:
    return ValidationReport.from_iterable(
        ValidationIssue(
            "DANGLING_DEPENDENCY",
            f"依赖边引用不存在对象: {edge.source_ref} -> {edge.target_ref}",
            edge.target_ref,
        )
        for edge in graph.dangling_edges(existing_refs)
    )
