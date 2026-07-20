import { Button, Modal } from 'antd';
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { ExternalLink } from 'lucide-react';
import type { AssetLibraryView, ResolvedRef } from '@/contracts/creator';
import { navigate } from '@/routing/navigation';
import { presentationOf, useWorkspaceViewStore } from '@/store/workspaceViewStore';
import { projectJsonPointer } from '@/lib/projectJsonPointer';
import type { AssetDisplayItem } from './AssetCard';
import { assetTypeTag } from './AssetCard';
import AssetMediaPreview from './AssetMediaPreview';

const STATUS_LABELS = { draft: '草稿', pending: '待统一审阅', accepted: '已接受', stale: '已过期' } as const;
const STATUS_TONES = {
  draft: 'border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-tertiary)]',
  pending: 'border-[var(--color-accent)]/25 bg-[var(--color-accent-soft)] text-[var(--color-accent)]',
  accepted: 'border-[var(--color-success)]/25 bg-[var(--color-success-soft)] text-[var(--color-success)]',
  stale: 'border-[var(--color-danger)]/25 bg-[var(--color-danger-soft)] text-[var(--color-danger)]',
} as const;

function identifierOf(ref: string): string {
  return ref.split('/').at(-1)?.split('@')[0] || ref.split(':').at(-1) || ref;
}

function sameRef(left: string, right: string): boolean {
  return left === right || identifierOf(left) === identifierOf(right);
}

function navigateToResolved(projectId: string, resolved: ResolvedRef) {
  const locator = resolved.uiLocator || {};
  if (locator.page === 'workbench' && locator.unitId) navigate(`/project/${projectId}/plan/unit/${locator.unitId}/workbench`);
  else if (locator.page === 'section-compose' && locator.sectionId) navigate(`/project/${projectId}/plan/section/${locator.sectionId}`);
  else if (locator.page === 'final-compose') navigate(`/project/${projectId}/plan?finalCompose=1`);
  else if (locator.page === 'assets' && locator.assetId) navigate(`/project/${projectId}/assets?select=${locator.assetId}${locator.versionId ? `&version=${locator.versionId}` : ''}`);
  else if (locator.sectionId) navigate(`/project/${projectId}/plan?section=${locator.sectionId}`);
  else if (locator.unitId) navigate(`/project/${projectId}/plan?unit=${locator.unitId}`);
}

function RefChip({ projectId, view, refId }: { projectId: string; view: AssetLibraryView; refId: string }) {
  const resolved = view.resolvedRefs.find((item) => sameRef(item.ref, refId));
  const label = resolved?.name ?? refId;
  return (
    <button
      type="button"
      onClick={() => resolved && navigateToResolved(projectId, resolved)}
      className={`inline-flex max-w-full items-center gap-1 truncate rounded-md px-1.5 py-0.5 text-[11px] font-medium transition-colors ${resolved ? 'text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]' : 'text-[var(--color-text-tertiary)] line-through'}`}
      title={resolved ? label : '引用目标已不存在'}
    >
      @{label}
    </button>
  );
}

function RelationBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-[var(--color-bg-secondary)]/60 px-3 py-2.5">
      <b className="block text-[11px] font-bold text-[var(--color-text-primary)]">{title}</b>
      <div className="mt-1 text-[11px] leading-5 text-[var(--color-text-secondary)]">{children}</div>
    </div>
  );
}

function relationRefs(view: AssetLibraryView, asset: AssetDisplayItem) {
  const outgoing: Array<{ ref: string; kind: string }> = [];
  const incoming: Array<{ ref: string; kind: string }> = [];
  for (const relation of view.relations) {
    const from = String(relation.from || relation.sourceRef || relation.source || '');
    const to = String(relation.to || relation.targetRef || relation.target || '');
    const kind = String(relation.kind || relation.type || 'references');
    if (from && to && sameRef(from, asset.sourceRef)) outgoing.push({ ref: to, kind });
    if (from && to && sameRef(to, asset.sourceRef)) incoming.push({ ref: from, kind });
  }
  return { outgoing, incoming };
}

function categoryLabel(category: string, scenario?: string): string {
  if (category === 'subject_ref') return scenario === 'short_drama' ? '角色' : scenario === 'video_edit' ? '主体素材' : '主体参考';
  if (category === 'env_ref') return scenario === 'short_drama' ? '场景' : scenario === 'video_edit' ? '场景素材' : '环境参考';
  if (category === 'brand_constraint') return '品牌约束';
  if (category === 'understanding') return '理解资产';
  if (category === 'generated') return '生成资产';
  if (category === 'upload') return '用户上传';
  return category;
}

