import { create } from 'zustand';
import type {
  ExecutionAuthorizationApproval,
  ExecutionAuthorizationView,
  ReviewDecisionRequest,
  ReviewManifest,
  ReviewOperationContent,
} from '@/contracts/creator';
import {
  approveExecutionAuthorization,
  approveFileExecutionAuthorization,
  commentOnReviewGroup,
  decideReviewGroup,
  declineExecutionAuthorization,
  declineFileExecutionAuthorization,
  getReviewManifest,
  getReviewOperationContent,
  listExecutionAuthorizations,
  listFileExecutionAuthorizations,
  newClientId,
} from '@/api/creator';

const commentRetryIds = new Map<string, string>();
const actionRetryIds = new Map<string, string>();

interface ReviewManifestState {
  projectId: string | null;
  transactionId: string | null;
  manifest: ReviewManifest | null;
  authorizations: ExecutionAuthorizationView[];
  operationContents: Record<string, ReviewOperationContent>;
  operationContentLoading: Record<string, boolean>;
  operationContentErrors: Record<string, string>;
  loading: boolean;
  error: string | null;
  bindTransaction: (projectId: string, transactionId: string) => void;
  bindFileProject: (projectId: string) => void;
  load: (projectId: string, transactionId: string) => Promise<void>;
  decide: (groupId: string, request: ReviewDecisionRequest) => Promise<void>;
  comment: (groupId: string, text: string, selection?: { field: string; text: string }) => Promise<void>;
  loadAuthorizations: () => Promise<void>;
  loadFileAuthorizations: (projectId: string) => Promise<void>;
  loadOperationContent: (operationId: string) => Promise<void>;
  approveAuthorization: (authorizationId: string, request: ExecutionAuthorizationApproval) => Promise<void>;
  declineAuthorization: (authorizationId: string, authorizationToken: string) => Promise<void>;
  reset: () => void;
}

interface ReviewRequestToken {
  epoch: number;
  requestId: number;
  resource: string;
  projectId: string;
  transactionId: string | null;
}

