from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from services.project_files import (
    AiEditPlan,
    CanonicalJsonError,
    Project,
    canonical_json_bytes,
    load_project_json,
    project_etag,
    project_file_bytes,
)


pytestmark = pytest.mark.unit


def _edit_project() -> Project:
    raw = Project.new(
        project_id="project-edit",
        name="Edit Project",
        scenario="video_edit",
        now=datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc),
    ).model_dump(mode="json")
    raw["assets"] = {
        "files_by_id": {
            "file-source": {
                "file_id": "file-source",
                "kind": "source_original",
                "relative_uri": "assets/sources/source-1/version-1/original.mp4",
                "sha256": "a" * 64,
                "size_bytes": 123,
                "media_type": "video/mp4",
                "created_at": "2026-07-15T08:00:00Z",
            }
        },
        "source_versions_by_id": {
            "source-version-1": {
                "version_id": "source-version-1",
                "logical_asset_id": "logical-source-1",
                "name": "source.mp4",
                "file_id": "file-source",
                "checksum": "a" * 64,
                "media_kind": "video",
                "media_type": "video/mp4",
                "created_at": "2026-07-15T08:00:00Z",
            }
        },
    }
    raw["sources"] = {
        "sources": {
            "items": {
                "source-1": {
                    "source_id": "source-1",
                    "display_name": "Source",
                    "logical_asset_id": "logical-source-1",
                    "selected_asset_version_id": "source-version-1",
                }
            },
            "order": ["source-1"],
        }
    }
    raw["story"] = {
        "sections": {
            "items": {
                "section-1": {
                    "section_id": "section-1",
                    "title": "Section",
                    "units": {
                        "items": {
                            "unit-1": {
                                "unit_id": "unit-1",
                                "route": "edit",
                                "duration_seconds": 3,
                                "source_refs": ["source-1"],
                            }
                        },
                        "order": ["unit-1"],
                    },
                }
            },
            "order": ["section-1"],
        }
    }
    raw["production"] = {
        "units_by_id": {
            "unit-1": {
                "route": "edit",
                "source_asset_version_ids": ["source-version-1"],
                "plan": {
                    "plan_id": "plan-1",
                    "summary": "Embedded, not a sidecar",
                    "timeline": {
                        "items": {
                            "clip-1": {
                                "clip_id": "clip-1",
                                "source_asset_version_id": "source-version-1",
                                "source_in_seconds": 0,
                                "source_out_seconds": 3,
                            }
                        },
                        "order": ["clip-1"],
                    },
                    "storyboard": {
                        "items": {
                            "panel-1": {
                                "panel_id": "panel-1",
                                "clip_id": "clip-1",
                                "source_timestamp_seconds": 1,
                            }
                        },
                        "order": ["panel-1"],
                    },
                },
            }
        }
    }
    return Project.model_validate(raw)


def test_project_new_has_complete_valid_defaults_and_utc_time():
    project = Project.new(
        project_id="project-001",
        name="Project",
        now=datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc),
    )

    assert project.schema_version == 1
    assert project.generation == 0
    assert project.created_at.tzinfo == timezone.utc
    assert project.story.sections.items == {}
    assert project.assets.files_by_id == {}


def test_ai_edit_plan_is_embedded_and_hashes_its_canonical_content():
    project = _edit_project()
    production = project.production.units_by_id["unit-1"]

    assert production.route == "edit"
    assert production.plan is not None
    assert production.plan.plan_hash == production.plan.content_hash()
    assert production.plan.summary == "Embedded, not a sidecar"
    assert "ai_edit_plan" not in project.assets.files_by_id

    with pytest.raises(ValidationError, match="plan_hash"):
        AiEditPlan(plan_id="plan-bad", plan_hash="0" * 64)


def test_canonical_serialization_is_stable_human_readable_and_round_trips():
    project = _edit_project()
    first = project_file_bytes(project)
    second = project_file_bytes(Project.model_validate(project.model_dump(mode="json")))

    assert first == second
    assert first.endswith(b"\n")
    assert not first.startswith(b"\xef\xbb\xbf")
    assert first.index(b'"schema_version"') < first.index(b'"project_id"')
    assert load_project_json(first) == project
    assert project_etag(load_project_json(first)) == project_etag(project)


def test_dynamic_map_keys_are_sorted_but_business_order_is_preserved():
    value = {"z": 1, "a": 2, "order": ["z", "a"]}
    assert canonical_json_bytes(value) == b'{"a":2,"order":["z","a"],"z":1}'


def test_parser_rejects_duplicate_keys_non_object_root_and_non_finite_numbers():
    with pytest.raises(CanonicalJsonError, match="duplicate"):
        load_project_json('{"schema_version":1,"schema_version":1}')
    with pytest.raises(CanonicalJsonError, match="root"):
        load_project_json("[]")
    with pytest.raises(CanonicalJsonError, match="invalid JSON number"):
        load_project_json('{"value": NaN}')


@pytest.mark.parametrize(
    "relative_uri",
    ["assets", "../outside.bin", "/assets/file.bin", r"assets\\file.bin"],
)
def test_indexed_file_uri_must_name_a_file_below_assets(relative_uri):
    raw = _edit_project().model_dump(mode="json")
    raw["assets"]["files_by_id"]["file-source"]["relative_uri"] = relative_uri

    with pytest.raises(ValidationError, match="relative_uri"):
        Project.model_validate(raw)


def test_graph_rejects_production_for_missing_story_unit():
    raw = Project.new(project_id="project-bad", name="Bad").model_dump(mode="json")
    raw["production"] = {"units_by_id": {"missing": {"route": "edit"}}}

    with pytest.raises(ValidationError, match="production unit references missing"):
        Project.model_validate(raw)


def test_project_json_is_plain_json_with_no_runtime_state():
    payload = json.loads(project_file_bytes(_edit_project()))

    assert "runtime" not in payload
    assert "reviews" not in payload
    assert payload["production"]["units_by_id"]["unit-1"]["plan"]["plan_id"] == "plan-1"
