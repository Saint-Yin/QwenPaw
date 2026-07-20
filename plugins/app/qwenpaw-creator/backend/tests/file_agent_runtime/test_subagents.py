from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.file_agent_runtime.subagents import (
    DelegateToAgentInput,
    delegate_tool_manifest,
)


pytestmark = pytest.mark.unit


def test_delegate_input_rejects_duplicate_target_refs() -> None:
    with pytest.raises(ValidationError, match="target_refs must contain unique values"):
        DelegateToAgentInput.model_validate(
            {
                "role": "visual_development_agent",
                "target_refs": ["project:assets", "project:assets"],
                "task": "建立视觉结构",
            }
        )


def test_story_and_unit_planning_are_not_delegatable() -> None:
    roles = delegate_tool_manifest()["function"]["parameters"]["properties"]["role"][
        "enum"
    ]
    assert roles == [
        "source_intelligence_agent",
        "visual_development_agent",
        "r2v_generation_director",
        "ai_editing_director",
    ]

    for role, target_ref in (
        ("story_planning_agent", "project:plan"),
        ("unit_planning_routing_agent", "section:section-1"),
    ):
        delegated = DelegateToAgentInput.model_validate(
            {
                "role": role,
                "target_refs": [target_ref],
                "task": "这个职责现在属于 Creator 主 Agent",
            }
        )
        with pytest.raises(ValueError, match="is not delegatable"):
            delegated.validate_contract(project_id="project-1")
