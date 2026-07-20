from __future__ import annotations

import pytest

from domain.enums import DETERMINISTIC_COMMANDS, CreatorCommandType, UiPhase
from domain.errors import PhaseConflictError, ValidationError
from schemas.commands import CreatorCommandRequest
from services.format_layer.command_translator import translate_command


def _command(kind: CreatorCommandType, **overrides) -> CreatorCommandRequest:
    payload = {
        "clientCommandId": f"command-{kind.value}",
        "editSessionId": "edit-1",
        "type": kind.value,
        "targetRef": "unit:u1",
        "arguments": {},
        "expectedTargetVersions": [{"ref": "unit:u1", "objectVersion": "v1"}],
    }
    payload.update(overrides)
    return CreatorCommandRequest.model_validate(payload)


def test_all_42_commands_have_exactly_one_lane() -> None:
    assert len(CreatorCommandType) == 42
    coalesced = {
        CreatorCommandType.SET_STRATEGY_TEXT,
        CreatorCommandType.SET_SECTION_TEXT,
        CreatorCommandType.SET_UNIT_TEXT,
        CreatorCommandType.SET_EDIT_AUDIO_PLAN,
    }
    for kind in CreatorCommandType:
        command = _command(kind)
        if kind == CreatorCommandType.CHANGE_UNIT_ROUTE:
            command = _command(kind, arguments={"taskType": "r2v"})
        elif kind in {CreatorCommandType.ATTACH_SOURCE_ASSETS, CreatorCommandType.DETACH_SOURCE_ASSETS}:
            command = _command(kind, arguments={"assetVersionRefs": ["asset://source@v1"]})
        elif kind == CreatorCommandType.SUPPLEMENT_ASSET:
            command = _command(
                kind,
                targetRef="asset:visual-1",
                arguments={"field": "name", "value": "视觉资产"},
            )
        disposition = translate_command(command, ui_phase=UiPhase.IDLE)
        assert (disposition.lane == "deterministic_mutation") is (kind in DETERMINISTIC_COMMANDS)
        assert disposition.requires_manual_edit_outbox is (kind in DETERMINISTIC_COMMANDS)
        assert (disposition.coalesce_key is not None) is (kind in coalesced)

    audio = translate_command(
        _command(CreatorCommandType.SET_EDIT_AUDIO_PLAN), ui_phase=UiPhase.IDLE
    )
    assert audio.coalesce_key == '["edit-1","unit:u1","audio_plan"]'


def test_pending_generation_is_durable_deferred_not_executed() -> None:
    disposition = translate_command(_command(CreatorCommandType.GENERATE_R2V_VIDEO), ui_phase=UiPhase.WAITING_REVIEW)
    assert disposition.lane == "creator_action"
    assert disposition.phase_state == "DEFERRED_UNTIL_REVIEW_RESOLVED"
    assert not disposition.requires_manual_edit_outbox


def test_pending_manual_edit_requires_presentation_or_overlay_cas() -> None:
    command = _command(CreatorCommandType.SET_UNIT_TEXT)
    with pytest.raises(ValidationError, match="presentationVersion"):
        translate_command(command, ui_phase=UiPhase.WAITING_REVIEW)
    accepted = command.model_copy(update={"expected_presentation_version": "presentation-1"})
    disposition = translate_command(accepted, ui_phase=UiPhase.WAITING_REVIEW)
    assert disposition.phase_state == "APPLY"
    assert disposition.coalesce_key == '["edit-1","unit:u1","value"]'


def test_attach_uses_exact_immutable_asset_versions_and_route_has_no_alias() -> None:
    with pytest.raises(ValidationError):
        translate_command(
            _command(CreatorCommandType.ATTACH_SOURCE_ASSETS, arguments={"assetVersionRefs": ["asset:a1"]}),
            ui_phase=UiPhase.IDLE,
        )


def test_asset_create_delete_use_the_fixed_deterministic_supplement_lane() -> None:
    create = translate_command(
        _command(
            CreatorCommandType.SUPPLEMENT_ASSET,
            targetRef="project:assets",
            arguments={"operation": "create", "assetKind": "character", "name": "新角色"},
        ),
        ui_phase=UiPhase.IDLE,
    )
    assert create.lane == "deterministic_mutation"
    assert create.requires_manual_edit_outbox is True
    assert create.description == "新建角色资产「新角色」"

    delete = translate_command(
        _command(
            CreatorCommandType.SUPPLEMENT_ASSET,
            targetRef="asset:character-1",
            arguments={"operation": "delete"},
        ),
        ui_phase=UiPhase.IDLE,
    )
    assert delete.lane == "deterministic_mutation"
    assert delete.requires_manual_edit_outbox is True
    assert delete.description == "删除指定视觉资产并闭合所有引用"

    with pytest.raises(ValidationError, match="assetKind"):
        translate_command(
            _command(
                CreatorCommandType.SUPPLEMENT_ASSET,
                targetRef="project:assets",
                arguments={"operation": "create", "assetKind": "unknown", "name": "x"},
            ),
            ui_phase=UiPhase.IDLE,
        )
    with pytest.raises(ValidationError, match="Asset ingest"):
        translate_command(
            _command(
                CreatorCommandType.SUPPLEMENT_ASSET,
                targetRef="project:assets",
                arguments={"operation": "create", "assetKind": "material", "name": "素材"},
            ),
            ui_phase=UiPhase.IDLE,
        )
    with pytest.raises(ValidationError):
        translate_command(
            _command(CreatorCommandType.CHANGE_UNIT_ROUTE, arguments={"taskType": "i" + "2v"}),
            ui_phase=UiPhase.IDLE,
        )


def test_finalizing_queues_while_stopped_phases_reject_new_commands() -> None:
    assert translate_command(
        _command(CreatorCommandType.GENERATE_SCRIPT), ui_phase=UiPhase.FINALIZING
    ).phase_state == "QUEUE_FOR_BOUNDARY"
    for phase in (UiPhase.INTERRUPTING, UiPhase.CANCELLED, UiPhase.ERROR):
        with pytest.raises(PhaseConflictError):
            translate_command(_command(CreatorCommandType.GENERATE_SCRIPT), ui_phase=phase)
