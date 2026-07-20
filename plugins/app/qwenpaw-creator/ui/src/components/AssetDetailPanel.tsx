import { useMemo, useRef, useState } from 'react';
import { Drawer, Button, Tag, Empty, Input, message, Modal, Popconfirm } from 'antd';
import { CloseOutlined, EditOutlined, UserOutlined, PictureOutlined, StarOutlined, LinkOutlined, UploadOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { displayMediaUrl } from '@/lib/mediaUrl';
import type { AssetDetailView } from '@/contracts/creator';
import NewAppearanceModal from './assets/NewAppearanceModal';

type AssetItem = AssetDetailView;

export interface ReferenceImageOption {
  value: string;
  url?: string;
  label: string;
  available: boolean;
}

interface AssetDetailPanelProps {
  open: boolean;
  onClose: () => void;
  asset: AssetItem | null;
  assetType: 'characters' | 'scenes' | 'props' | 'materials';
  projectId?: string;
  initialPromptIndex?: number;
  referenceImageOptions?: ReferenceImageOption[];
  onEdit?: () => void;
  onNameChange?: (asset: AssetItem, name: string) => void;
  onPromptConfigChange?: (asset: AssetItem, promptIndex: number, prompt: string, referenceImageUrls: string[]) => void;
  onGeneratePrompt?: (asset: AssetItem, promptIndex: number, prompt: string, referenceImageUrls: string[]) => Promise<void>;
  onUploadImage?: (asset: AssetItem, index: number, file: File) => void | Promise<void>;
  onUploadReference?: (asset: AssetItem, file: File) => void | Promise<void>;
  onAddAppearance?: (asset: AssetItem, refDescription: string, prompt: string, imageUrl: string) => Promise<void>;
  onDeleteAppearance?: (asset: AssetItem, index: number) => Promise<void>;
  onGenerateAppearancePrompt?: (asset: AssetItem, refDescription: string) => Promise<string>;
  onGenerateAppearanceImage?: (asset: AssetItem, prompt: string) => Promise<string>;
}

export default function AssetDetailPanel({
  open,
  onClose,
  asset,
  assetType,
  projectId,
  initialPromptIndex = 0,
  referenceImageOptions = [],
  onEdit,
  onNameChange,
  onPromptConfigChange,
  onGeneratePrompt,
  onUploadImage,
  onUploadReference,
  onAddAppearance,
  onDeleteAppearance,
  onGenerateAppearancePrompt,
  onGenerateAppearanceImage,
}: AssetDetailPanelProps) {
  const [promptState, setPromptState] = useState<{
    assetId: string;
    index: number;
    draft: string;
    referenceDraft: string;
  } | null>(null);
  const [generatingIndex, setGeneratingIndex] = useState<number | null>(null);
  const [editingName, setEditingName] = useState(false);
    const [nameDraft, setNameDraft] = useState('');
    const [originalName, setOriginalName] = useState('');

    // 清理状态逻辑
    const handleClose = () => {
      setEditingName(false);
      setNameDraft('');
      setOriginalName('');
      setUploadingIndex(null);
      setUploadingReference(false);
      onClose();
    };
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);
  const [uploadingReference, setUploadingReference] = useState(false);
  const uploadImageInputRef = useRef<HTMLInputElement>(null);
  const uploadReferenceInputRef = useRef<HTMLInputElement>(null);

  // ── 新建形象弹窗 ─────────────────────────────────────────────
  const [newAppearanceOpen, setNewAppearanceOpen] = useState(false);

  const promptEntries = useMemo(() => {
    if (!asset) return [];
    const refs = asset.refsNeeded;
    const prompts = asset.prompts;
    const storedImageCount = asset.images.length;
    const count = Math.max(refs.length, prompts.length, storedImageCount, assetType === 'characters' ? 0 : 1);

    return Array.from({ length: count || 1 }, (_, index) => {
      const image = asset.images[index]?.url || (index === 0 ? asset.primaryUrl || '' : '');
      const requirement = refs[index] || asset.images[index]?.name || '';
      return {
        index,
        title: requirement || `Prompt ${index + 1}`,
        requirement,
        prompt: prompts[index] || '',
        image,
        referenceImageUrls: (asset.referenceImageRefs[index] || []).filter((url) => url.trim()),
      };
    });
  }, [asset, assetType]);

  if (!asset) return null;

  const activePromptIndex = promptState?.assetId === asset.id ? promptState.index : Math.min(initialPromptIndex, Math.max(promptEntries.length - 1, 0));
  const activeEntryForState = promptEntries[activePromptIndex];
  const draftPrompt = promptState?.assetId === asset.id
    ? promptState.draft
    : activeEntryForState?.prompt || '';
  const referenceDraft = promptState?.assetId === asset.id
    ? promptState.referenceDraft
    : activeEntryForState?.referenceImageUrls.join('\n') || '';

  const parseReferenceDraft = (value: string) => value
    .split('\n')
    .map((url) => url.trim())
    .filter(Boolean);

  const getReferenceLabel = (value: string) => {
    return referenceImageOptions.find((option) => option.value === value)?.label || value;
  };

  const selectedReferenceValues = parseReferenceDraft(referenceDraft);
  const selectedMissingReferences = selectedReferenceValues.filter((value) => {
    const option = referenceImageOptions.find((candidate) => candidate.value === value);
    return option ? !option.available : false;
  });

  const toggleReferenceValue = (value: string) => {
    const cleanValue = value.trim();
    if (!cleanValue) return;
    const currentReferences = parseReferenceDraft(referenceDraft);
    const nextReferences = currentReferences.includes(cleanValue)
      ? currentReferences.filter((reference) => reference !== cleanValue)
      : [...currentReferences, cleanValue];
    setPromptState({
      assetId: asset.id,
      index: activePromptIndex,
      draft: draftPrompt,
      referenceDraft: nextReferences.join('\n'),
    });
    onPromptConfigChange?.(asset, activePromptIndex, draftPrompt, nextReferences);
  };

  const savePrompt = () => {
    onPromptConfigChange?.(asset, activePromptIndex, draftPrompt, parseReferenceDraft(referenceDraft));
  };

  const handleGenerate = async () => {
    if (!onGeneratePrompt || selectedMissingReferences.length > 0) return;
    savePrompt();
    setGeneratingIndex(activePromptIndex);
    try {
      await onGeneratePrompt(asset, activePromptIndex, draftPrompt, parseReferenceDraft(referenceDraft));
    } finally {
      setGeneratingIndex(null);
    }
  };

  const getDisplayDescription = (description?: string) => {
    return description?.split('\n')[0]?.trim() || '';
  };

  const renderPromptEditor = (listTitle: string) => {
    const activeEntry = promptEntries[activePromptIndex] || promptEntries[0];
    return (
      <div>
        <h4 className="mb-3 text-sm font-medium text-[var(--color-text-secondary)]">{listTitle}</h4>
        <div className="space-y-3">
          {promptEntries.map((entry) => {
            const selected = entry.index === activePromptIndex;
            return (
              <button
                key={entry.index}
                type="button"
                onClick={() => setPromptState({
                  assetId: asset.id,
                  index: entry.index,
                  draft: entry.prompt,
                  referenceDraft: entry.referenceImageUrls.join('\n'),
                })}
                className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                  selected
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
                    : 'border-[var(--color-border)] bg-[var(--color-bg-secondary)] hover:border-[var(--color-accent)]/50'
                }`}
              >
                <div className="group relative h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-[var(--color-bg-card)]">
                  {entry.image ? (
                    <img src={displayMediaUrl(entry.image)} alt={entry.title} className="h-full w-full object-cover" />
                  ) : onUploadImage ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setUploadingIndex(entry.index);
                        uploadImageInputRef.current?.click();
                      }}
                      disabled={uploadingIndex === entry.index}
                      className="flex h-full w-full items-center justify-center text-xs text-[var(--color-text-tertiary)] hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-accent)] disabled:opacity-50"
                      title="本地上传"
                    >
                      {uploadingIndex === entry.index ? '上传中...' : <UploadOutlined />}
                    </button>
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs text-[var(--color-text-tertiary)]">
                      待生成
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">{entry.title}</p>
                  <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">
                    {entry.prompt ? 'Prompt 已就绪' : 'Prompt 待补'} · 引用图 {entry.referenceImageUrls.length}
                  </p>
                </div>
                {/* 删除按钮（第一个是主图，不允许删除） */}
                {onDeleteAppearance && entry.index > 0 && (
                  <Popconfirm
                    title="确定删除此形象？"
                    okText="删除"
                    cancelText="取消"
                    onConfirm={async (e) => {
                      e?.stopPropagation();
                      try {
                        await onDeleteAppearance(asset, entry.index);
                        message.success('已删除');
                      } catch (err) {
                        message.error(`删除失败：${(err as Error).message}`);
                      }
                    }}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <button
                      type="button"
                      onClick={(e) => e.stopPropagation()}
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[var(--color-text-tertiary)] transition-colors hover:bg-red-50 hover:text-red-500"
                      title="删除此形象"
                    >
                      <DeleteOutlined style={{ fontSize: 12 }} />
                    </button>
                  </Popconfirm>
                )}
              </button>
            );
          })}
          {/* 新建形象按钮 */}
          {onAddAppearance && (
            <button
              type="button"
              onClick={() => setNewAppearanceOpen(true)}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--color-border)] p-3 text-sm text-[var(--color-text-tertiary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            >
              <PlusOutlined /> 新建形象
            </button>
          )}
        </div>

        {activeEntry && (
          <div className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-[var(--color-text-primary)]">{activeEntry.title}</span>
            </div>
            <Input.TextArea
              value={draftPrompt}
              onChange={(event) => setPromptState({
                assetId: asset.id,
                index: activePromptIndex,
                draft: event.target.value,
                referenceDraft,
              })}
              onBlur={savePrompt}
              rows={6}
              placeholder="输入文生图 Prompt"
            />
            <div className="mt-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--color-text-secondary)]">参考图输入</span>
                <Tag color={parseReferenceDraft(referenceDraft).length > 0 ? 'blue' : 'default'}>
                  {parseReferenceDraft(referenceDraft).length} 张
                </Tag>
              </div>
              {selectedMissingReferences.length > 0 && (
                <div className="mb-2 rounded-md border border-[var(--color-warning)]/30 bg-[var(--color-warning-soft)] px-2 py-2 text-xs leading-5 text-[var(--color-warning)]">
                  依赖图片尚未生成：{selectedMissingReferences.map(getReferenceLabel).join('、')}
                </div>
              )}
              <div className="mb-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2">
                <div className="mb-2 text-xs font-medium text-[var(--color-text-secondary)]">已有资产图</div>
                {referenceImageOptions.length > 0 ? (
                  <div className="grid max-h-36 grid-cols-3 gap-2 overflow-y-auto">
                    {referenceImageOptions.map((option) => {
                      const selected = parseReferenceDraft(referenceDraft).includes(option.value);
                      return (
                        <button
                          key={option.value}
                          type="button"
                          title={option.label}
                          onClick={() => toggleReferenceValue(option.value)}
                          className={`overflow-hidden rounded-lg border text-left transition-colors ${
                            selected
                              ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
                              : 'border-[var(--color-border)] bg-[var(--color-bg-card)] hover:border-[var(--color-accent)]/50'
                          }`}
                        >
                          {option.url ? (
                            <img src={displayMediaUrl(option.url)} alt={option.label} className="h-14 w-full object-cover" />
                          ) : (
                            <div className="flex h-14 w-full items-center justify-center bg-[var(--color-bg-secondary)] text-[10px] text-[var(--color-text-tertiary)]">
                              待生成
                            </div>
                          )}
                          <span className="block truncate px-1.5 py-1 text-[10px] text-[var(--color-text-secondary)]">
                            {option.label}
                          </span>
                          {!option.available && (
                            <span className="block px-1.5 pb-1 text-[10px] text-[var(--color-warning)]">依赖未完成</span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-[var(--color-border)] px-2 py-3 text-xs text-[var(--color-text-tertiary)]">
                    暂无可选的已生成资产图
                  </div>
                )}
              </div>

              {/* 本地上传参考图 */}
              {onUploadReference && asset && (
                <div className="mt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setUploadingReference(true);
                      uploadReferenceInputRef.current?.click();
                    }}
                    disabled={uploadingReference}
                    className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-[var(--color-border)] py-2 text-xs text-[var(--color-text-tertiary)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] disabled:opacity-50"
                  >
                    {uploadingReference ? '上传中...' : <><UploadOutlined /> 本地上传参考图</>}
                  </button>
                </div>
              )}
            </div>
            <div className="mt-3 flex gap-2">
              <Button className="!rounded-lg flex-1" onClick={savePrompt}>
                保存 Prompt
              </Button>
              {onGeneratePrompt && (
                <Button
                  type="primary"
                  className="!rounded-lg flex-1"
                  loading={generatingIndex === activePromptIndex}
                  disabled={!draftPrompt.trim() || selectedMissingReferences.length > 0}
                  onClick={handleGenerate}
                >
                  {activeEntry.image ? '重新生成' : '生成'}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderCharacterDetail = (char: AssetDetailView) => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-[var(--color-accent-soft)]">
          <UserOutlined className="text-2xl text-[var(--color-accent)]" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{char.name}</h3>
        </div>
      </div>

      {promptEntries.length === 0 ? (
        <Empty description="暂无形象规划" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : renderPromptEditor(`形象列表 (${promptEntries.length})`)}
    </div>
  );

  const renderSceneDetail = (scene: AssetDetailView) => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-16 h-16 rounded-xl bg-[var(--color-bg-secondary)] flex items-center justify-center">
          <PictureOutlined className="text-2xl text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{scene.name}</h3>
        </div>
      </div>

      {getDisplayDescription(scene.description) && (
        <div>
          <h4 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">描述</h4>
          <p className="text-sm text-[var(--color-text-primary)]">{getDisplayDescription(scene.description)}</p>
        </div>
      )}

      {(scene.images[0]?.url || scene.primaryUrl) && (
        <div>
          <h4 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">场景图片</h4>
          <div className="rounded-xl overflow-hidden border border-[var(--color-border)]">
            <img src={displayMediaUrl(scene.images[0]?.url || scene.primaryUrl || '')} alt={scene.name} className="w-full object-cover" />
          </div>
        </div>
      )}

      {renderPromptEditor('场景生成 Prompt')}
    </div>
  );

  const renderPropDetail = (prop: AssetDetailView) => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-16 h-16 rounded-xl bg-[var(--color-warning-soft)] flex items-center justify-center">
          <StarOutlined className="text-2xl text-[var(--color-warning)]" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{prop.name}</h3>
        </div>
      </div>
      {getDisplayDescription(prop.description) && (
        <div>
          <h4 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">描述</h4>
          <p className="text-sm text-[var(--color-text-primary)]">{getDisplayDescription(prop.description)}</p>
        </div>
      )}
      {(prop.images[0]?.url || prop.primaryUrl) && (
        <div>
          <h4 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">图片</h4>
          <div className="rounded-xl overflow-hidden border border-[var(--color-border)]">
            <img src={displayMediaUrl(prop.images[0]?.url || prop.primaryUrl || '')} alt={prop.name} className="w-full object-cover" />
          </div>
        </div>
      )}
      {renderPromptEditor('道具生成 Prompt')}
    </div>
  );

  const renderMaterialDetail = (mat: AssetDetailView) => (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-[var(--color-accent-soft)]">
          <LinkOutlined className="text-2xl text-[var(--color-accent)]" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{mat.name}</h3>
          <Tag>{mat.mediaType === 'image' ? '图片' : mat.mediaType === 'video' ? '视频' : '音频'}</Tag>
        </div>
      </div>
      {mat.primaryUrl && (
        <div>
          <h4 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">资源地址</h4>
          <p className="break-all rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2 text-xs text-[var(--color-text-secondary)]">{mat.primaryUrl}</p>
        </div>
      )}
      {renderPromptEditor('素材生成 Prompt')}
    </div>
  );

  const renderContent = () => {
    switch (assetType) {
      case 'characters':
        return renderCharacterDetail(asset);
      case 'scenes':
        return renderSceneDetail(asset);
      case 'props':
        return renderPropDetail(asset);
      case 'materials':
        return renderMaterialDetail(asset);
      default:
        return null;
    }
  };

  return (
    <Drawer
      open={open}
      onClose={handleClose}
      title={null}
      closable={false}
      width={380}
      styles={{
        body: { padding: '24px', background: 'var(--color-bg-card)' },
        header: { display: 'none' },
      }}
      mask={false}
      className="asset-detail-drawer"
    >
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-[var(--color-text-secondary)]">资产详情</span>
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          onClick={onClose}
          className="!text-[var(--color-text-secondary)]"
        />
      </div>

      {/* 资产名编辑 */}
      {asset && onNameChange && (
        <div className="mb-4">
          <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1">
            {assetType === 'characters' ? '角色名' : assetType === 'scenes' ? '场景名' : assetType === 'props' ? '道具名' : '素材名'}
          </label>
          {editingName ? (
            <Input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={() => {
                const trimmedName = nameDraft.trim();
                if (trimmedName !== originalName) {
                  onNameChange(asset, trimmedName || asset.name);
                }
                setEditingName(false);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onNameChange(asset, nameDraft.trim() || asset.name);
                  setEditingName(false);
                }
                if (e.key === 'Escape') {
                  setEditingName(false);
                  setNameDraft(originalName);
                }
              }}
              size="small"
              autoFocus
            />
          ) : (
            <div className="flex items-center gap-2">
              <span className="flex-1 truncate text-sm font-semibold text-[var(--color-text-primary)]">{asset.name}</span>
              <button
                type="button"
                onClick={() => {
                  setOriginalName(asset.name);
                  setNameDraft(asset.name);
                  setEditingName(true);
                }}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-bg-secondary)] hover:text-[var(--color-accent)]"
                title="编辑名称"
              >
                <EditOutlined className="text-xs" />
              </button>
            </div>
          )}
        </div>
      )}

      {renderContent()}

      {/* 新建形象 Modal */}
      {asset && projectId && (
        <NewAppearanceModal
          open={newAppearanceOpen}
          onClose={() => setNewAppearanceOpen(false)}
          onConfirm={async (refDescription, prompt, imageUrl) => {
            if (onAddAppearance) {
              await onAddAppearance(asset, refDescription, prompt, imageUrl);
            }
            setNewAppearanceOpen(false);
          }}
          assetName={asset.name}
          projectId={projectId}
          assetId={asset.id}
          referenceImageUrl={
            assetType === 'characters' ? asset.images[0]?.url : undefined
          }
          onGeneratePrompt={(refDescription) => onGenerateAppearancePrompt
            ? onGenerateAppearancePrompt(asset, refDescription)
            : Promise.resolve(`${asset.name}，${refDescription}`)}
          onGenerateImage={(prompt) => onGenerateAppearanceImage
            ? onGenerateAppearanceImage(asset, prompt)
            : Promise.resolve(
              assetType === 'characters'
                ? asset.images[0]?.url || ''
                : '',
            )}
        />
      )}

      <div className="flex gap-2 mt-8 pt-4 border-t border-[var(--color-border)]">
        {onEdit && (
          <Button
            type="primary"
            icon={<EditOutlined />}
            onClick={onEdit}
            className="!rounded-lg flex-1"
          >
            编辑
          </Button>
        )}
        <Button onClick={onClose} className="!rounded-lg flex-1">
          关闭
        </Button>
      </div>

      {/* 隐藏的文件输入 */}
      <input
        ref={uploadImageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
                    if (file && asset && onUploadImage) {
                      // 文件类型验证
                      if (!file.type.startsWith('image/')) {
                        message.error('请选择图片文件');
                        return;
                      }
                      // 文件大小验证（例如限制为10MB）
                      const MAX_FILE_SIZE = 10 * 1024 * 1024;
                      if (file.size > MAX_FILE_SIZE) {
                        message.error('图片大小不能超过10MB');
                        return;
                      }
                      onUploadImage(asset, promptState?.index ?? 0, file);
                    }
          e.target.value = '';
          setUploadingIndex(null);
        }}
      />
      <input
        ref={uploadReferenceInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
                    if (file && asset && onUploadReference) {
                      // 使用异步处理等待上传完成
                      Promise.resolve(onUploadReference(asset, file))
                        .finally(() => {
                          e.target.value = '';
                          setUploadingReference(false);
                        });
                    }
        }}
      />
    </Drawer>
  );
}
