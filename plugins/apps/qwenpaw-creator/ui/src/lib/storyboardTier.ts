// Client mirror of the backend's three-tier storyboard triage
// (models/video_task_plans.r2v_continuity_storyboard_need). The backend
// stays authoritative for dispatch; this only drives overview copy and
// the "仍生成分镜" affordance, so keep the regexes and thresholds in
// lockstep with the Python original (tests pin both sides).
import type { ProjectDocument } from "@/contracts/creator/projectSnapshot";

export type StoryboardTier = "plain" | "none" | "combined";

const CAMERA =
  /(缓推|推近|推进|拉远|后拉|摇镜|横移|跟随|跟拍|环绕|升降|dolly|zoom|orbit|tracking)/;
const BEAT =
  /(随后|紧接着|然后|最后|起初|切到|cut to|\d+\s*秒[后内]|第[一二三四五六七八九十]\s*秒)/;
const PROP_STATE = /(撑开|收拢|合上|打开|关上|点亮|熄灭|点燃|收起|展开|拔出)/;
const CUT_KEYWORDS = [
  "切到",
  "切换到",
  "另一机位",
  "时间跳转",
  "回忆",
  "闪回",
  "转场到",
];

type AnyRecord = Record<string, any>;

function timelinesOf(project: ProjectDocument): AnyRecord[] {
  const timelines = (project as AnyRecord).timelines as AnyRecord;
  return Object.values(timelines.items ?? {}) as AnyRecord[];
}

function locate(
  project: ProjectDocument,
  elementId: string,
): { timeline: AnyRecord; element: AnyRecord } | null {
  for (const timeline of timelinesOf(project)) {
    const element = timeline?.elements_by_id?.[elementId];
    if (element) return { timeline, element };
  }
  return null;
}

function findPredecessor(
  timeline: AnyRecord,
  element: AnyRecord,
): AnyRecord | null {
  const targetTick = Number(element.span?.start_tick ?? 0);
  let bestKey: [number, string] | null = null;
  let best: AnyRecord | null = null;
  for (const [id, candidate] of Object.entries(
    timeline.elements_by_id ?? {},
  ) as [string, AnyRecord][]) {
    if (id === element.element_id) continue;
    if (candidate.enabled === false) continue;
    const type = candidate.creation?.type;
    if (type !== "r2v" && type !== "i2v") continue;
    const tick = Number(candidate.span?.start_tick ?? 0);
    if (tick >= targetTick) continue;
    if (tick + Number(candidate.span?.duration_tick ?? 0) > targetTick) {
      continue;
    }
    const key: [number, string] = [tick, id];
    if (
      bestKey === null ||
      key[0] > bestKey[0] ||
      (key[0] === bestKey[0] && key[1] > bestKey[1])
    ) {
      bestKey = key;
      best = candidate;
    }
  }
  return best;
}

function mayConsumePredecessor(
  timeline: AnyRecord,
  element: AnyRecord,
  prev: AnyRecord | null,
): boolean {
  if (!prev) return false;
  if (prev.creation?.scene_ref !== element.creation?.scene_ref) return false;
  const prevRefs = new Set<string>([
    ...(prev.creation?.character_refs ?? []),
    ...(prev.creation?.prop_refs ?? []),
  ]);
  const curRefs: string[] = [
    ...(element.creation?.character_refs ?? []),
    ...(element.creation?.prop_refs ?? []),
  ];
  if (curRefs.some((ref) => !prevRefs.has(ref))) return false;
  for (const item of Object.values(
    timeline.elements_by_id ?? {},
  ) as AnyRecord[]) {
    const creation = item.creation;
    if (
      creation?.type === "transition" &&
      creation.from_element_id === prev.element_id &&
      creation.to_element_id === element.element_id
    ) {
      return false;
    }
  }
  const text = String(element.creation?.continuity ?? "");
  if (CUT_KEYWORDS.some((keyword) => text.includes(keyword))) return false;
  return true;
}

function isComplex(timeline: AnyRecord, element: AnyRecord): boolean {
  const creation = element.creation ?? {};
  const ticksPerSecond = Math.max(Number(timeline.ticks_per_second ?? 10), 1);
  const seconds = Number(element.span?.duration_tick ?? 0) / ticksPerSecond;
  if (seconds > 8) return true;
  if ((creation.character_refs ?? []).length >= 2) return true;
  const text = `${creation.video_prompt ?? ""}\n${creation.narrative ?? ""}`;
  if (CAMERA.test(text)) return true;
  if (BEAT.test(text)) return true;
  if ((creation.prop_refs ?? []).length > 0 && PROP_STATE.test(text)) {
    return true;
  }
  return false;
}

/** Tier for one element; "plain" whenever the segment is not anchored. */
export function storyboardTierForElement(
  project: ProjectDocument,
  elementId: string,
): StoryboardTier {
  const found = locate(project, elementId);
  if (!found) return "plain";
  const { timeline, element } = found;
  if (element.creation?.type !== "r2v") return "plain";
  if (element.creation.force_storyboard) return "combined";
  const dial = (project as AnyRecord).settings?.video_continuity;
  if (dial === "throughput") return "plain";
  const prev = findPredecessor(timeline, element);
  if (!mayConsumePredecessor(timeline, element, prev)) return "plain";
  return isComplex(timeline, element) ? "combined" : "none";
}
