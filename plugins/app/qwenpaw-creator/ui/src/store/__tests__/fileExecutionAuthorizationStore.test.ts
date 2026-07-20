import { beforeEach, describe, expect, it } from 'vitest';
import { installMockFetch } from '@/test/mockFetch';
import { useReviewManifestStore } from '@/store/reviewManifestStore';

const pending = {
  id: 'authorization-1',
  transactionId: 'round-1',
  specialistRunId: 'run-1',
  executionRequestId: 'request-1',
  targetRef: 'asset:hero',
  scope: { operation: 'image_generation' },
  status: 'PENDING' as const,
  authorizationToken: 'token-1',
  provider: 'creator-image',
  model: 'configured-image-model',
  estimatedCost: 0,
  maxCandidates: 1,
  createdAt: 'now',
};

describe('file execution authorization polling', () => {
  beforeEach(() => useReviewManifestStore.getState().reset());

  it('uses project-level file routes without a SQL transaction', async () => {
    const { calls } = installMockFetch([
      {
        match: '/projects/p1/execution-authorizations?status=PENDING',
        response: { json: { items: [pending] } },
      },
      {
        match: '/projects/p1/execution-authorizations/authorization-1/approve',
        response: { json: { ...pending, status: 'APPROVED' } },
      },
    ]);

    await useReviewManifestStore.getState().loadFileAuthorizations('p1');
    await useReviewManifestStore.getState().approveAuthorization('authorization-1', {
      authorizationToken: 'token-1',
      provider: 'creator-image',
      model: 'configured-image-model',
      maxCost: 0,
      maxCandidates: 1,
    });

    expect(useReviewManifestStore.getState().authorizations[0].status).toBe('APPROVED');
    expect(calls.some((call) => call.url.includes('/transactions/'))).toBe(false);
    expect(calls.at(-1)?.body).toEqual({
      authorizationToken: 'token-1',
      provider: 'creator-image',
      model: 'configured-image-model',
      maxCost: 0,
      maxCandidates: 1,
    });
  });
});