export default function AssetInspector({ projectId, asset, view, onEditDetail, onDelete }: {
  projectId: string;
  asset: AssetDisplayItem;
  view: AssetLibraryView;
  onEditDetail?: (asset: AssetDisplayItem) => void;
  onDelete: (asset: AssetDisplayItem) => void | Promise<void>;
}) {
  const header = presentationOf(useWorkspaceViewStore((state) => state.header));
  const { outgoing, incoming } = relationRefs(view, asset);
  const derivedFrom = outgoing.filter((item) => /derive/i.test(item.kind));
  const referencedBy = incoming.filter((item) => !/constraint|constrain|derive/i.test(item.kind));
  const derivatives = incoming.filter((item) => /derive/i.test(item.kind));
  const constraintRefs = outgoing.filter((item) => /constraint|constrain/i.test(item.kind));
  const constrainsRefs = incoming.filter((item) => /constraint|constrain/i.test(item.kind));
  const assetNamePath = asset.kind === 'visual'
    ? projectJsonPointer('visual', 'entities', 'items', asset.id, 'name')
    : asset.versionId
      ? projectJsonPointer('assets', 'source_versions_by_id', asset.versionId, 'name')
      : undefined;
  const assetDescriptionPath = asset.kind === 'visual'
    ? projectJsonPointer('visual', 'entities', 'items', asset.id, 'description')
    : undefined;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
        <div className="min-w-0">
          <h3
            data-creator-field={`asset:${asset.id}/name`}
            data-creator-path={assetNamePath}
            data-creator-field-label="资产名称"
            className="truncate text-sm font-semibold text-[var(--color-text-primary)]"
          >
            {asset.name}
          </h3>
          <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{categoryLabel(asset.category, header?.scenario)} · {assetTypeTag(asset)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className={`rounded border px-1.5 py-px text-[10px] ${STATUS_TONES[asset.status]}`}>{asset.planned ? '待生成' : STATUS_LABELS[asset.status]}</span>
          <button
            type="button"
            onClick={() => Modal.confirm({
              title: `删除「${asset.name}」？`,
              content: '删除后无法恢复',
              okText: '删除',
              cancelText: '取消',
              okButtonProps: { danger: true },
              centered: true,
              onOk: () => onDelete(asset),
            })}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
            title="删除"
            aria-label="删除资产"
          >
            <DeleteOutlined className="text-xs" />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {(asset.mediaType === 'image' || asset.mediaType === 'video') && (
          <AssetMediaPreview
            name={asset.name}
            mediaType={asset.mediaType}
            previewUrl={asset.previewUrl}
            state={asset.previewState}
            controls={asset.mediaType === 'video'}
            mediaClassName="w-full rounded-lg border border-[var(--color-border)]"
            placeholderClassName="flex h-28 w-full items-center justify-center rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-secondary)] text-xs font-semibold text-[var(--color-text-tertiary)]"
          />
        )}
        {asset.mediaType === 'url' && asset.sourceUrl && (
          <a href={asset.sourceUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 truncate rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-accent)] hover:bg-[var(--color-accent-soft)]">
            <ExternalLink className="h-3 w-3 shrink-0" /><span className="truncate">{asset.sourceUrl}</span>
          </a>
        )}
        {(asset.userNotes || (asset.content && asset.generatedKind !== 'storyboard_image')) && (
          <p
            data-creator-field={`asset:${asset.id}/description`}
            data-creator-path={assetDescriptionPath}
            data-creator-field-label="资产描述"
            className="whitespace-pre-wrap rounded-lg bg-[var(--color-bg-secondary)]/60 px-3 py-2 text-xs leading-5 text-[var(--color-text-secondary)]"
          >
            {asset.userNotes || asset.content}
          </p>
        )}

        {asset.generatedKind === 'storyboard_image' && asset.content && (
          <RelationBlock title="生成 Prompt">
            <p className="max-h-40 overflow-y-auto whitespace-pre-wrap">{asset.content}</p>
          </RelationBlock>
        )}
        {asset.detail?.prompts?.some((prompt) => prompt.trim()) && (
          <RelationBlock title="文生图 Prompt">
            <div className="max-h-40 space-y-2 overflow-y-auto whitespace-pre-wrap">
              {asset.detail.prompts.map((prompt, index) => prompt.trim() ? (
                <p key={`${asset.id}-prompt-${index}`}>{prompt}</p>
              ) : null)}
            </div>
          </RelationBlock>
        )}

        <RelationBlock title="来源">
          {derivedFrom.length > 0 ? (
            <span className="flex flex-wrap items-center gap-1">派生自{derivedFrom.map((item) => <RefChip key={item.ref} projectId={projectId} view={view} refId={item.ref} />)}</span>
          ) : asset.sourceLine || '—'}
        </RelationBlock>
        <RelationBlock title={`被引用（${referencedBy.length + derivatives.length}）`}>
          {referencedBy.length === 0 && derivatives.length === 0 ? '暂未被任何对象引用。' : (
            <span className="flex flex-wrap items-center gap-1">
              {referencedBy.map((item) => <RefChip key={`u-${item.ref}`} projectId={projectId} view={view} refId={item.ref} />)}
              {derivatives.map((item) => <RefChip key={`d-${item.ref}`} projectId={projectId} view={view} refId={item.ref} />)}
            </span>
          )}
        </RelationBlock>
        <RelationBlock title="作用约束">
          {constraintRefs.length === 0 && constrainsRefs.length === 0 ? '暂无关联约束。' : (
            <span className="flex flex-wrap items-center gap-1">
              {constraintRefs.length > 0 && '受'}
              {constraintRefs.map((item) => <RefChip key={`cb-${item.ref}`} projectId={projectId} view={view} refId={item.ref} />)}
              {constraintRefs.length > 0 && '约束'}
              {constrainsRefs.length > 0 && '约束了'}
              {constrainsRefs.map((item) => <RefChip key={`c-${item.ref}`} projectId={projectId} view={view} refId={item.ref} />)}
            </span>
          )}
        </RelationBlock>
      </div>

      <div className="flex items-center gap-2 border-t border-[var(--color-border)] p-3">
        {asset.generatedKind === 'storyboard_image' && (
          <Button
            size="small"
            onClick={() => {
              const unitId = asset.ownerRef?.startsWith('unit:') ? asset.ownerRef.slice(5) : '';
              if (unitId) navigate(`/project/${projectId}/plan/unit/${unitId}/workbench`);
            }}
            disabled={!asset.ownerRef?.startsWith('unit:')}
            className="!flex-1 !text-xs"
          >
            前往工作台修改
          </Button>
        )}
        {onEditDetail && (
          <Button size="small" icon={<EditOutlined />} onClick={() => onEditDetail(asset)} className="!flex-1 !text-xs">编辑详情</Button>
        )}
      </div>
    </div>
  );
}
