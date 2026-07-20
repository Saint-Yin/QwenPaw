# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import pytest

from services.project_files.migrations import PROJECT_MIGRATIONS
from services.project_files.models import Project
from services.project_files.serialization import (
    CanonicalJsonError,
    load_project_json,
)


def _raw_project() -> dict:
    return Project.new(project_id="project-1", name="Project").model_dump(
        mode="json",
    )


def test_registered_migration_runs_before_strict_project_validation() -> None:
    raw = _raw_project()
    raw["schema_version"] = 0
    raw["legacy_name"] = raw.pop("name")

    def migrate_v0(document: dict) -> dict:
        document["schema_version"] = 1
        document["name"] = document.pop("legacy_name")
        return document

    PROJECT_MIGRATIONS[0] = migrate_v0
    try:
        project = load_project_json(json.dumps(raw))
    finally:
        PROJECT_MIGRATIONS.pop(0, None)

    assert project.schema_version == 1
    assert project.name == "Project"


def test_unregistered_or_future_schema_fails_closed() -> None:
    raw = _raw_project()
    raw["schema_version"] = 0
    with pytest.raises(CanonicalJsonError):
        load_project_json(json.dumps(raw))

    raw["schema_version"] = 2
    with pytest.raises(CanonicalJsonError):
        load_project_json(json.dumps(raw))


def test_migration_cannot_change_project_identity() -> None:
    raw = _raw_project()
    raw["schema_version"] = 0

    def invalid(document: dict) -> dict:
        document["schema_version"] = 1
        document["project_id"] = "different"
        return document

    PROJECT_MIGRATIONS[0] = invalid
    try:
        with pytest.raises(CanonicalJsonError):
            load_project_json(json.dumps(raw))
    finally:
        PROJECT_MIGRATIONS.pop(0, None)
