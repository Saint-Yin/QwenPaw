import { useEffect, useRef, useState } from "react";
import { Button, InputNumber, Input, Popconfirm } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import type { ShotCamera, ShotView } from "@/contracts/creator";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";
import { projectJsonPointer } from "@/lib/projectJsonPointer";

const { TextArea } = Input;

const CANONICAL_CAMERAS: ShotCamera[] = [
  "⊙ 静止",
  "↑ 推近",
  "↓ 拉远",
  "→ 横摇右",
  "← 横摇左",
  "↕ 升降",
  "◎ 环绕",
  "～ 手持晃动",
];

interface ShotListProps {
  shots: ShotView[];
  unitId: string;
  sectionId?: string;
  disabled?: boolean;
  onUpsert: (shot: ShotView) => Promise<unknown>;
  onDelete: (shot: ShotView) => Promise<unknown>;
}

/** origin/main Shot 列表外观；持久化改走 canonical UPSERT/DELETE Command。 */
export default function ShotList({
  shots,
  unitId,
  sectionId,
  disabled,
  onUpsert,
  onDelete,
}: ShotListProps) {
  const [drafts, setDrafts] = useState<Record<string, ShotView>>(() =>
    Object.fromEntries(shots.map((shot) => [shot.id, shot])),
  );
  const draftsRef = useRef(drafts);
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const onUpsertRef = useRef(onUpsert);
  draftsRef.current = drafts;
  onUpsertRef.current = onUpsert;

  useEffect(() => {
    setDrafts((current) =>
      Object.fromEntries(
        shots.map((shot) => [
          shot.id,
          timersRef.current.has(shot.id) ? current[shot.id] || shot : shot,
        ]),
      ),
    );
  }, [shots]);

  useEffect(
    () => () => {
      for (const [shotId, timer] of timersRef.current) {
        clearTimeout(timer);
        const draft = draftsRef.current[shotId];
        if (draft) void onUpsertRef.current(draft);
      }
      timersRef.current.clear();
    },
    [],
  );

  const sameShot = (left: ShotView, right: ShotView) =>
    left.description === right.description &&
    left.camera === right.camera &&
    left.framing === right.framing &&
    left.cameraDescription === right.cameraDescription &&
    left.dialogue === right.dialogue &&
    left.duration === right.duration;

  const commit = (
    shot: ShotView,
    draft = draftsRef.current[shot.id] || shot,
  ) => {
    const timer = timersRef.current.get(shot.id);
    if (timer) clearTimeout(timer);
    timersRef.current.delete(shot.id);
    if (!sameShot(draft, shot)) void onUpsertRef.current(draft);
  };

  const patchDraft = (shot: ShotView, patch: Partial<ShotView>) => {
    const next = { ...(draftsRef.current[shot.id] || shot), ...patch };
    draftsRef.current = { ...draftsRef.current, [shot.id]: next };
    setDrafts(draftsRef.current);
    const previous = timersRef.current.get(shot.id);
    if (previous) clearTimeout(previous);
    timersRef.current.set(
      shot.id,
      setTimeout(() => commit(shot, next), 600),
    );
  };

  const trackShotFocus = (shotId: string, field: string) => {
    const store = useCreatorInteractionStore.getState();
    store.select(`shot:${shotId}`);
    store.setEditingField(`unit:${unitId}/shot:${shotId}/${field}`);
  };

  const addShot = () => {
    const maxNumber =
      shots.length > 0 ? Math.max(...shots.map((shot) => shot.number)) : 0;
    void onUpsert({
      id: `shot-${Date.now()}`,
      number: maxNumber + 1,
      duration: 3,
      description: "",
      camera: "⊙ 静止",
      framing: "中景",
      cameraDescription: "中景",
      dialogue: "",
      targetVersion: "",
    });
  };

  return (
    <div className="space-y-2">
      {shots.map((shot) => {
        const draft = drafts[shot.id] || shot;
        return (
          <div
            key={shot.id}
            data-creator-module="shot-row"
            data-creator-module-id={shot.id}
            data-creator-module-ref={`unit:${unitId}`}
            className="flex items-start gap-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 p-2.5"
          >
            <span className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-primary)] text-[10px] font-bold text-[var(--color-text-secondary)]">
              {shot.number}
            </span>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div
                data-creator-field={`unit:${unitId}/shot:${shot.id}/description`}
                data-creator-path={
                  sectionId
                    ? projectJsonPointer(
                        "story",
                        "sections",
                        "items",
                        sectionId,
                        "units",
                        "items",
                        unitId,
                        "shots",
                        "items",
                        shot.id,
                        "description",
                      )
                    : undefined
                }
                data-creator-field-label={`镜头${shot.number} · 描述`}
              >
                <TextArea
                  value={draft.description}
                  disabled={disabled}
                  onChange={(event) =>
                    patchDraft(shot, { description: event.target.value })
                  }
                  onFocus={() => trackShotFocus(shot.id, "description")}
                  onBlur={() => {
                    commit(shot);
                    useCreatorInteractionStore.getState().setEditingField(null);
                  }}
                  autoSize={{ minRows: 1, maxRows: 6 }}
                  placeholder="镜头描述…"
                  className="!rounded-md !border-transparent !bg-transparent !p-1 !text-xs hover:!border-[var(--color-border)] focus:!border-[var(--color-accent)]"
                />
              </div>
              <div className="flex items-center gap-2">
                <span
                  data-creator-field={`unit:${unitId}/shot:${shot.id}/cameraDescription`}
                  data-creator-path={
                    sectionId
                      ? projectJsonPointer(
                          "story",
                          "sections",
                          "items",
                          sectionId,
                          "units",
                          "items",
                          unitId,
                          "shots",
                          "items",
                          shot.id,
                          "camera_description",
                        )
                      : undefined
                  }
                  data-creator-field-label={`镜头${shot.number} · 运镜`}
                  className="contents"
                >
                  <Input
                    value={
                      draft.cameraDescription ??
                      `${draft.camera} · ${draft.framing}`
                    }
                    disabled={disabled}
                    onChange={(event) => {
                      const value = event.target.value;
                      patchDraft(shot, {
                        cameraDescription: value,
                        ...(CANONICAL_CAMERAS.includes(value as ShotCamera)
                          ? { camera: value as ShotCamera }
                          : {}),
                      });
                    }}
                    onFocus={() => trackShotFocus(shot.id, "cameraDescription")}
                    onBlur={() => {
                      commit(shot);
                      useCreatorInteractionStore
                        .getState()
                        .setEditingField(null);
                    }}
                    size="small"
                    placeholder="镜头运镜"
                    className="!w-36 !rounded-md !text-[11px]"
                  />
                </span>
                <span
                  data-creator-field={`unit:${unitId}/shot:${shot.id}/duration`}
                  data-creator-path={
                    sectionId
                      ? projectJsonPointer(
                          "story",
                          "sections",
                          "items",
                          sectionId,
                          "units",
                          "items",
                          unitId,
                          "shots",
                          "items",
                          shot.id,
                          "duration_seconds",
                        )
                      : undefined
                  }
                  data-creator-field-label={`镜头${shot.number} · 时长`}
                >
                  <InputNumber
                    min={1}
                    max={15}
                    value={draft.duration}
                    disabled={disabled}
                    onChange={(value) =>
                      patchDraft(shot, { duration: value ?? 1 })
                    }
                    onFocus={() => trackShotFocus(shot.id, "duration")}
                    onBlur={() => {
                      commit(shot);
                      useCreatorInteractionStore
                        .getState()
                        .setEditingField(null);
                    }}
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
        onClick={addShot}
        disabled={disabled}
        className="!w-full !text-xs"
      >
        添加镜头
      </Button>
    </div>
  );
}
