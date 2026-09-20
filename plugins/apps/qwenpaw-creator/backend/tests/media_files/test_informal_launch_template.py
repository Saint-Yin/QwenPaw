# -*- coding: utf-8 -*-
"""Official launch captions use their fixed template without an Edit clip."""

import json
from unittest.mock import AsyncMock

import pytest

from domain.errors import ValidationError
from services.media_files import motion_design
from services.media_files.informal_launch_template import (
    render_informal_launch_caption,
)
from services.media_files.local_execution import _motion_document_matches_text
from services.media_files.video_templates import (
    apply_video_template_to_project,
    get_video_template,
    list_video_templates,
)
from services.project_files.facade import CreatorFileServices
from services.project_files.models import (
    ElementLocation,
    OverlayCreation,
    Project,
    TimelineElement,
    TimelineSpan,
)


def caption(text="正式登场\nTakes the Stage", **options):
    return TimelineElement(
        element_id="caption",
        span=TimelineSpan(start_tick=0, duration_tick=3000),
        creation=OverlayCreation(
            text=text,
            prompt=json.dumps({"template": "informal_launch", **options}),
        ),
        location=ElementLocation(x=0.25, y=0.5, width=0.34, height=0.26),
    )


def test_official_template_is_available_without_user_files():
    template = get_video_template("informal_launch")
    assert template.name == "非正式发布会"
    assert list_video_templates()[0] is template
    assert get_video_template("user:cat_launch_v1") is template
    assert "一次视频模型调用" in template.design_floor.opening


@pytest.mark.asyncio
@pytest.mark.parametrize("caption_style", ["varied", "uniform"])
async def test_r2v_timeline_uses_fixed_document_without_model_or_edit(
    tmp_path,
    monkeypatch,
    caption_style,
):
    services = CreatorFileServices.create(tmp_path)
    project = apply_video_template_to_project(
        Project.new(project_id="fixed-launch", name="固定字幕测试"),
        get_video_template("informal_launch"),
    )
    project.timelines.items["timeline:main"].elements_by_id[
        "caption"
    ] = caption(recipe="hero")
    services.projects.create(project)
    model = AsyncMock(
        side_effect=AssertionError(
            "Fixed template must not call a design model",
        ),
    )
    monkeypatch.setattr(motion_design, "_design_document", model)
    monkeypatch.setattr(motion_design.vlm_model, "chat_completion", model)
    result = await motion_design.design_motion_overlays(
        services,
        project_id=project.project_id,
        target_ref="timeline:main",
        arguments={"captionStyle": caption_style},
        idempotency_key="fixed-caption",
    )
    assert result["designedCount"] == 1
    current = services.projects.read(project.project_id).project
    element = current.timelines.items["timeline:main"].elements_by_id[
        "caption"
    ]
    motion = element.creation.motion
    assert motion.format == "html_css" and motion.template_version == 4
    assert element.location.width == element.location.height == 1
    assert element.location.x == element.location.y == 0.5
    file = current.assets.files_by_id[motion.html_file_id]
    html = (
        services.projects.project_root(project.project_id) / file.relative_uri
    ).read_text()
    assert _motion_document_matches_text(html, element.creation.text)
    assert 'data-motion="slide"' in html
    assert 'class="group accent"' in html
    model.assert_not_called()
    second = await motion_design.design_motion_overlays(
        services,
        project_id=project.project_id,
        target_ref="timeline:main",
        arguments={},
        idempotency_key="preserve-caption",
    )
    assert second["designedCount"] == 0
    assert second["textOverlays"][0]["status"] == "already_styled"


def test_collection_keeps_every_translation_and_escapes_copy():
    text = (
        "四款造型\nFour Looks\n米白针织\nCream Knit\n"
        "灰蓝围巾\nBlue-Grey Scarf\n浅灰外套\nGrey <Jacket>\n"
        "深紫领结\nPurple Bow Tie"
    )
    motion, location = render_informal_launch_caption(
        caption(text, recipe="look_labels"),
        ticks_per_second=1000,
        canvas_size=(1920, 1080),
        card_index=8,
        card_count=10,
    )
    assert motion.html.count('class="group label center"') == 4
    assert "&lt;Jacket&gt;" in motion.html and "<Jacket>" not in motion.html
    assert _motion_document_matches_text(motion.html, text)
    assert location.width == 1


def test_portrait_sizes_only_a_transparent_text_band():
    motion, location = render_informal_launch_caption(
        caption(recipe="hero"),
        ticks_per_second=1000,
        canvas_size=(1080, 1920),
        card_index=0,
        card_count=10,
    )
    assert location.width == 1 and location.height <= 0.4
    assert "background:transparent" in motion.html


@pytest.mark.parametrize(
    "options",
    [{"region": [0, 0, 100, 100]}, {"accent": "red;display:none"}],
)
def test_invalid_style_slots_fail_instead_of_falling_back(options):
    with pytest.raises(ValidationError):
        render_informal_launch_caption(
            caption(**options),
            ticks_per_second=1000,
            canvas_size=(1920, 1080),
            card_index=0,
            card_count=10,
        )
