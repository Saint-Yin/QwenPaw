import { describe, expect, it } from 'vitest';
import { buildCreatorCommand } from '@/hooks/useCreatorCommand';
import { envelope, unit } from '@/test/creatorFixtures';

describe('semantic command builder', () => {
  it('keeps exact text payload and target CAS', () => {
    const command = buildCreatorCommand(envelope({}), 'SET_UNIT_TEXT', 'unit:u1', { field: 'storyText', value: '新文本' }, unit.targetVersion);
    expect(command.arguments).toEqual({ field: 'storyText', value: '新文本' });
    expect(command.expectedTargetVersions).toEqual([{ ref: 'unit:u1', objectVersion: 'ov-u1' }]);
    expect(command.editSessionId).toMatch(/^edit-/);
    expect(command.context).toEqual({ autosaveCommit: true });
  });

  it('carries presentation/decision/overlay CAS during Pending', () => {
    const pending = envelope({ presentationVersion: 'pv-2', reviewRevisionId: 'rr-1', approvedRevisionId: 'r1', overlayId: 'o1', overlayHead: 'oh-3', view: {}, origins: { 'unit:u1': 'review_candidate' as const }, targetVersions: { 'unit:u1': { targetVersion: 'ov-review', decisionGroupId: 'g1', decisionToken: 'dt-1' } } }, { uiPhase: 'waiting_review' });
    const command = buildCreatorCommand(pending, 'SET_UNIT_TEXT', 'unit:u1', { field: 'storyText', value: '覆盖' });
    expect(command).toMatchObject({ expectedPresentationVersion: 'pv-2', expectedDecisionToken: 'dt-1', expectedOverlayHead: 'oh-3', expectedTargetVersions: [{ ref: 'unit:u1', objectVersion: 'ov-review' }] });
  });

  it('preserves seconds and snake_case AI Edit fields', () => {
    const command = buildCreatorCommand(envelope({}), 'SET_EDIT_CLIP_OS', 'unit:u1', { clipId: 'clip-01', text: '出发', vibe: 'action' }, 'ov-u1');
    const range = buildCreatorCommand(envelope({}), 'SET_EDIT_CLIP_RANGE', 'unit:u1', { clipId: 'clip-01', start: 1.25, end: 8.75 }, 'ov-u1');
    expect(command.arguments).toEqual({ clipId: 'clip-01', text: '出发', vibe: 'action' });
    expect(command.editSessionId).toBeUndefined();
    expect(command.context).toEqual({});
    expect(range.arguments).toEqual({ clipId: 'clip-01', start: 1.25, end: 8.75 });
  });

  it.each([
    ['CREATE_SECTION', 'project:plan', { title: '第二幕', afterSectionId: 's1' }],
    ['MOVE_SECTION', 'section:s2', { beforeSectionId: 's1' }],
    ['DELETE_SECTION', 'section:s2', {}],
    ['CREATE_UNIT', 'section:s1', { title: 'Unit 2', taskType: 'edit', afterUnitId: 'u1' }],
    ['MOVE_UNIT', 'unit:u2', { toSectionId: 's2', afterUnitId: 'u4' }],
    ['DELETE_UNIT', 'unit:u2', {}],
    ['UPSERT_SHOT', 'unit:u1', { shot: { id: 'shot-1', description: '描述', camera: '推镜', duration: 3.5 } }],
    ['MOVE_SHOT', 'shot:shot-1', { afterShotId: 'shot-2' }],
    ['DELETE_SHOT', 'shot:shot-1', {}],
    ['BIND_REFERENCE', 'unit:u1', { field: 'characters', referenceSet: 'storyboard_and_video', sourceRef: 'asset://a1@av1' }],
    ['UNBIND_REFERENCE', 'unit:u1', { field: 'characters', referenceSet: 'storyboard_and_video', sourceRef: 'asset://a1@av1' }],
    ['SET_EDIT_AUDIO_PLAN', 'unit:u1', { audio_plan: { bgm: '保留' } }],
    ['ATTACH_SOURCE_ASSETS', 'project:assets', { assetVersionRefs: ['asset://a1@av1'] }],
    ['DETACH_SOURCE_ASSETS', 'project:assets', { assetVersionRefs: ['asset://a1@av1'] }],
    ['SELECT_ARTIFACT_VERSION', 'unit:u1', { slotId: 'slot-u1', artifactVersionId: 'art-v1', artifactRef: 'artifact://slot-u1@art-v1' }],
    ['SET_SECTION_COMPOSE_SELECTION', 'post:s1', { selections: [{ sourceRef: 'project://unit/u1', artifactVersionId: 'art-v1', artifactRef: 'artifact://slot-u1@art-v1', order: 0 }] }],
    ['SET_FINAL_COMPOSE_TRANSITION', 'post:final', { fromSourceRef: 'project://section/s1', toSourceRef: 'project://section/s2', type: 'fade', durationSeconds: 0.5 }],
  ] as const)('keeps the canonical %s argument envelope unchanged', (type, targetRef, args) => {
    const command = buildCreatorCommand(envelope({}), type, targetRef, args, 'ov');
    expect(command.arguments).toEqual(args);
    expect(command.targetRef).toBe(targetRef);
  });
});
