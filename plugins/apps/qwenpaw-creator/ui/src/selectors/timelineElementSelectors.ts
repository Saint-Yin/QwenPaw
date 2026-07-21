import type {
  ArtifactSlotDocument,
  ArtifactVersionDocument,
  ElementCreationDocument,
  ProjectDocument,
  TimelineDocument,
  TimelineElementDocument,
} from "@/contracts/creator";

export interface DisplayLane {
  id: string;
  elements: TimelineElementDocument[];
}

export interface ResolvedArtifactOutput {
  name: string;
  slot: ArtifactSlotDocument;
  selected: ArtifactVersionDocument | null;
}

export function selectPrimaryTimeline(
  project: ProjectDocument | null | undefined,
): TimelineDocument | null {
  if (!project) return null;
  const orderedId = project.timelines.order.find(
    (id) => project.timelines.items[id],
  );
  if (orderedId) return project.timelines.items[orderedId];
  return Object.values(project.timelines.items)[0] ?? null;
}

export function timelineEndTick(
  timeline: TimelineDocument | null | undefined,
): number {
  if (!timeline) return 0;
  return Object.values(timeline.elements_by_id).reduce(
    (end, element) =>
      element.enabled
        ? Math.max(end, element.span.start_tick + element.span.duration_tick)
        : end,
    0,
  );
}

export function orderedTimelineElements(
  timeline: TimelineDocument | null | undefined,
): TimelineElementDocument[] {
  if (!timeline) return [];
  return Object.values(timeline.elements_by_id).sort(
    (left, right) =>
      left.span.start_tick - right.span.start_tick ||
      right.z_index - left.z_index ||
      left.element_id.localeCompare(right.element_id),
  );
}

export function elementsAtTick(
  timeline: TimelineDocument | null | undefined,
  tick: number,
  includeDisabled = false,
): TimelineElementDocument[] {
  if (!timeline || !Number.isFinite(tick) || tick < 0) return [];
  return orderedTimelineElements(timeline).filter((element) => {
    const end = element.span.start_tick + element.span.duration_tick;
    return (
      (includeDisabled || element.enabled) &&
      element.span.start_tick <= tick &&
      tick < end
    );
  });
}

export function elementsOverlappingRange(
  timeline: TimelineDocument | null | undefined,
  startTick: number,
  endTick: number,
): TimelineElementDocument[] {
  if (!timeline || endTick <= startTick) return [];
  return orderedTimelineElements(timeline).filter(
    (element) =>
      element.enabled &&
      element.span.start_tick < endTick &&
      startTick < element.span.start_tick + element.span.duration_tick,
  );
}

/** Frontend-only lane packing. Lanes are not persisted Tracks. */
export function packDisplayLanes(
  timeline: TimelineDocument | null | undefined,
): DisplayLane[] {
  const lanes: Array<{ endTick: number; elements: TimelineElementDocument[] }> =
    [];
  orderedTimelineElements(timeline).forEach((element) => {
    const lane = lanes.find(
      (candidate) => candidate.endTick <= element.span.start_tick,
    );
    const endTick = element.span.start_tick + element.span.duration_tick;
    if (lane) {
      lane.elements.push(element);
      lane.endTick = endTick;
    } else {
      lanes.push({ endTick, elements: [element] });
    }
  });
  return lanes.map((lane, index) => ({
    id: `L${index + 1}`,
    elements: lane.elements,
  }));
}

export function selectedSlotVersion(
  project: ProjectDocument,
  slotId: string,
): ResolvedArtifactOutput | null {
  const slot = project.assets.artifact_slots_by_id[slotId];
  if (!slot) return null;
  return {
    name: slot.kind,
    slot,
    selected: slot.selected_version_id
      ? project.assets.artifact_versions_by_id[slot.selected_version_id] ?? null
      : null,
  };
}

export function resolveElementOutputs(
  project: ProjectDocument,
  element: TimelineElementDocument,
): ResolvedArtifactOutput[] {
  return Object.entries(element.outputs).map(([name, output]) => {
    const resolved = selectedSlotVersion(project, output.slot_id);
    return resolved
      ? { ...resolved, name }
      : {
          name,
          slot: {
            slot_id: output.slot_id,
            kind: name,
            owner_ref: `element:${element.element_id}`,
            version_ids: [],
            selected_version_id: null,
            metadata: {},
          },
          selected: null,
        };
  });
}

export function resolveTimelineRender(
  project: ProjectDocument,
  timeline: TimelineDocument,
): ResolvedArtifactOutput | null {
  return selectedSlotVersion(
    project,
    `timeline:${timeline.timeline_id}:render`,
  );
}

export function elementCreationSummary(
  creation: ElementCreationDocument,
): string {
  switch (creation.type) {
    case "r2v":
      return creation.narrative || creation.intent || creation.video_prompt;
    case "edit":
      return creation.intent || creation.reason;
    case "overlay":
      return creation.text || creation.prompt || creation.overlay_kind;
    case "transition":
      return `${creation.transition_kind} 转场`;
    case "audio":
      return "时间线音频";
  }
}

export const ELEMENT_TYPE_META: Record<
  ElementCreationDocument["type"],
  {
    label: string;
    color: string;
    soft: string;
  }
> = {
  r2v: { label: "AI 生成画面", color: "#ff7f16", soft: "rgba(255,127,22,.12)" },
  edit: { label: "素材剪辑", color: "#3b82f6", soft: "rgba(59,130,246,.12)" },
  overlay: {
    label: "字幕与动效",
    color: "#8b5cf6",
    soft: "rgba(139,92,246,.12)",
  },
  transition: {
    label: "转场",
    color: "#9a9188",
    soft: "rgba(154,145,136,.12)",
  },
  audio: { label: "音频", color: "#12b76a", soft: "rgba(18,183,106,.12)" },
};
