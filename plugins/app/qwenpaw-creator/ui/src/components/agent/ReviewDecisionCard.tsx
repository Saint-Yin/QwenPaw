import { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { ClipboardCheck, FileQuestion, FileVideo } from 'lucide-react';
import { getArtifactVersionMediaUrl, getAssetVersionMediaUrl } from '@/api/creator';
import type {
  IntegrationPreview,
  MediaComparison,
  ReviewDecisionGroup,
  ReviewMediaVersion,
  ReviewOperation,
} from '@/contracts/creator';
import { navigateToLocator } from '@/routing/locators';
import { useAgentDockUiStore } from '@/store/agentDockUiStore';
import { useReviewManifestStore } from '@/store/reviewManifestStore';
import ReviewDiffText from './ReviewDiffText';
import { resolveReviewNavigationTarget } from './reviewNavigation';

const BUTTON_BASE = 'rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-50';
const BUTTON_PRIMARY = `${BUTTON_BASE} bg-[var(--color-accent)] text-white hover:opacity-90`;
const BUTTON_GHOST = `${BUTTON_BASE} border border-[var(--color-border)] bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]`;

function mediaVersionUrl(version: ReviewMediaVersion): string {
  return version.versionKind === 'artifact'
    ? getArtifactVersionMediaUrl(version.versionId)
    : getAssetVersionMediaUrl(version.versionId);
}

function DecisionThumb({ title, comparison }: { title: string; comparison?: MediaComparison }) {
  const version = comparison?.after ?? comparison?.before ?? comparison?.candidates[0];
  if (version?.mediaType === 'image') {
    return (
      <img
        src={mediaVersionUrl(version)}
        alt={title}
        className="h-10 w-14 shrink-0 rounded-md border border-[var(--color-border)] object-cover"
      />
    );
  }
  const Icon = version?.mediaType === 'video' ? FileVideo : FileQuestion;
  return (
    <div className="flex h-10 w-14 shrink-0 items-center justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
      <Icon className="h-4 w-4 text-[var(--color-text-tertiary)]" />
    </div>
  );
}

export default function ReviewDecisionCard({
  projectId,
  group,
  operations,
  mediaComparisons = [],
  integrationPreviews = [],
}: {
  projectId: string;
  group: ReviewDecisionGroup;
  operations: ReviewOperation[];
  mediaComparisons?: MediaComparison[];
  integrationPreviews?: IntegrationPreview[];
}) {
  const decide = useReviewManifestStore((state) => state.decide);
  const operationContents = useReviewManifestStore((state) => state.operationContents);
  const contentLoading = useReviewManifestStore((state) => state.operationContentLoading);
  const contentErrors = useReviewManifestStore((state) => state.operationContentErrors);
  const loadOperationContent = useReviewManifestStore((state) => state.loadOperationContent);
  const selectedText = useAgentDockUiStore((state) => state.selection);
  const setOpen = useAgentDockUiStore((state) => state.setOpen);
  const setReviewContext = useAgentDockUiStore((state) => state.setReviewContext);
  const requestReviewRevision = useAgentDockUiStore((state) => state.requestReviewRevision);
  const [busy, setBusy] = useState(false);
  const pending = group.decision === 'PENDING';
  const first = operations[0];
  const reasons = useMemo(
    () => [...new Set([...group.groupingReasons, ...operations.flatMap((item) => item.dependencyReasons)])],
    [group.groupingReasons, operations],
  );
  const groupSelection = selectedText && operations.some((operation) => (
    operation.path === selectedText.field || operation.targetRef === selectedText.ref
  )) ? selectedText : null;
  const textOperations = operations.filter((operation) => (
    ['markdown', 'text', 'vtt', 'ctm'].includes(operation.artifactKind)
  ));
  const textOperationKey = textOperations.map((operation) => operation.id).join(':');

  useEffect(() => {
    textOperations.forEach((operation) => {
      void loadOperationContent(operation.id).catch(() => undefined);
    });
  }, [loadOperationContent, textOperationKey]);

  const accept = async () => {
    setBusy(true);
    try {
      await decide(group.id, {
        decisionToken: group.decisionToken,
        decision: 'ACCEPT',
      });
      const dockState = useAgentDockUiStore.getState();
      if (dockState.reviewRevisionHandoff?.groupId === group.id) {
        dockState.clearReviewRevisionHandoff();
      } else if (dockState.reviewContext?.groupId === group.id) {
        setReviewContext(null);
      }
      message.success('该组已接受并应用');
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    setBusy(true);
    try {
      await decide(group.id, {
        decisionToken: group.decisionToken,
        decision: 'REJECT',
      });
      const dockState = useAgentDockUiStore.getState();
      if (dockState.reviewRevisionHandoff?.groupId === group.id) {
        dockState.clearReviewRevisionHandoff();
      } else if (dockState.reviewContext?.groupId === group.id) {
        setReviewContext(null);
      }
      message.success('已撤销该项改动');
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const revise = () => {
    requestReviewRevision({
      groupId: group.id,
      decisionToken: group.decisionToken,
      title: group.title,
      targetRef: first?.targetRef ?? null,
      selection: groupSelection?.field
        ? { field: groupSelection.field, text: groupSelection.text }
        : undefined,
    });
  };

  const view = () => {
    const target = resolveReviewNavigationTarget({ group, operations, mediaComparisons, integrationPreviews });
    if (!target) return;
    setReviewContext({
      groupId: group.id,
      decisionToken: group.decisionToken,
      title: group.title,
      targetRef: target.targetRef,
      selection: groupSelection?.field
        ? { field: groupSelection.field, text: groupSelection.text }
        : undefined,
    });
    setOpen(false);
    navigateToLocator(projectId, target.locator, {
      description: '审阅/决策',
      review: true,
      field: target.field,
    });
  };

  const detail = reasons.length > 0
    ? reasons.join('；')
    : `${operations.length} 项变更${first?.targetRef ? ` · ${first.targetRef}` : ''}`;

  return (
    <article data-review-decision-card={group.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-2.5">
      <div className="flex items-start gap-2.5">
        <DecisionThumb title={group.title} comparison={mediaComparisons[0]} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1 rounded bg-[var(--color-accent-soft)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--color-accent)]">
              <ClipboardCheck className="h-3 w-3" />
              {pending ? '待审' : '已处理'}
            </span>
            <span className="min-w-0 flex-1 truncate text-xs font-semibold text-[var(--color-text-primary)]">{group.title}</span>
          </div>
          <p className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-[var(--color-text-tertiary)]">{detail}</p>
          {textOperations.length > 0 && (
            <div className="mt-1.5 max-h-40 space-y-1 overflow-y-auto">
              {textOperations.map((operation) => {
                const content = operationContents[operation.id];
                return (
                  <div key={operation.id} className="rounded bg-[var(--color-bg-secondary)] px-1.5 py-1">
                    <div className="mb-0.5 text-[10px] font-semibold text-[var(--color-text-tertiary)]">{operation.kind} · {operation.targetRef}</div>
                    {content && <ReviewDiffText before={content.before || ''} after={content.after || ''} field={operation.path || operation.targetRef} />}
                    {contentLoading[operation.id] && <p className="text-[10px] text-[var(--color-text-tertiary)]">加载 immutable text diff…</p>}
                    {contentErrors[operation.id] && <p className="text-[10px] text-[var(--color-danger)]">{contentErrors[operation.id]}</p>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {pending && (
          <>
            <button type="button" disabled={busy} onClick={() => void accept()} className={`flex-1 ${BUTTON_PRIMARY}`}>接受</button>
            <button type="button" disabled={busy} onClick={() => void reject()} className={`flex-1 ${BUTTON_GHOST}`}>撤销</button>
            <button type="button" disabled={busy} onClick={revise} className={BUTTON_GHOST}>要求修改</button>
          </>
        )}
        {(first?.uiLocator || integrationPreviews[0]?.uiLocator) && (
          <button type="button" onClick={view} className={BUTTON_GHOST}>查看</button>
        )}
      </div>
    </article>
  );
}
