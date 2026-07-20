import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import ReviewFieldText, { ReviewDiffPreview, reviewFieldForOperation, reviewFieldMatchesOperation } from '@/components/agent/ReviewFieldText';
import type { ReviewManifest, ReviewOperation } from '@/contracts/creator';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import { installMockFetch } from '@/test/mockFetch';

const field = 'story/sections/s1/units/u1/narrative.md';

function manifest(decision: 'PENDING' | 'ACCEPTED_APPLIED' = 'PENDING'): ReviewManifest {
  return {
    id: 'review-1',
    transactionId: 'tx1',
    reviewRound: 1,
    baseRevisionId: 'revision-a',
    reviewRevisionId: 'revision-b',
    manifestToken: 'manifest-token',
    summary: '',
    journalSeqRange: { fromExclusive: 0, toInclusive: 1 },
    decisionGroups: [{ id: 'g1', title: 'Unit 文案', operationIds: ['op1'], groupingReasons: [], decisionToken: 'token', decision }],
    operations: [{
      id: 'op1', decisionGroupId: 'g1', mutationIds: ['m1'], kind: 'update', targetRef: 'unit:u1', artifactKind: 'markdown', path: field,
      beforeVersionRef: 'workspace-content://before@ov1', afterVersionRef: 'workspace-content://after@ov2', causalRefs: [], source: 'user_direct', actorRunIds: ['run1'], triggerMessageSeqs: [1], dependencyReasons: [], uiLocator: { page: 'workbench', unitId: 'u1', field },
    }],
    createdArtifactVersionRefs: [],
    mediaComparisons: [],
    integrationPreviews: [],
    createdAt: 'now',
  };
}

