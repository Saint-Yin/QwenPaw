"""Prompt-content validation coverage for R2V execution."""

from __future__ import annotations

import pytest

from services.validators.r2v import PromptEvaluation, evaluate_video_prompt


pytestmark = pytest.mark.unit

_REQUIRED_FINAL_CONSTRAINT = (
    "保持无字幕，避免生成任何文字或字幕，不要生成Logo，不要生成水印，"
    "人物面部和身体比例稳定不变形，动作自然流畅，无卡顿无闪烁。"
)


def test_video_prompt_evaluator_accepts_complete_seedance_prompt() -> None:
    context = {
        "reference_bindings": [{"ref": "图1", "name": "阿圆"}],
        "characters": [{"name": "阿圆"}],
        "shots": [{"dialogue": "出发吧"}, {"dialogue": ""}],
    }
    prompt = (
        "将图1中的短发、蓝色外套、圆框眼镜定义为阿圆。"
        "镜头1采用中景固定机位，阿圆先轻轻抬手，手指慢慢收紧，眼神紧张地看向门外，"
        "随后迅速转身并向前迈出两步，衣摆随动作自然摆动；阿圆低声说{出发吧}。"
        "镜头2切到特写并缓慢推近，阿圆停住脚步，深吸一口气，眉头逐渐舒展，"
        "最后坚定点头，背景灯光从冷蓝色过渡到温暖橙色。"
        "<保留自然环境声和细微动作声>。"
        "整体画面保持高清电影质感，动作自然流畅、人物结构稳定。"
        + _REQUIRED_FINAL_CONSTRAINT
    )

    assert evaluate_video_prompt(prompt, context) == PromptEvaluation(
        passed=True,
        score=13,
        max_score=13,
        failures=[],
        warnings=[],
    )


def test_video_prompt_evaluator_rejects_neighbor_context_exact_time_and_missing_rules() -> (
    None
):
    context = {
        "reference_bindings": [{"ref": "图1", "name": "阿圆"}],
        "characters": [{"name": "阿圆"}],
        "shots": [{"dialogue": "出发吧"}],
    }
    evaluation = evaluate_video_prompt(
        "上一Clip结束后，0-3秒阿圆出现，下一Clip继续。",
        context,
    )

    assert evaluation.passed is False
    assert evaluation.score < 11
    assert "prompt过短，缺少足够的导演描述和生成约束。" in evaluation.failures
    assert "包含相邻Clip或续写语义：上一Clip, 下一Clip。" in evaluation.failures
    assert (
        "使用了精确秒段，Seedance建议使用镜头顺序而非强行限制0-3秒。"
        in evaluation.failures
    )
    assert "台词未按Seedance建议使用中文花括号{}标注。" in evaluation.failures
    assert (
        "缺少稳定性约束：保持无字幕, 避免生成任何文字或字幕, "
        "不要生成Logo, 不要生成水印。"
    ) in evaluation.failures
