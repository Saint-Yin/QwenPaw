# -*- coding: utf-8 -*-
"""Fixed caption slot filling owned by the informal-launch video template."""

from __future__ import annotations

from functools import lru_cache
from html import escape
import json
import math
from pathlib import Path
import re

from domain.errors import ValidationError
from services.project_files.models import (
    ElementLocation,
    MotionGraphic,
    OverlayCreation,
    Timeline,
    TimelineElement,
)

TEMPLATE_MARKER = "【官方固定模板：informal_launch】"


def uses_informal_launch_captions(timeline: Timeline) -> bool:
    return bool(
        timeline.edit_plan
        and TEMPLATE_MARKER in timeline.edit_plan.design_floor.opening,
    )


@lru_cache(maxsize=1)
def _styles() -> dict:
    path = (
        Path(__file__).resolve().parents[3]
        / "templates/cat-launch/caption-styles.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _pairs(text: str) -> list[tuple[str, str]]:
    """Keep authored words and line breaks; never invent a translation."""
    result: list[tuple[str, str]] = []
    chinese: list[str] = []
    english: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.search(r"[\u3400-\u9fff]", line):
            if english:
                result.append(("\n".join(chinese), "\n".join(english)))
                chinese, english = [], []
            chinese.append(line)
        elif chinese:
            english.append(line)
        else:
            raise ValidationError(
                "非正式发布会字幕须按中文、对应英文的顺序填写",
            )
    if not chinese or not english:
        raise ValidationError("非正式发布会字幕缺少中文或对应英文")
    result.append(("\n".join(chinese), "\n".join(english)))
    return result


def _region(value: object, default: list[float]) -> list[float]:
    if value is None:
        return default
    if not isinstance(value, list) or len(value) != 4:
        raise ValidationError("模板 region 须为 [左, 上, 宽, 高] 百分比")
    try:
        box = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise ValidationError("模板 region 必须是有限数字") from exc
    x, y, width, height = box
    if not all(math.isfinite(v) for v in box) or not (
        x >= 6
        and y >= 6
        and width > 0
        and height > 0
        and x + width <= 94
        and y + height <= 94
    ):
        raise ValidationError("模板文字区须保留6%画布安全边距")
    return box


def render_informal_launch_caption(
    overlay: TimelineElement,
    *,
    ticks_per_second: int,
    canvas_size: tuple[int, int],
    card_index: int,
    card_count: int,
) -> tuple[MotionGraphic, ElementLocation]:
    creation = overlay.creation
    assert isinstance(creation, OverlayCreation)
    pairs = _pairs(creation.text)
    try:
        options = json.loads(creation.prompt or "{}")
    except ValueError:
        options = {}
    if (
        not isinstance(options, dict)
        or options.get("template") != "informal_launch"
    ):
        options = {}
    recipe = options.get("recipe") or (
        "look_labels"
        if len(pairs) >= 3
        else (
            "hero"
            if card_index == 0
            else "closing"
            if card_index == card_count - 1
            else "detail"
        )
    )
    recipes = {item["name"]: item for item in _styles()["recipes"]}
    if not isinstance(recipe, str) or recipe not in recipes:
        raise ValidationError(f"未知的非正式发布会字幕样式: {recipe}")
    portrait = canvas_size[0] < canvas_size[1]
    location = ElementLocation(x=0.5, y=0.5, width=1, height=1)
    reference_width, reference_height = 1280, 720
    if portrait:
        # Size only the transparent text band; keep the video full frame.
        top = bool(overlay.location and overlay.location.y < 0.5)
        location = ElementLocation(
            x=0.5,
            y=0.25 if top else 0.75,
            width=1,
            height=0.36,
        )
        reference_width, reference_height = 720, 1280 * 0.36

    def fill(key: str, **values: object) -> str:
        document = _styles()[key]
        for name, value in values.items():
            document = document.replace("{{" + name + "}}", str(value))
        if "{{" in document:
            raise ValidationError(f"非正式发布会字幕模板槽位未填全: {key}")
        return document

    def color(key: str, default: str) -> str:
        value = str(options.get(key, default))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValidationError("模板强调色须为六位十六进制颜色")
        return value

    def group(
        pair: tuple[str, str],
        *,
        kind: str = "",
        motion: str = "fade",
        zh: int = 42,
        en: int = 23,
        delay: float = 0,
        center: bool = False,
    ) -> str:
        return fill(
            "group_template",
            CLASS=kind,
            MOTION=motion,
            DELAY=delay,
            ZH_SIZE=zh,
            EN_SIZE=en,
            ALIGN="center" if center else "left",
            INK="#20242c",
            MUTED="#454c58",
            SHADOW="none",
            COLOR=color("accent", "#6142bd"),
            COLOR_END=color("accent_end", "#277f83"),
            RULE="",
            ZH=escape(pair[0]).replace("\n", "<br>"),
            EN=escape(pair[1]).replace("\n", "<br>"),
        )

    def region(
        area: list[float],
        items: list[str],
        layout: str = "",
        count: int = 1,
    ) -> str:
        return fill(
            "region_template",
            LEFT=area[0],
            TOP=area[1],
            WIDTH=area[2],
            HEIGHT=area[3],
            ITEMS="".join(items),
            LAYOUT=layout,
            COUNT=count,
        )

    if recipe == "look_labels":
        if not 2 <= len(pairs) <= 6:
            raise ValidationError("造型字幕需要总标题及1–5款完整双语标签")
        header = _region(
            options.get("header_region"),
            [6, 8, 88, 22] if portrait else [6, 6.5, 88, 11],
        )
        labels = _region(
            options.get("label_region"),
            [6, 38, 88, 55] if portrait else [9, 83, 82, 10.5],
        )
        content = region(
            header,
            [group(pairs[0], kind="center", zh=28, en=17, center=True)],
            "top",
        )
        content += region(
            labels,
            [
                group(
                    pair,
                    kind="label center",
                    zh=22,
                    en=17,
                    delay=round(0.16 + 0.08 * index, 2),
                    center=True,
                )
                for index, pair in enumerate(pairs[1:])
            ],
            "row",
            min(2, len(pairs) - 1) if portrait else len(pairs) - 1,
        )
    else:
        if len(pairs) > 2:
            raise ValidationError(
                "普通字幕每个文字区最多两组双语；造型列表请用 look_labels",
            )
        layout = options.get("layout") or (
            "text_right"
            if overlay.location and overlay.location.x > 0.5
            else "text_left"
        )
        layouts = _styles()["overlay_layouts"]
        if layout not in ("text_left", "text_right", "top_left", "top_right"):
            raise ValidationError(f"未知的非正式发布会文字区域: {layout}")
        preset = layouts[layout]["text_region_percent"]
        default = (
            [6, 10, 88, 80]
            if portrait
            else [preset[key] for key in ("LEFT", "TOP", "WIDTH", "HEIGHT")]
        )
        area = _region(options.get("region"), default)
        top = layout.startswith("top_")
        main_size = (
            38
            if portrait or top
            else 50
            if recipe in ("hero", "closing")
            else 42
        )
        content = region(
            area,
            [
                group(
                    pair,
                    kind="small" if index else recipes[recipe]["class"],
                    motion="fade" if index else recipes[recipe]["motion"],
                    zh=30 if index else main_size,
                    en=21 if index else 22 if top else 24,
                    delay=0.18 if index else 0,
                )
                for index, pair in enumerate(pairs)
            ],
            "top" if top else "",
        )
    document = fill(
        "document_template",
        WIDTH=reference_width,
        HEIGHT=reference_height,
        DURATION=overlay.span.duration_tick / ticks_per_second,
        GROUPS=content,
    )
    return (
        MotionGraphic(
            format="html_css",
            html=document,
            template_version=4,
            fps=30,
            loop=False,
            motif="custom",
            design_notes=f"非正式发布会官方固定字幕 · {recipe}",
        ),
        location,
    )