describe('ReviewFieldText origin DOM over Review Manifest', () => {
  beforeEach(() => {
    useReviewManifestStore.getState().reset();
    useReviewManifestStore.getState().bindTransaction('p1', 'tx1');
  });

  it('keeps origin data-agent-diff DOM and loads immutable operation content', async () => {
    installMockFetch([{ match: '/review-operation-op1', response: { json: { view: { operationId: 'op1', before: '旧文案结尾', after: '新文案结尾', contentType: 'markdown' } } } }]);
    useReviewManifestStore.setState({ manifest: manifest() });
    const { container } = render(<ReviewFieldText field={field}>新文案结尾</ReviewFieldText>);
    await waitFor(() => expect(container.querySelector('[data-agent-diff]')).toBeInTheDocument());
    expect(container.querySelector('.agent-diff-del')).toHaveTextContent('旧');
    expect(container.querySelector('.agent-diff-add')).toHaveTextContent('新');
    expect(screen.getByText('文案结尾')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `接受 ${field} 修改` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `撤销 ${field} 修改` })).toBeInTheDocument();
  });

  it('keeps origin inline diff focus attributes and hides resolved groups', async () => {
    installMockFetch([{ match: '/review-operation-op1', response: { json: { view: { operationId: 'op1', before: 'A', after: 'B', contentType: 'markdown' } } } }]);
    useReviewManifestStore.setState({ manifest: manifest() });
    const { container, rerender } = render(<ReviewDiffPreview field={field} label="剧情文案" focusTarget />);
    await waitFor(() => expect(container.querySelector('[data-agent-diff-preview]')).toBeInTheDocument());
    const preview = container.querySelector('[data-agent-diff-preview]')!;
    expect(preview).toHaveAttribute('data-review-field', field);
    expect(preview).toHaveAttribute('data-review-field-label', '剧情文案');

    useReviewManifestStore.setState({ manifest: manifest('ACCEPTED_APPLIED') });
    rerender(<ReviewDiffPreview field={field} label="剧情文案" focusTarget />);
    expect(container.querySelector('[data-agent-diff-preview]')).not.toBeInTheDocument();
  });

  it('keeps origin LCS character highlighting for separated edits', async () => {
    installMockFetch([{ match: '/review-operation-op1', response: { json: { view: { operationId: 'op1', before: '甲乙丙丁', after: '甲X丙Y', contentType: 'markdown' } } } }]);
    useReviewManifestStore.setState({ manifest: manifest() });
    const { container } = render(<ReviewFieldText field={field}>甲X丙Y</ReviewFieldText>);
    await waitFor(() => expect(container.querySelector('[data-agent-diff]')).toBeInTheDocument());

    expect([...container.querySelectorAll('.agent-diff-del')].map((item) => item.textContent)).toEqual(['乙', '丁']);
    expect([...container.querySelectorAll('.agent-diff-add')].map((item) => item.textContent)).toEqual(['X', 'Y']);
  });

  it('keeps long paragraphs inline and highlights only changed tokens', async () => {
    const commonPrefix = '猫咪沿着林间小路前进，'.repeat(40);
    const commonSuffix = '随后回到营地休息。'.repeat(40);
    installMockFetch([{ match: '/review-operation-op1', response: { json: { view: {
      operationId: 'op1',
      before: `${commonPrefix}旧镜头${commonSuffix}`,
      after: `${commonPrefix}新镜头${commonSuffix}`,
      contentType: 'markdown',
    } } } }]);
    useReviewManifestStore.setState({ manifest: manifest() });
    const { container } = render(<ReviewFieldText field={field}>新文案</ReviewFieldText>);
    await waitFor(() => expect(container.querySelector('[data-agent-diff]')).toBeInTheDocument());

    expect(container.querySelector('.agent-diff-del')).toHaveTextContent('旧');
    expect(container.querySelector('.agent-diff-add')).toHaveTextContent('新');
    expect(container.querySelector('.agent-diff-del')?.textContent?.length).toBeLessThan(10);
    expect(container.querySelector('.agent-diff-add')?.textContent?.length).toBeLessThan(10);
    expect(container.textContent).toContain(commonPrefix.slice(0, 30));
    expect(container.textContent).toContain(commonSuffix.slice(-30));
  });

  it.each([
    ['section:sec-1/title', 'section:sec-1', 'story/sections/001000--sec-1--opening/title.txt'],
    ['section:sec-1/summary', 'section:sec-1', 'story/sections/001000--sec-1--opening/summary.md'],
    ['section:sec-1/pacing', 'section:sec-1', 'story/sections/001000--sec-1--opening/pacing.md'],
    ['section:sec-1/narrative', 'section:sec-1', 'story/sections/001000--sec-1--opening/narrative.md'],
    ['section:sec-1/script', 'section:sec-1', 'story/sections/001000--sec-1--opening/script.md'],
    ['section:sec-1/constraints', 'section:sec-1', 'story/sections/001000--sec-1--opening/constraints.md'],
    ['section:sec-1/transitionNote', 'section:sec-1', 'story/sections/001000--sec-1--opening/transition.md'],
    ['section:sec-1/durationBudget', 'section:sec-1', 'story/sections/001000--sec-1--opening/duration-budget.txt'],
    ['unit:unit-1/title', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/title.txt'],
    ['unit:unit-1/goal', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/production/edit/intent.md'],
    ['unit:unit-1/storyText', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/narrative.md'],
    ['unit:unit-1/duration', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/duration.txt'],
    ['unit:unit-1/storyboardPrompt', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/production/r2v/storyboard/prompt.md'],
    ['unit:unit-1/videoPrompt', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/production/r2v/video/prompt.md'],
    ['unit:unit-1/shot:shot-1/description', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/shots/001000--shot-1/description.md'],
    ['unit:unit-1/shot:shot-1/cameraDescription', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/shots/001000--shot-1/camera-source.md'],
    ['unit:unit-1/shot:shot-1/dialogue', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/shots/001000--shot-1/dialogue.md'],
    ['unit:unit-1/shot:shot-1/duration', 'unit:unit-1', 'story/sections/001000--sec-1--opening/units/001000--unit-1--intro/shots/001000--shot-1/duration.txt'],
  ])('maps origin semantic field %s to workspace path %s', (semanticField, targetRef, path) => {
    const candidate: ReviewOperation = { ...manifest().operations[0], targetRef, path, uiLocator: { page: 'plan' } };
    expect(reviewFieldMatchesOperation(semanticField, candidate)).toBe(true);
    expect(reviewFieldForOperation(candidate)).toBe(semanticField);
    expect(reviewFieldMatchesOperation(semanticField.replace(/(sec|unit|shot)-1/, '$1-other'), candidate)).toBe(false);
  });

  it('renders an inline diff when Plan uses a semantic field and the operation has only a workspace path', async () => {
    const semanticManifest = manifest();
    semanticManifest.operations[0] = {
      ...semanticManifest.operations[0],
      targetRef: 'unit:u1',
      path: 'story/sections/001000--s1--opening/units/001000--u1--intro/narrative.md',
      uiLocator: { page: 'workbench', unitId: 'u1' },
    };
    installMockFetch([{ match: '/review-operation-op1', response: { json: { view: { operationId: 'op1', before: '旧叙事', after: '新叙事', contentType: 'markdown' } } } }]);
    useReviewManifestStore.setState({ manifest: semanticManifest });
    const { container } = render(<ReviewFieldText field="unit:u1/storyText">新叙事</ReviewFieldText>);
    await waitFor(() => expect(container.querySelector('[data-agent-diff]')).toBeInTheDocument());
    expect(container.querySelector('.agent-diff-del')).toHaveTextContent('旧');
    expect(container.querySelector('.agent-diff-add')).toHaveTextContent('新');
  });
});
