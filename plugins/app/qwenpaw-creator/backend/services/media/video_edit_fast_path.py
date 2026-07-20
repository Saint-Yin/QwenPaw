"""Deterministic single-source topology for the default video-edit flow."""

from __future__ import annotations

from collections.abc import Mapping


VIDEO_EDIT_FAST_PATH_SECTION_ID = "video-edit-main"
VIDEO_EDIT_FAST_PATH_UNIT_ID = "video-edit-main"
VIDEO_EDIT_FAST_PATH_SECTION_ROOT = (
    "story/sections/001000--video-edit-main--AI剪辑"
)
VIDEO_EDIT_FAST_PATH_UNIT_ROOT = (
    f"{VIDEO_EDIT_FAST_PATH_SECTION_ROOT}/units/"
    "001000--video-edit-main--主素材剪辑"
)


def _seconds_text(value: float) -> str:
    return f"{value:g}"


def video_edit_fast_path_values(
    *,
    summary: str,
    source_ref: str,
    analysis_ref: str,
    target_duration: float,
) -> dict[str, str]:
    """Return the complete model-free Section/Unit projection.

    The topology is intentionally stable. Source Intelligence owns the evidence;
    Runtime only projects that evidence and the Creator-owned target duration into
    the minimal structures required by the AI Edit service.
    """

    duration = _seconds_text(target_duration)
    concise_summary = summary.strip()
    section = VIDEO_EDIT_FAST_PATH_SECTION_ROOT
    unit = VIDEO_EDIT_FAST_PATH_UNIT_ROOT
    return {
        f"{section}/title.txt": "AI 剪辑",
        f"{section}/summary.md": concise_summary,
        f"{section}/narrative.md": concise_summary,
        f"{section}/duration-budget.txt": duration,
        f"{section}/pacing.md": "根据 Source Intelligence 的语义时间片段选择并重排高价值画面。",
        f"{section}/transition.md": "默认使用直接切换；仅在语义衔接需要时使用短转场。",
        f"{section}/constraints.md": (
            "- 只使用 Source Intelligence 中可追溯的真实素材时间片段\n"
            "- 不创建 R2V 片段，除非用户明确要求生成插入\n"
        ),
        f"{section}/source-analysis.ref": analysis_ref,
        f"{unit}/title.txt": "主素材剪辑",
        f"{unit}/route.txt": "edit",
        f"{unit}/duration.txt": duration,
        f"{unit}/narrative.md": concise_summary,
        f"{unit}/continuity.md": "按语义事件和动作连续性组织片段，避免重复理解整段源视频。",
        f"{unit}/refs/sources/main.ref": source_ref,
        f"{unit}/refs/source-analysis.ref": analysis_ref,
    }


VIDEO_EDIT_FAST_PATH_PATHS = frozenset(
    video_edit_fast_path_values(
        summary="placeholder",
        source_ref="asset://placeholder@placeholder",
        analysis_ref="analysis://placeholder@placeholder",
        target_duration=1,
    )
)


def fast_path_can_replace_workspace(paths: Mapping[str, object] | set[str]) -> bool:
    """Allow creation or refresh of only the canonical fast-path subtree."""

    path_set = set(paths)
    story_paths = {path for path in path_set if path.startswith("story/sections/")}
    return not story_paths or all(
        path.startswith(f"{VIDEO_EDIT_FAST_PATH_SECTION_ROOT}/")
        for path in story_paths
    )


def has_single_selected_source(paths: Mapping[str, object] | set[str]) -> bool:
    """Keep the deterministic topology restricted to the one-source product path."""

    return (
        len(
            {
                path
                for path in paths
                if path.startswith("sources/")
                and path.endswith("/selected-version.ref")
            }
        )
        == 1
    )


__all__ = [
    "VIDEO_EDIT_FAST_PATH_PATHS",
    "VIDEO_EDIT_FAST_PATH_SECTION_ID",
    "VIDEO_EDIT_FAST_PATH_SECTION_ROOT",
    "VIDEO_EDIT_FAST_PATH_UNIT_ID",
    "VIDEO_EDIT_FAST_PATH_UNIT_ROOT",
    "fast_path_can_replace_workspace",
    "has_single_selected_source",
    "video_edit_fast_path_values",
]