export const useReviewManifestStore = create<ReviewManifestState>((set, get) => {
  let requestEpoch = 0;
  let nextRequestId = 0;
  const latestRequestByResource = new Map<string, number>();

  const invalidateRequests = () => {
    requestEpoch += 1;
    latestRequestByResource.clear();
  };

  const beginRequest = (
    resource: string,
    projectId: string,
    transactionId: string | null,
  ): ReviewRequestToken => {
    const requestId = ++nextRequestId;
    latestRequestByResource.set(resource, requestId);
    return { epoch: requestEpoch, requestId, resource, projectId, transactionId };
  };

  const isCurrent = (token: ReviewRequestToken, state = get()) => (
    token.epoch === requestEpoch
    && latestRequestByResource.get(token.resource) === token.requestId
    && state.projectId === token.projectId
    && state.transactionId === token.transactionId
  );

  const fenceMutation = (
    resource: string,
    projectId: string,
    transactionId: string | null,
  ) => beginRequest(resource, projectId, transactionId);

  const bindScope = (projectId: string, transactionId: string) => {
    const state = get();
    if (state.projectId === projectId && state.transactionId === transactionId) return;
    invalidateRequests();
    set({
      projectId,
      transactionId,
      manifest: null,
      authorizations: [],
      operationContents: {},
      operationContentLoading: {},
      operationContentErrors: {},
      loading: false,
      error: null,
    });
  };

  const bindFileScope = (projectId: string) => {
    const state = get();
    if (state.projectId === projectId && state.transactionId === null) return;
    invalidateRequests();
    set({
      projectId,
      transactionId: null,
      manifest: null,
      authorizations: [],
      operationContents: {},
      operationContentLoading: {},
      operationContentErrors: {},
      loading: false,
      error: null,
    });
  };

  return {
  projectId: null,
  transactionId: null,
  manifest: null,
  authorizations: [],
  operationContents: {},
  operationContentLoading: {},
  operationContentErrors: {},
  loading: false,
  error: null,
  bindTransaction: bindScope,
  bindFileProject: bindFileScope,
  load: async (projectId, transactionId) => {
    bindScope(projectId, transactionId);
    const manifestRequest = beginRequest('manifest', projectId, transactionId);
    const authorizationRequest = beginRequest('authorizations', projectId, transactionId);
    set({ loading: true, error: null });
    try {
      const [manifest, auth] = await Promise.all([
        getReviewManifest(projectId, transactionId),
        listExecutionAuthorizations(projectId, transactionId),
      ]);
      set((state) => ({
        ...(isCurrent(manifestRequest, state) ? { manifest, loading: false } : {}),
        ...(isCurrent(authorizationRequest, state) ? { authorizations: auth.items } : {}),
      }));
    } catch (error) {
      if (isCurrent(manifestRequest)) {
        set({ loading: false, error: (error as Error).message });
      }
      throw error;
    }
  },
  decide: async (groupId, request) => {
    const { projectId, transactionId } = get();
    if (!projectId || !transactionId) throw new Error('当前没有可审阅的 Transaction');
    const signature = JSON.stringify({ projectId, transactionId, groupId, request });
    const clientRequestId = actionRetryIds.get(signature) ?? newClientId('review-decision');
    actionRetryIds.set(signature, clientRequestId);
    const response = await decideReviewGroup(projectId, transactionId, groupId, request, clientRequestId);
    actionRetryIds.delete(signature);
    if (get().projectId !== projectId || get().transactionId !== transactionId) return;
    const token = fenceMutation('manifest', projectId, transactionId);
    set((state) => isCurrent(token, state) ? {
      manifest: response.manifest,
      loading: false,
      error: null,
    } : {});
  },
  comment: async (groupId, text, selection) => {
    const { projectId, transactionId } = get();
    if (!projectId || !transactionId) throw new Error('当前没有可审阅的 Transaction');
    const signature = JSON.stringify({ projectId, transactionId, groupId, text, selection });
    const clientCommentId = commentRetryIds.get(signature) ?? newClientId('review-comment');
    commentRetryIds.set(signature, clientCommentId);
    await commentOnReviewGroup(projectId, transactionId, groupId, {
      clientCommentId,
      text,
      selection,
    });
    commentRetryIds.delete(signature);
  },
  loadAuthorizations: async () => {
    const { projectId, transactionId } = get();
    if (!projectId || !transactionId) return;
    const token = beginRequest('authorizations', projectId, transactionId);
    const response = await listExecutionAuthorizations(projectId, transactionId);
    set((state) => isCurrent(token, state) ? { authorizations: response.items } : {});
  },
  loadFileAuthorizations: async (projectId) => {
    bindFileScope(projectId);
    const token = beginRequest('authorizations', projectId, null);
    const response = await listFileExecutionAuthorizations(projectId);
    set((state) => isCurrent(token, state) ? { authorizations: response.items ?? [] } : {});
  },
  loadOperationContent: async (operationId) => {
    const { projectId, transactionId, manifest, operationContents, operationContentLoading } = get();
    if (!projectId || !transactionId || !manifest || operationContents[operationId] || operationContentLoading[operationId]) return;
    const token = beginRequest(`operation:${operationId}`, projectId, transactionId);
    set((state) => ({
      operationContentLoading: { ...state.operationContentLoading, [operationId]: true },
      operationContentErrors: { ...state.operationContentErrors, [operationId]: '' },
    }));
    try {
      const content = await getReviewOperationContent(projectId, manifest.reviewRevisionId, operationId);
      set((state) => isCurrent(token, state) ? ({
          operationContents: { ...state.operationContents, [operationId]: content },
          operationContentLoading: { ...state.operationContentLoading, [operationId]: false },
        }) : {});
    } catch (error) {
      set((state) => isCurrent(token, state) ? ({
          operationContentLoading: { ...state.operationContentLoading, [operationId]: false },
          operationContentErrors: { ...state.operationContentErrors, [operationId]: (error as Error).message },
        }) : {});
      throw error;
    }
  },
  approveAuthorization: async (authorizationId, request) => {
    const { projectId, transactionId } = get();
    if (!projectId) throw new Error('当前没有活动 Project');
    const signature = JSON.stringify({ projectId, transactionId, authorizationId, request, action: 'approve' });
    const clientRequestId = actionRetryIds.get(signature) ?? newClientId('authorization-approve');
    actionRetryIds.set(signature, clientRequestId);
    const updated = transactionId
      ? await approveExecutionAuthorization(projectId, transactionId, authorizationId, request, clientRequestId)
      : await approveFileExecutionAuthorization(projectId, authorizationId, request, clientRequestId);
    actionRetryIds.delete(signature);
    if (get().projectId !== projectId || get().transactionId !== transactionId) return;
    const token = fenceMutation('authorizations', projectId, transactionId);
    set((state) => isCurrent(token, state) ? ({
      authorizations: state.authorizations.map((item) => item.id === authorizationId ? updated : item),
    }) : {});
  },
  declineAuthorization: async (authorizationId, authorizationToken) => {
    const { projectId, transactionId } = get();
    if (!projectId) throw new Error('当前没有活动 Project');
    const request = {
      authorizationToken,
    };
    const signature = JSON.stringify({ projectId, transactionId, authorizationId, request, action: 'decline' });
    const clientRequestId = actionRetryIds.get(signature) ?? newClientId('authorization-decline');
    actionRetryIds.set(signature, clientRequestId);
    const updated = transactionId
      ? await declineExecutionAuthorization(projectId, transactionId, authorizationId, request, clientRequestId)
      : await declineFileExecutionAuthorization(projectId, authorizationId, request, clientRequestId);
    actionRetryIds.delete(signature);
    if (get().projectId !== projectId || get().transactionId !== transactionId) return;
    const token = fenceMutation('authorizations', projectId, transactionId);
    set((state) => isCurrent(token, state) ? ({
      authorizations: state.authorizations.map((item) => item.id === authorizationId ? updated : item),
    }) : {});
  },
  reset: () => {
    invalidateRequests();
    set({
      projectId: null,
      transactionId: null,
      manifest: null,
      authorizations: [],
      operationContents: {},
      operationContentLoading: {},
      operationContentErrors: {},
      loading: false,
      error: null,
    });
  },
  };
});
