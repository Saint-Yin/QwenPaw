import { Component, useCallback, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import type {
  EditWorkbenchView,
  R2VWorkbenchView,
  RefSearchItem,
  ViewEnvelope,
} from "@/contracts/creator";
import { useParams, useRouter, useSearchParams } from "@/routing/navigation";
import {
  presentationOf,
  useWorkspaceViewStore,
} from "@/store/workspaceViewStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";
import PageSkeleton from "@/components/PageSkeleton";
import R2VWorkbench from "@/components/workbench/R2VWorkbench";
import AiEditWorkbench from "@/components/workbench/AiEditWorkbench";
import { useReviewFieldFocus } from "@/routing/reviewFocus";
import PageLoadError from "@/components/PageLoadError";

class WorkbenchErrorBoundary extends Component<
  { children: ReactNode },
  { error: string | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: unknown) {
    const message =
      error instanceof Error
        ? `${error.name}: ${error.message}\n${error.stack ?? ""}`
        : String(error);
    return { error: message };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-full overflow-y-auto bg-[var(--color-warning-soft)] p-6 font-mono text-xs text-[var(--color-warning)]">
          <strong className="text-sm">Workbench render error:</strong>
          <pre className="mt-3 whitespace-pre-wrap">{this.state.error}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function unitTermForScenario(scenario?: string): string {
  if (scenario === "short_drama") return "Clip";
  if (scenario === "video_edit") return "剪辑片段";
  return "生成单元";
}

function isRefSearchItem(
  value: RefSearchItem | null | undefined,
): value is RefSearchItem {
  return value != null;
}

export default function UnitWorkbenchPage() {
  const { id = "", unitId = "" } = useParams();
  const router = useRouter();
  const query = useSearchParams();
  const envelope = useWorkspaceViewStore((state) => state.workbenches[unitId]);
  const planEnvelope = useWorkspaceViewStore((state) => state.plan);
  const headerEnvelope = useWorkspaceViewStore((state) => state.header);
  const assetsEnvelope = useWorkspaceViewStore((state) => state.assets);
  const loadWorkbench = useWorkspaceViewStore((state) => state.loadWorkbench);
  const loadPlan = useWorkspaceViewStore((state) => state.loadPlan);
  const loadAssets = useWorkspaceViewStore((state) => state.loadAssets);
  const events = useCreatorSessionStore((state) => state.events);
  const view = presentationOf(envelope || null);
  const plan = presentationOf(planEnvelope);
  const header = presentationOf(headerEnvelope);
  const assets = presentationOf(assetsEnvelope);
  const error = useWorkspaceViewStore(
    (state) => state.errors[`workbench:${unitId}`],
  );
  const focusVersion = query.get("version");
  const reviewField = query.get("field");
  const reviewEnabled = query.get("review") === "1";
  const reviewFocus =
    reviewEnabled &&
    (query.get("focus") === "storyboard" || query.get("focus") === "video")
      ? (query.get("focus") as "storyboard" | "video")
      : null;
  const pulse = query.get("reviewPulse");
  const lastViewSeq = [...events]
    .reverse()
    .find(
      (event) =>
        event.type === "workspace.head_changed" ||
        [
          "task.completed",
          "task.failed",
          "task.quarantined",
          "subagent.completed",
        ].includes(event.type),
    )?.seq;

  useEffect(() => {
    const requests: Array<Promise<void>> = [
      loadAssets(id),
      loadWorkbench(id, unitId),
    ];
    // ProjectLayout owns the initial Header + Plan bootstrap.  A semantic
    // workspace/task event is the only reason this mounted workbench needs to
    // refresh Plan metadata itself.
    if (lastViewSeq != null) requests.push(loadPlan(id));
    void Promise.allSettled(requests);
  }, [id, lastViewSeq, loadAssets, loadPlan, loadWorkbench, unitId]);

  useEffect(() => {
    useCreatorInteractionStore.getState().select(`unit:${unitId}`);
  }, [unitId]);

  useReviewFieldFocus({
    path: `/project/${id}/plan/unit/${unitId}/workbench`,
    field: reviewField,
    enabled: reviewEnabled,
    pulse,
  });

  const lastPulse = useRef<string | null>(null);
  useEffect(() => {
    if (!focusVersion) return;
    const focusKey = `${focusVersion}:${pulse || "direct"}`;
    if (focusKey === lastPulse.current) return;
    const target = document.querySelector<HTMLElement>(
      `[data-artifact-version="${CSS.escape(focusVersion)}"]`,
    );
    if (!target) return;
    lastPulse.current = focusKey;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.remove("review-flash");
    void target.offsetWidth;
    target.classList.add("review-flash");
  }, [focusVersion, pulse, view]);

  const locatedSection = useMemo(
    () =>
      plan?.sections.find((section) =>
        section.units.some((unit) => unit.id === unitId),
      ),
    [plan, unitId],
  );
  const locatedUnit = useMemo(
    () => locatedSection?.units.find((unit) => unit.id === unitId),
    [locatedSection, unitId],
  );
  const displayView = useMemo(
    () =>
      view && locatedUnit
        ? {
            ...view,
            unit: {
              ...view.unit,
              number: locatedUnit.number,
              title: locatedUnit.title,
            },
          }
        : view,
    [locatedUnit, view],
  );
  const availableAssetRefs = useMemo<
    Array<RefSearchItem & { mediaType?: string }>
  >(() => {
    if (!assets) return [];
    const logicalAssets = new Map(
      assets.availableAssets.map((asset) => [asset.assetId, asset]),
    );
    return [...logicalAssets.values()].map((asset) => ({
      ref: asset.sourceRef,
      name: asset.name,
      type: "asset",
      version: asset.assetVersionId,
      thumbnailUrl: asset.thumbnailUrl,
      mediaType: asset.mediaType,
      uiLocator: asset.uiLocator,
    }));
  }, [assets]);
  const referenceOptions = useMemo(
    () => ({
      scene: (assets?.visualAssets ?? [])
        .filter((asset) => asset.category === "scene")
        .map((asset) => asset.resolvedRef)
        .filter(isRefSearchItem),
      characters: (assets?.visualAssets ?? [])
        .filter((asset) => asset.category === "character")
        .map((asset) => asset.resolvedRef)
        .filter(isRefSearchItem),
      props: (assets?.visualAssets ?? [])
        .filter((asset) => asset.category === "prop")
        .map((asset) => asset.resolvedRef)
        .filter(isRefSearchItem),
      sources: availableAssetRefs,
    }),
    [assets, availableAssetRefs],
  );
  const materialReferenceOptions = useMemo(
    () => availableAssetRefs.filter((asset) => asset.mediaType === "video"),
    [availableAssetRefs],
  );
  const onBack = useCallback(
    () => router.push(`/project/${id}/plan?unit=${encodeURIComponent(unitId)}`),
    [id, router, unitId],
  );
  const reload = useCallback(
    () => loadWorkbench(id, unitId),
    [id, loadWorkbench, unitId],
  );

  if (error && !view) {
    return (
      <PageLoadError
        message={error}
        retry={() => void loadWorkbench(id, unitId)}
      />
    );
  }
  if (!envelope || !view || !plan || !header || !assets)
    return <PageSkeleton type="editor" />;

  const typedEnvelope = envelope as ViewEnvelope<
    R2VWorkbenchView | EditWorkbenchView
  >;

  return (
    <WorkbenchErrorBoundary>
      {displayView.kind === "r2v" ? (
        <R2VWorkbench
          projectId={id}
          envelope={typedEnvelope as ViewEnvelope<R2VWorkbenchView>}
          view={displayView}
          reload={reload}
          focusVersion={focusVersion}
          reviewFocus={reviewFocus}
          sectionNumber={locatedSection?.number}
          sectionTitle={locatedSection?.title}
          sectionId={locatedSection?.id}
          aspectRatio={plan?.aspectRatio || header?.aspectRatio}
          unitTerm={unitTermForScenario(header?.scenario)}
          referenceOptions={referenceOptions}
          onBack={onBack}
        />
      ) : (
        <AiEditWorkbench
          projectId={id}
          envelope={typedEnvelope as ViewEnvelope<EditWorkbenchView>}
          view={displayView}
          reload={reload}
          focusVersion={focusVersion}
          reviewFocus={reviewFocus}
          sectionNumber={locatedSection?.number}
          sectionTitle={locatedSection?.title}
          materialReferenceOptions={materialReferenceOptions}
          onBack={onBack}
        />
      )}
    </WorkbenchErrorBoundary>
  );
}
