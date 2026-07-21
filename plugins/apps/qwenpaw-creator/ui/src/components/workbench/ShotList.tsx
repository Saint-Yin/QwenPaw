import { useEffect, useState } from "react";
import { Button, InputNumber, Input, Popconfirm } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import type {
  ProjectEntityCollection,
  ShotDocument,
} from "@/contracts/creator";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";

const { TextArea } = Input;

type ShotField = "description" | "camera" | "framing" | "duration_seconds";

interface ShotListProps {
  shots: ProjectEntityCollection<ShotDocument>;
  elementId: string;
  shotPointer: (shotId: string, field: ShotField) => string;
  disabled?: boolean;
  onPatchField: (
    shotId: string,
    field: ShotField,
    before: unknown,
    value: unknown,
  ) => Promise<unknown>;
  onAdd: () => Promise<unknown>;
  onDelete: (shot: ShotDocument) => Promise<unknown>;
}

/** origin/main Shot 列表外观；持久化改走 schema-v2 Project CAS Patch。 */
export default function ShotList({
  shots,
  elementId,
  shotPointer,
  disabled,
  onPatchField,
  onAdd,
  onDelete,
}: ShotListProps) {
  const [drafts, setDrafts] = useState<Record<string, ShotDocument>>(() =>
    Object.fromEntries(
      shots.order.map((shotId) => [shotId, shots.items[shotId]]),
    ),
  );

  useEffect(() => {
    setDrafts(
      Object.fromEntries(
        shots.order.map((shotId) => [shotId, shots.items[shotId]]),
      ),
    );
  }, [shots]);

  const patchDraft = (shotId: string, patch: Partial<ShotDocument>) =>
    setDrafts((current) => ({
      ...current,
      [shotId]: { ...(current[shotId] ?? shots.items[shotId]), ...patch },
    }));

  const commit = (shot: ShotDocument, field: ShotField) => {
    const draft = drafts[shot.shot_id];
    if (!draft || draft[field] === shot[field]) return;
    void onPatchField(shot.shot_id, field, shot[field], draft[field]).catch(
      () => patchDraft(shot.shot_id, { [field]: shot[field] }),
    );
  };

  const trackShotFocus = (shotId: string, field: ShotField) => {
    const store = useCreatorInteractionStore.getState();
    store.select(`element:${elementId}`);
    store.setEditingField(`element:${elementId}/shot:${shotId}/${field}`);
  };

  const releaseShotFocus = (shot: ShotDocument, field: ShotField) => {
    commit(shot, field);
    useCreatorInteractionStore.getState().setEditingField(null);
  };

  return (
    <div className="space-y-2">
      {shots.order.map((shotId, index) => {
        const shot = shots.items[shotId];
        if (!shot) return null;
        const draft = drafts[shotId] ?? shot;
        return (
          <div
            key={shotId}
            data-creator-module="shot-row"
            data-creator-module-id={shotId}
            data-creator-module-ref={`element:${elementId}`}
            className="flex items-start gap-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 p-2.5"
          >
            <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-primary)] text-[10px] font-bold text-[var(--color-text-secondary)]">
              {index + 1}
            </span>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div
                data-creator-field={`element:${elementId}/shot:${shotId}/description`}
                data-creator-path={shotPointer(shotId, "description")}
                data-creator-field-label={`镜头${index + 1} · 描述`}
              >
                <TextArea
                  value={draft.description}
                  disabled={disabled}
                  onChange={(event) =>
                    patchDraft(shotId, { description: event.target.value })
                  }
                  onFocus={() => trackShotFocus(shotId, "description")}
                  onBlur={() => releaseShotFocus(shot, "description")}
                  autoSize={{ minRows: 1, maxRows: 6 }}
                  placeholder="镜头描述…"
                  className="!rounded-md !border-transparent !bg-transparent !p-1 !text-xs hover:!border-[var(--color-border)] focus:!border-[var(--color-accent)]"
                />
              </div>
              <div className="flex items-center gap-2">
                <span
                  data-creator-field={`element:${elementId}/shot:${shotId}/camera`}
                  data-creator-path={shotPointer(shotId, "camera")}
                  data-creator-field-label={`镜头${index + 1} · 运镜`}
                  className="contents"
                >
                  <Input
                    value={draft.camera ?? ""}
                    disabled={disabled}
                    onChange={(event) =>
                      patchDraft(shotId, { camera: event.target.value })
                    }
                    onFocus={() => trackShotFocus(shotId, "camera")}
                    onBlur={() => releaseShotFocus(shot, "camera")}
                    size="small"
                    placeholder="镜头运镜"
                    className="!w-28 !rounded-md !text-[11px]"
                  />
                </span>
                <span
                  data-creator-field={`element:${elementId}/shot:${shotId}/framing`}
                  data-creator-path={shotPointer(shotId, "framing")}
                  data-creator-field-label={`镜头${index + 1} · 景别`}
                  className="contents"
                >
                  <Input
                    value={draft.framing ?? ""}
                    disabled={disabled}
                    onChange={(event) =>
                      patchDraft(shotId, { framing: event.target.value })
                    }
                    onFocus={() => trackShotFocus(shotId, "framing")}
                    onBlur={() => releaseShotFocus(shot, "framing")}
                    size="small"
                    placeholder="景别"
                    className="!w-20 !rounded-md !text-[11px]"
                  />
                </span>
                <span
                  data-creator-field={`element:${elementId}/shot:${shotId}/duration_seconds`}
                  data-creator-path={shotPointer(shotId, "duration_seconds")}
                  data-creator-field-label={`镜头${index + 1} · 时长`}
                >
                  <InputNumber
                    min={1}
                    max={15}
                    value={draft.duration_seconds}
                    disabled={disabled}
                    onChange={(value) =>
                      patchDraft(shotId, { duration_seconds: value ?? 1 })
                    }
                    onFocus={() => trackShotFocus(shotId, "duration_seconds")}
                    onBlur={() => releaseShotFocus(shot, "duration_seconds")}
                    size="small"
                    addonAfter="s"
                    className="!w-24"
                  />
                </span>
              </div>
            </div>
            <Popconfirm
              title="删除此镜头？"
              onConfirm={() => void onDelete(shot)}
              okText="删除"
              cancelText="取消"
            >
              <Button
                type="text"
                size="small"
                disabled={disabled}
                icon={<DeleteOutlined />}
                className="!text-[var(--color-text-tertiary)] hover:!text-[var(--color-danger)]"
              />
            </Popconfirm>
          </div>
        );
      })}
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        onClick={() => void onAdd()}
        disabled={disabled}
        className="!w-full !text-xs"
      >
        添加镜头
      </Button>
    </div>
  );
}
