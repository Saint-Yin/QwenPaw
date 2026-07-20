# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

from services.validators.video_edit_topology import (
    normalized_video_edit_routes,
    validate_video_edit_routes,
)


def test_video_edit_topology_validation_is_disabled() -> None:
    validate_video_edit_routes(
        scenario="video_edit",
        routes=("edit",),
        durations=(60,),
        allow_generated_insert=False,
    )
    validate_video_edit_routes(
        scenario="video_edit",
        routes=("edit", "edit", "edit"),
        durations=(20, 20, 20),
        allow_generated_insert=False,
    )


def test_explicit_generated_insert_keeps_boundary_and_merges_adjacent_edits() -> (
    None
):
    assert normalized_video_edit_routes(("edit", "r2v", "edit", "edit")) == (
        "edit",
        "r2v",
        "edit",
    )
    validate_video_edit_routes(
        scenario="video_edit",
        routes=("edit", "r2v", "edit"),
        durations=(25, 10, 25),
        allow_generated_insert=True,
    )


def test_short_drama_30_seconds_remains_two_r2v_units() -> None:
    validate_video_edit_routes(
        scenario="short_drama",
        routes=("r2v", "r2v"),
        durations=(15, 15),
        allow_generated_insert=False,
    )
