from __future__ import annotations

import asyncio

from services.creator.message_classification import (
    ModelBackedMessageIntentClassifier,
)
from services.creator.model_adapter import CreatorModelTurn


class StaticClassificationModel:
    model_name = "test-classifier"

    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls = 0

    async def complete(self, **_kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.text is not None
        return CreatorModelTurn(text=self.text)


def _classify(model: StaticClassificationModel, *, parts=None):
    return asyncio.run(
        ModelBackedMessageIntentClassifier(model).classify_waiting_input(
            text=(
                "继续当前目标，不修改任何已有创作要求或当前产物；"
                "只重新执行一致性质检并完成审阅。"
            ),
            content_parts=parts or [{"type": "text", "text": "control"}],
            ui_context={"panel": "plan", "selected": {"ref": "section:chase"}},
        )
    )


def test_explicit_no_op_continuation_requires_all_four_semantic_evidence_flags():
    model = StaticClassificationModel(
        """{"classification":"no_op_continuation","resumeRequested":true,
        "preserveRequirementsExplicit":true,"preserveArtifactsExplicit":true,
        "introducesNewDirective":false}"""
    )

    decision = _classify(model)

    assert decision.classification == "read_only_question"
    assert decision.is_no_op_continuation is True
    assert decision.reason_code == "explicit_no_op_continuation"
    assert decision.model_name == "test-classifier"


def test_ambiguous_or_inconsistent_no_op_evidence_fails_closed_to_mutation():
    model = StaticClassificationModel(
        """{"classification":"no_op_continuation","resumeRequested":true,
        "preserveRequirementsExplicit":true,"preserveArtifactsExplicit":false,
        "introducesNewDirective":false}"""
    )

    decision = _classify(model)

    assert decision.classification == "mutation_instruction"
    assert decision.control_intent is None
    assert decision.reason_code == "incomplete_no_op_evidence"


def test_classifier_protocol_or_provider_failure_fails_closed_to_mutation():
    malformed = _classify(StaticClassificationModel("not-json"))
    unavailable = _classify(
        StaticClassificationModel(error=RuntimeError("provider unavailable"))
    )

    assert malformed.classification == "mutation_instruction"
    assert malformed.reason_code == "classifier_unavailable"
    assert unavailable.classification == "mutation_instruction"
    assert unavailable.reason_code == "classifier_unavailable"


def test_non_text_content_never_calls_model_or_receives_no_op_semantics():
    model = StaticClassificationModel(
        """{"classification":"no_op_continuation","resumeRequested":true,
        "preserveRequirementsExplicit":true,"preserveArtifactsExplicit":true,
        "introducesNewDirective":false}"""
    )

    decision = _classify(
        model,
        parts=[
            {"type": "text", "text": "continue"},
            {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
        ],
    )

    assert decision.classification == "mutation_instruction"
    assert decision.reason_code == "non_text_content_requires_mutation"
    assert model.calls == 0
