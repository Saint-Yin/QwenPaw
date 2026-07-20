import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "@/routing/navigation";
import {
  presentationOf,
  useWorkspaceViewStore,
} from "@/store/workspaceViewStore";
import PageSkeleton from "@/components/PageSkeleton";
import ComposeWorkspace from "@/components/plan/ComposeWorkspace";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import PageLoadError from "@/components/PageLoadError";
import { useReviewFieldFocus } from "@/routing/reviewFocus";

export default function SectionComposePage() {
  const { id = "", sectionId = "" } = useParams();
  const router = useRouter();
  const query = useSearchParams();
  const envelope = useWorkspaceViewStore(
    (state) => state.sectionCompose[sectionId],
  );
  const load = useWorkspaceViewStore((state) => state.loadSectionCompose);
  const view = presentationOf(envelope || null);
  const error = useWorkspaceViewStore(
    (state) => state.errors[`section-compose:${sectionId}`],
  );
  const events = useCreatorSessionStore((state) => state.events);
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
    void load(id, sectionId).catch(() => undefined);
  }, [id, load, sectionId, lastViewSeq]);
  const review = query.get("review") === "1";
  const reviewField = query.get("field");
  const reviewPulse = query.get("reviewPulse");
  useReviewFieldFocus({
    path: `/project/${id}/plan/section/${sectionId}`,
    field: reviewField,
    enabled: review,
    pulse: reviewPulse,
  });
  if (error && !view)
    return (
      <PageLoadError message={error} retry={() => void load(id, sectionId)} />
    );
  if (!envelope || !view) return <PageSkeleton type="list" />;
  return (
    <ComposeWorkspace
      projectId={id}
      envelope={envelope}
      view={view}
      reload={() => load(id, sectionId)}
      onClose={() => router.push(`/project/${id}/plan?section=${sectionId}`)}
      focusVersion={query.get("version")}
      focusPulse={reviewPulse}
    />
  );
}
