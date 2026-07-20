import { useCallback, useRef, useState } from 'react';
import { message } from 'antd';
import type {
  CreatorCommandAccepted,
  CreatorCommandType,
  ReviewPresentationView,
  ViewEnvelope,
} from '@/contracts/creator';
import { newClientId, submitCreatorCommand } from '@/api/creator';

const COALESCED_AUTOSAVE_COMMANDS = new Set<CreatorCommandType>([
  'SET_STRATEGY_TEXT',
  'SET_SECTION_TEXT',
  'SET_UNIT_TEXT',
  'SET_EDIT_AUDIO_PLAN',
]);

function isCoalescedAutosave(type: CreatorCommandType): boolean {
  return COALESCED_AUTOSAVE_COMMANDS.has(type);
}

function reviewPresentation<T>(envelope: ViewEnvelope<T>): ReviewPresentationView<T> | null {
  const value = envelope.view as T | ReviewPresentationView<T>;
  return value && typeof value === 'object' && 'presentationVersion' in value
    ? value as ReviewPresentationView<T>
    : null;
}

export function buildCreatorCommand<T>(
  envelope: ViewEnvelope<T>,
  type: CreatorCommandType,
  targetRef: string,
  args: Record<string, unknown>,
  objectVersion?: string,
) {
  const presentation = reviewPresentation(envelope);
  const targetMetadata = presentation?.targetVersions[targetRef];
  const coalescedAutosave = isCoalescedAutosave(type);
  return {
    clientCommandId: newClientId('command'),
    editSessionId: coalescedAutosave ? newClientId('edit') : undefined,
    type,
    targetRef,
    arguments: args,
    // This submit path is called by blur/confirm handlers.  Per-keystroke
    // clients may send autosaveCommit=false (or omit it) and let the Runtime's
    // durable silent window coalesce their drafts.
    context: coalescedAutosave ? { autosaveCommit: true } : {},
    expectedTargetVersions: objectVersion || targetMetadata?.targetVersion
      ? [{ ref: targetRef, objectVersion: objectVersion || targetMetadata!.targetVersion }]
      : [],
    expectedPresentationVersion: presentation?.presentationVersion,
    expectedDecisionToken: targetMetadata?.decisionToken,
    expectedOverlayHead: presentation?.overlayHead || envelope.manualEditOverlay?.head,
  };
}

export function commandStatusCopy(result: CreatorCommandAccepted, uiPhase: string): string {
  if (result.status === 'DEFERRED_UNTIL_REVIEW_RESOLVED') return '已记录，将在本轮审阅结束后执行';
  if (result.status === 'QUEUED') return '已排队，Creator 会在合法消息边界继续处理';
  if (uiPhase === 'waiting_review') return '已加入本轮待审修改';
  return '修改已提交';
}

export function useCreatorCommand<T>(
  projectId: string,
  envelope: ViewEnvelope<T> | null,
  afterSuccess?: () => void | Promise<void>,
) {
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<CreatorCommandAccepted | null>(null);
  const retryIds = useRef(new Map<string, { clientCommandId: string; editSessionId?: string }>());
  const submit = useCallback(async (
    type: CreatorCommandType,
    targetRef: string,
    args: Record<string, unknown>,
    objectVersion?: string,
  ) => {
    if (!envelope) throw new Error('页面 View 尚未加载');
    setSubmitting(true);
    const signature = JSON.stringify({
      type,
      targetRef,
      args,
      objectVersion,
      approvedRevisionId: envelope.approvedRevisionId,
      workingHead: envelope.workingHead,
      reviewRevisionId: envelope.reviewRevisionId,
      overlayHead: envelope.manualEditOverlay?.head,
    });
    const stableIds = retryIds.current.get(signature) ?? {
      clientCommandId: newClientId('command'),
      editSessionId: isCoalescedAutosave(type) ? newClientId('edit') : undefined,
    };
    retryIds.current.set(signature, stableIds);
    const command = buildCreatorCommand(envelope, type, targetRef, args, objectVersion);
    try {
      const result = await submitCreatorCommand(
        projectId,
        { ...command, ...stableIds },
      );
      retryIds.current.delete(signature);
      setLastResult(result);
      message.success(commandStatusCopy(result, envelope.uiPhase));
      try {
        await afterSuccess?.();
      } catch (refreshError) {
        message.warning(`命令已持久化，但刷新 View 失败：${(refreshError as Error).message}`);
      }
      return result;
    } catch (error) {
      // Local drafts are deliberately not cleared on CAS/phase errors.
      message.error((error as Error).message);
      return null;
    } finally {
      setSubmitting(false);
    }
  }, [afterSuccess, envelope, projectId]);
  return { submit, submitting, lastResult };
}
