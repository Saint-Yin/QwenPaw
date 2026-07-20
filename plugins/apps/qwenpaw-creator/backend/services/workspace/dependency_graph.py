# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=unnecessary-lambda
"""Governance-only dependency graph; it is never written into Agent Workspace."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class DependencyStrength(StrEnum):
    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source_ref: str
    target_ref: str
    strength: DependencyStrength
    reason: str
    provenance_ref: str | None = None


class DependencyGraph:
    def __init__(self, edges: Iterable[DependencyEdge] = ()) -> None:
        self._edges: set[DependencyEdge] = set(edges)

    @property
    def edges(self) -> tuple[DependencyEdge, ...]:
        return tuple(
            sorted(
                self._edges,
                key=lambda item: (
                    item.source_ref,
                    item.target_ref,
                    item.strength.value,
                    item.reason,
                ),
            ),
        )

    def add(self, edge: DependencyEdge) -> None:
        if edge.source_ref == edge.target_ref:
            raise ValueError("dependency self-edge is not allowed")
        self._edges.add(edge)

    def remove_for(self, ref: str) -> None:
        self._edges = {
            edge
            for edge in self._edges
            if ref not in {edge.source_ref, edge.target_ref}
        }

    def direct_dependents(
        self,
        ref: str,
        *,
        strength: DependencyStrength | None = None,
    ) -> frozenset[str]:
        return frozenset(
            edge.target_ref
            for edge in self._edges
            if edge.source_ref == ref
            and (strength is None or edge.strength == strength)
        )

    def impact_closure(
        self,
        roots: Iterable[str],
        *,
        include_soft: bool = True,
    ) -> frozenset[str]:
        visited = set(roots)
        queue = list(visited)
        while queue:
            current = queue.pop(0)
            for edge in self._edges:
                if edge.source_ref != current or (
                    not include_soft
                    and edge.strength != DependencyStrength.HARD
                ):
                    continue
                if edge.target_ref not in visited:
                    visited.add(edge.target_ref)
                    queue.append(edge.target_ref)
        return frozenset(visited)

    def hard_components(
        self,
        refs: Iterable[str],
    ) -> tuple[frozenset[str], ...]:
        remaining = set(refs)
        adjacency: dict[str, set[str]] = {ref: set() for ref in remaining}
        for edge in self._edges:
            if edge.strength != DependencyStrength.HARD:
                continue
            if edge.source_ref in remaining and edge.target_ref in remaining:
                adjacency[edge.source_ref].add(edge.target_ref)
                adjacency[edge.target_ref].add(edge.source_ref)
        components: list[frozenset[str]] = []
        while remaining:
            root = min(remaining)
            component = {root}
            stack = [root]
            while stack:
                current = stack.pop()
                for neighbor in adjacency[current]:
                    if neighbor not in component:
                        component.add(neighbor)
                        stack.append(neighbor)
            remaining -= component
            components.append(frozenset(component))
        return tuple(sorted(components, key=lambda item: sorted(item)))

    def dangling_edges(
        self,
        existing_refs: Iterable[str],
    ) -> tuple[DependencyEdge, ...]:
        known = set(existing_refs)
        return tuple(
            edge
            for edge in self.edges
            if edge.source_ref not in known or edge.target_ref not in known
        )
