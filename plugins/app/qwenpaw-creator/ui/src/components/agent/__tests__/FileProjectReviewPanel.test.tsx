import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import FileProjectReviewPanel from '@/components/agent/FileProjectReviewPanel';
import type { FileProjectReviewRecord } from '@/contracts/creator';
import { useFileProjectReviewStore } from '@/store/fileProjectReviewStore';

function review(operationCount = 1): FileProjectReviewRecord {
  return {
    review_id: 'review-1',
    round_id: 'round-1',
    request_id: 'request-1',
    request_message_seq: 4,
    interrupted_run_id: 'run-1',
    baseline_generation: 2,
    baseline_etag: 'base-2',
    candidate_generation: 3,
    candidate_etag: 'candidate-3',
    decision_token: 'token-1',
    status: 'PENDING',
    operations: Array.from({ length: operationCount }, (_, index) => ({
      kind: 'update',
      json_pointer: index === 0 ? '/story/title' : `/story/scenes/${index}`,
      file_id: null,
      target_ref: null,
      before_hash: `before-${index}`,
      after_hash: `after-${index}`,
      before: index === 0 ? 'Old title' : { index, enabled: false },
      after: index === 0 ? { title: 'New title', text: 'x'.repeat(300) } : { index, enabled: true },
      operation_id: `operation-${index + 1}`,
      ui_locator: {},
      decision: 'PENDING',
    })),
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:01Z',
  };
}

function seed(value: FileProjectReviewRecord, decide = vi.fn(async () => value)) {
  useFileProjectReviewStore.setState({
    projectId: 'p1',
    review: value,
    etag: '"token-1"',
    syncStatus: 'healthy',
    syncError: null,
    decisionInFlight: false,
    decide,
  });
  return decide;
}

afterEach(() => useFileProjectReviewStore.getState().reset());

describe('FileProjectReviewPanel', () => {
  it('only renders for the active Project file Review', () => {
    seed(review());
    const { rerender } = render(<FileProjectReviewPanel projectId="p2" />);
    expect(screen.queryByText('文件项目修改')).not.toBeInTheDocument();

    rerender(<FileProjectReviewPanel projectId="p1" />);
    expect(screen.getByText('文件项目修改')).toBeInTheDocument();
    expect(screen.getByText('/story/title')).toBeInTheDocument();
    expect(screen.getByText('Old title')).toBeInTheDocument();
    expect(screen.getByText('展开完整值')).toBeInTheDocument();
  });

  it('submits an individual Keep decision by operation_id', async () => {
    const decide = seed(review());
    render(<FileProjectReviewPanel projectId="p1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Keep /story/title' }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith('p1', [{
      operation_id: 'operation-1',
      decision: 'ACCEPT',
    }]));
  });

  it('submits all pending operations in one Undo all request', async () => {
    const value = review(2);
    const decide = seed(value);
    render(<FileProjectReviewPanel projectId="p1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Undo all' }));
    await waitFor(() => expect(decide).toHaveBeenCalledWith('p1', [
      { operation_id: 'operation-1', decision: 'REJECT' },
      { operation_id: 'operation-2', decision: 'REJECT' },
    ]));
  });
});
