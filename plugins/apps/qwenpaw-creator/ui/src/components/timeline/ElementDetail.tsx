import { useEffect, useMemo, useState } from "react";
import { Button, Input, InputNumber, Modal, Switch, message } from "antd";
import {
  ArrowUpRight,
  Box,
  Clock3,
  Film,
  Layers3,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import type {
  ProjectDocument,
  TaskView,
  TimelineDocument,
  TimelineElementDocument,
} from "@/contracts/creator";
import { getArtifactVersionMediaUrl } from "@/api/creator";
import {
  ELEMENT_TYPE_META,
  elementCreationSummary,
  resolveElementOutputs,
} from "@/selectors/timelineElementSelectors";
import { projectJsonPointer } from "@/lib/projectJsonPointer";

interface ElementDetailProps {
  project: ProjectDocument;
  timeline: TimelineDocument;
  element: TimelineElementDocument | null;
  tasks: TaskView[];
  patching: boolean;
  onClose: () => void;
  onPatch: (path: string, before: unknown, value: unknown) => Promise<void>;
  onDelete: (element: TimelineElementDocument) => Promise<void>;
  onAgent: (element: TimelineElementDocument, prompt?: string) => void;
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">
      {children}
    </span>
  );
}

function TextField({
  label,
  value,
  multiline = false,
  path,
  field,
  onCommit,
}: {
  label: string;
  value: string;
  multiline?: boolean;
  path: string;
  field: string;
  onCommit: (value: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    if (draft === value) return;
    void onCommit(draft).catch(() => setDraft(value));
  };
  return (
    <label
      data-creator-field={field}
      data-creator-path={path}
      data-creator-field-label={label}
      className="block"
    >
      <FieldLabel>{label}</FieldLabel>
      {multiline ? (
        <Input.TextArea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          autoSize={{ minRows: 3, maxRows: 8 }}
        />
      ) : (
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
        />
      )}
    </label>
  );
}

function taskStatus(element: TimelineElementDocument, tasks: TaskView[]) {
  const task = tasks.find(
    (item) => item.targetRef === `element:${element.element_id}`,
  );
  if (task?.status === "RUNNING" || task?.status === "QUEUED")
    return {
      label: task.status === "RUNNING" ? "生成中" : "等待中",
      tone: "text-[var(--color-warning)] bg-[var(--color-warning-soft)]",
    };
  if (task?.status === "FAILED" || task?.status === "QUARANTINED")
    return {
      label: "生成失败",
      tone: "text-[var(--color-danger)] bg-[var(--color-danger-soft)]",
    };
  if (Object.keys(element.outputs).length)
    return {
      label: "已有产物",
      tone: "text-[var(--color-success)] bg-[var(--color-success-soft)]",
    };
  return {
    label: "可编辑",
    tone: "text-[var(--color-text-secondary)] bg-[var(--color-bg-secondary)]",
  };
}

function sec(tick: number, ticksPerSecond: number): number {
  return Number((tick / ticksPerSecond).toFixed(3));
}

export default function ElementDetail({
  project,
  timeline,
  element,
  tasks,
  patching,
  onClose,
  onPatch,
  onDelete,
  onAgent,
}: ElementDetailProps) {
  const outputs = useMemo(
    () => (element ? resolveElementOutputs(project, element) : []),
    [element, project],
  );

  if (!element) {
    return (
      <section className="flex min-h-0 items-center justify-center overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-primary)] shadow-sm">
        <div className="max-w-sm px-8 text-center">
          <Layers3 className="mx-auto mb-3 h-8 w-8 text-[var(--color-text-tertiary)]" />
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
            选择一个 Element
          </h3>
          <p className="mt-2 text-xs leading-5 text-[var(--color-text-secondary)]">
            可从左侧列表或上方时间轴选择，查看其简介、创作方式、位置和产物。
          </p>
        </div>
      </section>
    );
  }

  const meta = ELEMENT_TYPE_META[element.creation.type];
  const status = taskStatus(element, tasks);
  const baseSegments = [
    "timelines",
    "items",
    timeline.timeline_id,
    "elements_by_id",
    element.element_id,
  ] as const;
  const pointer = (...segments: Array<string | number>) =>
    projectJsonPointer(...baseSegments, ...segments);
  const patch = (
    segments: Array<string | number>,
    before: unknown,
    value: unknown,
  ) =>
    onPatch(pointer(...segments), before, value).catch((error) => {
      message.error((error as Error).message);
      throw error;
    });
  const creation = element.creation;

  return (
    <section
      data-element-detail={element.element_id}
      className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-primary)] shadow-sm"
    >
      <header className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
              style={{ color: meta.color, background: meta.soft }}
            >
              {meta.label}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.tone}`}
            >
              {status.label}
            </span>
            {!element.enabled && (
              <span className="rounded-full bg-[var(--color-bg-secondary)] px-2 py-0.5 text-[10px] text-[var(--color-text-tertiary)]">
                已停用
              </span>
            )}
          </div>
          <h3 className="mt-2 truncate text-base font-semibold text-[var(--color-text-primary)]">
            {element.label || element.element_id}
          </h3>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-secondary)]">
            {elementCreationSummary(creation) || "尚未补充创作说明"}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="icon-button shrink-0"
          aria-label="关闭 Element 详情"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 [scrollbar-gutter:stable]">
        <section className="rounded-xl border border-[var(--color-border)] p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h4 className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-primary)]">
              <Clock3 className="h-3.5 w-3.5 text-[var(--color-accent)]" />
              时间与层级
            </h4>
            <label className="flex items-center gap-2 text-[11px] text-[var(--color-text-secondary)]">
              启用
              <Switch
                size="small"
                checked={element.enabled}
                loading={patching}
                onChange={(checked) =>
                  void patch(["enabled"], element.enabled, checked)
                }
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <label>
              <FieldLabel>开始时间（秒）</FieldLabel>
              <InputNumber
                className="w-full"
                min={0}
                step={0.1}
                value={sec(element.span.start_tick, timeline.ticks_per_second)}
                onChange={(value) => {
                  if (value == null) return;
                  void patch(
                    ["span", "start_tick"],
                    element.span.start_tick,
                    Math.round(Number(value) * timeline.ticks_per_second),
                  );
                }}
              />
            </label>
            <label>
              <FieldLabel>持续时间（秒）</FieldLabel>
              <InputNumber
                className="w-full"
                min={1 / timeline.ticks_per_second}
                step={0.1}
                value={sec(
                  element.span.duration_tick,
                  timeline.ticks_per_second,
                )}
                onChange={(value) => {
                  if (value == null) return;
                  void patch(
                    ["span", "duration_tick"],
                    element.span.duration_tick,
                    Math.max(
                      1,
                      Math.round(Number(value) * timeline.ticks_per_second),
                    ),
                  );
                }}
              />
            </label>
            <label>
              <FieldLabel>Z Index</FieldLabel>
              <InputNumber
                className="w-full"
                value={element.z_index}
                onChange={(value) =>
                  value != null &&
                  void patch(["z_index"], element.z_index, Number(value))
                }
              />
            </label>
            <div>
              <FieldLabel>Element ID</FieldLabel>
              <div className="truncate rounded-md bg-[var(--color-bg-secondary)] px-2.5 py-[7px] font-mono text-[11px] text-[var(--color-text-secondary)]">
                {element.element_id}
              </div>
            </div>
          </div>
          <div className="mt-3">
            <TextField
              label="名称"
              value={element.label}
              path={pointer("label")}
              field={`element:${element.element_id}/label`}
              onCommit={(value) => patch(["label"], element.label, value)}
            />
          </div>
        </section>

        {element.location && (
          <section className="rounded-xl border border-[var(--color-border)] p-3">
            <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-primary)]">
              <Box className="h-3.5 w-3.5 text-[var(--color-accent)]" />
              成片画面位置
            </h4>
            <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
              <div className="flex min-h-40 items-center justify-center rounded-lg bg-[#191613] p-3">
                <div
                  className="relative max-h-36 w-full overflow-hidden rounded border border-white/15 bg-[#312b26]"
                  style={{
                    aspectRatio: project.settings.aspect_ratio.replace(
                      ":",
                      " / ",
                    ),
                  }}
                >
                  <div
                    className="absolute flex items-center justify-center overflow-hidden rounded border border-white/80 bg-[var(--color-accent)]/35 text-[9px] font-semibold text-white"
                    style={{
                      left: `${
                        (element.location.x -
                          element.location.width * element.location.anchor_x) *
                        100
                      }%`,
                      top: `${
                        (element.location.y -
                          element.location.height * element.location.anchor_y) *
                        100
                      }%`,
                      width: `${element.location.width * 100}%`,
                      height: `${element.location.height * 100}%`,
                      opacity: element.location.opacity,
                      transform: `rotate(${element.location.rotation_degrees}deg)`,
                    }}
                  >
                    {element.label || element.element_id}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {(
                  [
                    "x",
                    "y",
                    "width",
                    "height",
                    "rotation_degrees",
                    "opacity",
                  ] as const
                ).map((key) => (
                  <label key={key}>
                    <FieldLabel>
                      {key === "rotation_degrees" ? "rotation" : key}
                    </FieldLabel>
                    <InputNumber
                      className="w-full"
                      step={key === "rotation_degrees" ? 1 : 0.05}
                      min={key === "opacity" ? 0 : undefined}
                      max={key === "opacity" ? 1 : undefined}
                      value={element.location![key]}
                      onChange={(value) =>
                        value != null &&
                        void patch(
                          ["location", key],
                          element.location![key],
                          Number(value),
                        )
                      }
                    />
                  </label>
                ))}
              </div>
            </div>
          </section>
        )}

        <section className="rounded-xl border border-[var(--color-border)] p-3">
          <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-primary)]">
            <Sparkles className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            创作内容
          </h4>
          {creation.type === "r2v" && (
            <div className="space-y-3">
              <TextField
                label="创作意图"
                value={creation.intent}
                multiline
                path={pointer("creation", "intent")}
                field={`element:${element.element_id}/creation/intent`}
                onCommit={(value) =>
                  patch(["creation", "intent"], creation.intent, value)
                }
              />
              <TextField
                label="叙事"
                value={creation.narrative}
                multiline
                path={pointer("creation", "narrative")}
                field={`element:${element.element_id}/creation/narrative`}
                onCommit={(value) =>
                  patch(["creation", "narrative"], creation.narrative, value)
                }
              />
              <TextField
                label="分镜 Prompt"
                value={creation.storyboard_prompt}
                multiline
                path={pointer("creation", "storyboard_prompt")}
                field={`element:${element.element_id}/creation/storyboard_prompt`}
                onCommit={(value) =>
                  patch(
                    ["creation", "storyboard_prompt"],
                    creation.storyboard_prompt,
                    value,
                  )
                }
              />
              <TextField
                label="视频 Prompt"
                value={creation.video_prompt}
                multiline
                path={pointer("creation", "video_prompt")}
                field={`element:${element.element_id}/creation/video_prompt`}
                onCommit={(value) =>
                  patch(
                    ["creation", "video_prompt"],
                    creation.video_prompt,
                    value,
                  )
                }
              />
              {creation.shots.order.length > 0 && (
                <div>
                  <FieldLabel>分镜</FieldLabel>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {creation.shots.order.map((shotId, index) => {
                      const shot = creation.shots.items[shotId];
                      if (!shot) return null;
                      return (
                        <div
                          key={shotId}
                          className="rounded-lg bg-[var(--color-bg-secondary)] p-2.5 text-[11px] leading-5 text-[var(--color-text-secondary)]"
                        >
                          <b className="text-[var(--color-text-primary)]">
                            {String(index + 1).padStart(2, "0")} ·{" "}
                            {shot.camera || "镜头"}
                          </b>
                          <p>{shot.description}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
          {creation.type === "edit" && (
            <div className="space-y-3">
              <TextField
                label="剪辑意图"
                value={creation.intent}
                multiline
                path={pointer("creation", "intent")}
                field={`element:${element.element_id}/creation/intent`}
                onCommit={(value) =>
                  patch(["creation", "intent"], creation.intent, value)
                }
              />
              <TextField
                label="选择理由"
                value={creation.reason}
                multiline
                path={pointer("creation", "reason")}
                field={`element:${element.element_id}/creation/reason`}
                onCommit={(value) =>
                  patch(["creation", "reason"], creation.reason, value)
                }
              />
              {element.render_source?.type === "source_asset_version" && (
                <div className="rounded-lg bg-[var(--color-bg-secondary)] p-3 font-mono text-[11px] text-[var(--color-text-secondary)]">
                  素材版本 {element.render_source.version_id}
                  <br />
                  范围 [{element.render_source.source_in_tick},{" "}
                  {element.render_source.source_out_tick ?? "end"}) ·{" "}
                  {element.render_source.playback_rate}x
                </div>
              )}
            </div>
          )}
          {creation.type === "overlay" && (
            <div className="space-y-3">
              <TextField
                label="文本"
                value={creation.text}
                multiline
                path={pointer("creation", "text")}
                field={`element:${element.element_id}/creation/text`}
                onCommit={(value) =>
                  patch(["creation", "text"], creation.text, value)
                }
              />
              <TextField
                label="动效 Prompt"
                value={creation.prompt}
                multiline
                path={pointer("creation", "prompt")}
                field={`element:${element.element_id}/creation/prompt`}
                onCommit={(value) =>
                  patch(["creation", "prompt"], creation.prompt, value)
                }
              />
            </div>
          )}
          {creation.type === "transition" && (
            <div className="rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs text-[var(--color-text-secondary)]">
              {creation.from_element_id} → {creation.to_element_id}
              <br />
              {creation.transition_kind} · {creation.easing}
            </div>
          )}
          {creation.type === "audio" && (
            <div className="rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs text-[var(--color-text-secondary)]">
              素材版本：{creation.source_asset_version_id}
              <br />
              Gain {creation.gain_db} dB · Pan {creation.pan}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-[var(--color-border)] p-3">
          <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-primary)]">
            <Film className="h-3.5 w-3.5 text-[var(--color-accent)]" />
            具名输出
          </h4>
          {outputs.length === 0 ? (
            <p className="rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs text-[var(--color-text-tertiary)]">
              当前还没有具名输出。
            </p>
          ) : (
            <div className="space-y-3">
              {outputs.map((output) => {
                const file = output.selected
                  ? project.assets.files_by_id[output.selected.file_id]
                  : null;
                const mediaType = file?.media_type || "";
                const url = output.selected
                  ? getArtifactVersionMediaUrl(output.selected.version_id)
                  : null;
                return (
                  <div
                    key={output.name}
                    className="overflow-hidden rounded-lg border border-[var(--color-border)]"
                  >
                    <div className="flex items-center justify-between gap-2 bg-[var(--color-bg-secondary)] px-3 py-2 text-[11px]">
                      <b>{output.name}</b>
                      <span className="truncate font-mono text-[var(--color-text-tertiary)]">
                        {output.selected?.version_id || "未产出"}
                      </span>
                    </div>
                    {url && mediaType.startsWith("image/") && (
                      <img
                        src={url}
                        alt={`${output.name} 输出`}
                        className="max-h-56 w-full bg-black object-contain"
                      />
                    )}
                    {url && mediaType.startsWith("video/") && (
                      <video
                        src={url}
                        controls
                        preload="metadata"
                        className="max-h-64 w-full bg-black object-contain"
                      />
                    )}
                    {url && mediaType.startsWith("audio/") && (
                      <audio src={url} controls className="w-full p-3" />
                    )}
                    {output.selected?.stale && (
                      <p className="px-3 py-2 text-[10px] text-[var(--color-warning)]">
                        该产物基于旧版 Project，需要重新生成。
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border)] bg-[var(--color-bg-primary)] px-4 py-3">
        <Button
          danger
          icon={<Trash2 className="h-3.5 w-3.5" />}
          onClick={() =>
            Modal.confirm({
              title: "删除 Element？",
              content: `将从 Timeline 中删除「${
                element.label || element.element_id
              }」。`,
              okText: "删除",
              okButtonProps: { danger: true },
              onOk: () => onDelete(element),
            })
          }
        >
          删除
        </Button>
        <div className="flex gap-2">
          {creation.type === "r2v" && (
            <Button
              icon={<ArrowUpRight className="h-3.5 w-3.5" />}
              onClick={() =>
                onAgent(
                  element,
                  "请继续完成这个 R2V Element 的分镜和视频生成。",
                )
              }
            >
              继续制作
            </Button>
          )}
          <Button
            type="primary"
            icon={<Sparkles className="h-3.5 w-3.5" />}
            onClick={() => onAgent(element)}
          >
            在 Agent 中修改
          </Button>
        </div>
      </footer>
    </section>
  );
}
