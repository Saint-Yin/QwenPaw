/**
 * Origin run/review surface projected from SpecialistRun + Review Manifest.
 * The component is a read/action surface over the unique Run and Decision
 * Group authorities.
 */
import { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { navigateToLocator } from '@/routing/locators';
import { useAgentDockUiStore } from '@/store/agentDockUiStore';
import { useCreatorTaskViewStore } from '@/store/creatorTaskViewStore';
import { useReviewManifestStore } from '@/store/reviewManifestStore';

interface RunReviewPanelProps {
  projectId: string;
  variant?: 'full' | 'gates-only' | 'review';
  excludeRunIds?: string[];
}

export default function RunReviewPanel({
  projectId,
  variant = 'full',
  excludeRunIds = [],
}: RunReviewPanelProps) {
  const runs = useCreatorTaskViewStore((state) => state.runs);
  const manifest = useReviewManifestStore((state) => state.manifest);
  const contents = useReviewManifestStore((state) => state.operationContents);
  const loadContent = useReviewManifestStore((state) => state.loadOperationContent);
  const decide = useReviewManifestStore((state) => state.decide);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const pendingGroups = manifest?.decisionGroups.filter((group) => group.decision === 'PENDING') ?? [];
  const pendingOperationIds = new Set(pendingGroups.flatMap((group) => group.operationIds));
  const operationsByRun = useMemo(() => new Map(runs.map((run) => [
    run.id,
    manifest?.operations.filter((operation) => operation.actorRunIds.includes(run.id)) ?? [],
  ])), [manifest, runs]);
  const visibleRuns = runs.filter((run) => {
    if (excludeRunIds.includes(run.id)) return false;
    if (variant !== 'review') return true;
    return (operationsByRun.get(run.id) ?? []).some((operation) => pendingOperationIds.has(operation.id))
      || run.status === 'STALE'
      || run.metadata.reviewPending === true;
  });
  const showRuns = variant !== 'gates-only';

  useEffect(() => {
    if (!expandedRunId) return;
    (operationsByRun.get(expandedRunId) ?? []).forEach((operation) => {
      if (!contents[operation.id] && ['markdown', 'text', 'vtt', 'ctm'].includes(operation.artifactKind)) {
        void loadContent(operation.id).catch(() => undefined);
      }
    });
  }, [contents, expandedRunId, loadContent, operationsByRun]);

  const groupsForRun = (runId: string) => {
    const operationIds = new Set((operationsByRun.get(runId) ?? []).map((operation) => operation.id));
    return pendingGroups.filter((group) => group.operationIds.some((id) => operationIds.has(id)));
  };
  const decideGroups = async (groupIds: string[], decision: 'ACCEPT' | 'REJECT') => {
    setBusy(true);
    try {
      for (const groupId of groupIds) {
        const current = useReviewManifestStore.getState().manifest?.decisionGroups
          .find((group) => group.id === groupId && group.decision === 'PENDING');
        if (current) await decide(groupId, { decisionToken: current.decisionToken, decision });
      }
      setSelectedGroupIds((ids) => ids.filter((id) => !groupIds.includes(id)));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const jumpRef = (runId: string, ref: string) => {
    const operation = (operationsByRun.get(runId) ?? []).find((item) => item.targetRef === ref);
    if (!operation?.uiLocator) return;
    useAgentDockUiStore.getState().setOpen(false);
    navigateToLocator(projectId, operation.uiLocator, { description: 'AgentDock Review' });
  };

  if (!showRuns || visibleRuns.length === 0) return null;

  return (
    <div className="agent-run-review-panel" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <section>
        <h4 style={{ margin: '4px 0' }}>{variant === 'review' ? '待审提案' : 'Sub-Agent 运行'}</h4>
        {visibleRuns.map((run) => {
          const operations = operationsByRun.get(run.id) ?? [];
          const groups = groupsForRun(run.id);
          const hasReviewGroups = groups.length > 0;
          const status = hasReviewGroups ? 'pending_review' : run.status.toLowerCase();
          const selectedForRun = groups.filter((group) => selectedGroupIds.includes(group.id));
          return (
            <div key={run.id} style={{ border: '1px solid #eee', borderRadius: 8, padding: 8, marginBottom: 8 }}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => setExpandedRunId((value) => value === run.id ? null : run.id)}
                onKeyDown={(event) => { if (event.key === 'Enter') setExpandedRunId((value) => value === run.id ? null : run.id); }}
                style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}
              >
                <span>{run.displayName}</span>
                <span style={{ fontSize: 12, opacity: 0.7 }}>
                  {status} · {operations.length} 文件 · rev {manifest?.baseRevisionId ?? '-'}
                </span>
              </div>
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                {run.targetRefs.map((ref) => (
                  <button
                    key={ref}
                    onClick={() => jumpRef(run.id, ref)}
                    style={{ marginRight: 6, color: '#1565c0', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontSize: 12 }}
                  >
                    {ref}
                  </button>
                ))}
              </div>

              {expandedRunId === run.id && (
                <div style={{ marginTop: 8 }}>
                  {run.finalSummaryText && <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>{run.finalSummaryText}</div>}
                  {run.finalMarker && (
                    <div style={{ fontSize: 12, color: run.finalMarker === 'SUCCESS' ? '#2e7d32' : '#c62828' }}>
                      校验：{run.finalMarker === 'SUCCESS' ? '通过' : '未通过'}
                    </div>
                  )}
                  {groups.some((group) => group.groupingReasons.length > 0) && (
                    <div style={{ fontSize: 12, color: '#b26a00', background: '#fff8e1', borderRadius: 6, padding: 6, marginTop: 4 }}>
                      影响下游 {groups.length} 项：{groups.flatMap((group) => group.groupingReasons).join('、')}
                    </div>
                  )}
                  {groups.map((group) => {
                    const checked = selectedGroupIds.includes(group.id);
                    const groupOperations = operations.filter((operation) => group.operationIds.includes(operation.id));
                    return (
                      <div key={group.id} style={{ marginTop: 6 }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={busy}
                            onChange={() => setSelectedGroupIds((ids) => checked ? ids.filter((id) => id !== group.id) : [...ids, group.id])}
                          />
                          <span>{group.title}</span>
                          <span style={{ fontWeight: 400, opacity: 0.7 }}>{groupOperations.length} 项</span>
                        </label>
                        {groupOperations.map((operation) => {
                          const content = contents[operation.id];
                          return content ? (
                            <pre key={operation.id} style={{ fontSize: 11, background: '#0d1117', color: '#c9d1d9', padding: 8, overflow: 'auto', maxHeight: 200 }}>
                              {content.before ?? ''}{'\n→\n'}{content.after ?? ''}
                            </pre>
                          ) : <div key={operation.id} style={{ fontSize: 11, opacity: 0.7 }}>{operation.path ?? operation.targetRef}</div>;
                        })}
                      </div>
                    );
                  })}
                  {hasReviewGroups && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                      <button disabled={busy || selectedForRun.length === 0} onClick={() => void decideGroups(selectedForRun.map((group) => group.id), 'ACCEPT')}>
                        应用选中（其余保留待审）{selectedForRun.length > 0 ? ` · ${selectedForRun.length}` : ''}
                      </button>
                      <button disabled={busy} onClick={() => void decideGroups(groups.map((group) => group.id), 'ACCEPT')}>接受全部</button>
                      <button disabled={busy} onClick={() => void decideGroups(groups.map((group) => group.id), 'REJECT')}>全部驳回</button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
