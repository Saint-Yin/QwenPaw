import type {
  ExecutionAuthorizationApproval,
  ExecutionAuthorizationDecision,
  ExecutionAuthorizationView,
  ReviewCommentRequest,
  ReviewCommentResponse,
  ReviewDecisionRequest,
  ReviewDecisionResponse,
  ReviewManifest,
  ReviewOperationContent,
  ViewEnvelope,
} from '@/contracts/creator';
import { creatorRequest, jsonBody, newClientId } from './client';

const transaction = (projectId: string, transactionId: string) => (
  `/projects/${encodeURIComponent(projectId)}/transactions/${encodeURIComponent(transactionId)}`
);

export function getActiveTransaction(projectId: string): Promise<Record<string, unknown> | null> {
  return creatorRequest(`/projects/${encodeURIComponent(projectId)}/transactions/active`);
}

export function getTransaction(projectId: string, transactionId: string): Promise<Record<string, unknown>> {
  return creatorRequest(transaction(projectId, transactionId));
}

export async function getReviewManifest(projectId: string, transactionId: string): Promise<ReviewManifest | null> {
  const manifest = await creatorRequest<ReviewManifest | undefined>(
    `${transaction(projectId, transactionId)}/review`,
  );
  return manifest ?? null;
}

export async function getReviewOperationContent(
  projectId: string,
  reviewRevisionId: string,
  operationId: string,
): Promise<ReviewOperationContent> {
  const response = await creatorRequest<ViewEnvelope<ReviewOperationContent>>(
    `/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(reviewRevisionId)}`
      + `/review-operation-${encodeURIComponent(operationId)}`,
  );
  return response.view as ReviewOperationContent;
}

export function decideReviewGroup(
  projectId: string,
  transactionId: string,
  groupId: string,
  request: ReviewDecisionRequest,
  clientRequestId = newClientId('review-decision'),
): Promise<ReviewDecisionResponse> {
  return creatorRequest(
    `${transaction(projectId, transactionId)}/review/groups/${encodeURIComponent(groupId)}/decision`,
    { method: 'PUT', headers: { 'Idempotency-Key': clientRequestId }, body: jsonBody(request) },
  );
}

export function commentOnReviewGroup(
  projectId: string,
  transactionId: string,
  groupId: string,
  request: ReviewCommentRequest,
): Promise<ReviewCommentResponse> {
  return creatorRequest(
    `${transaction(projectId, transactionId)}/review/groups/${encodeURIComponent(groupId)}/comments`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': request.clientCommentId },
      body: jsonBody(request),
    },
  );
}

export function listExecutionAuthorizations(
  projectId: string,
  transactionId: string,
  status = 'PENDING',
): Promise<{ items: ExecutionAuthorizationView[] }> {
  return creatorRequest(`${transaction(projectId, transactionId)}/execution-authorizations?status=${status}`);
}

export function getExecutionAuthorization(
  projectId: string,
  transactionId: string,
  authorizationId: string,
): Promise<ExecutionAuthorizationView> {
  return creatorRequest(
    `${transaction(projectId, transactionId)}/execution-authorizations/${encodeURIComponent(authorizationId)}`,
  );
}

export function approveExecutionAuthorization(
  projectId: string,
  transactionId: string,
  authorizationId: string,
  request: ExecutionAuthorizationApproval,
  clientRequestId = newClientId('authorization-approve'),
): Promise<ExecutionAuthorizationView> {
  return creatorRequest(
    `${transaction(projectId, transactionId)}/execution-authorizations/${encodeURIComponent(authorizationId)}/approve`,
    { method: 'POST', headers: { 'Idempotency-Key': clientRequestId }, body: jsonBody(request) },
  );
}

export function declineExecutionAuthorization(
  projectId: string,
  transactionId: string,
  authorizationId: string,
  request: ExecutionAuthorizationDecision,
  clientRequestId = newClientId('authorization-decline'),
): Promise<ExecutionAuthorizationView> {
  return creatorRequest(
    `${transaction(projectId, transactionId)}/execution-authorizations/${encodeURIComponent(authorizationId)}/decline`,
    { method: 'POST', headers: { 'Idempotency-Key': clientRequestId }, body: jsonBody(request) },
  );
}
