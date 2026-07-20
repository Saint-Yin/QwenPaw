import type {
  ArtifactVersionView,
  ReviewDecisionGroup,
  ReviewManifest,
} from "@/contracts/creator";

export type ArtifactPresentationStatus = "accepted" | "pending" | "stale";

export function reviewGroupForArtifactVersion(
  manifest: ReviewManifest | null,
  artifactVersionId: string | null | undefined,
  versionRef?: string | null,
): ReviewDecisionGroup | null {
  if (!manifest || !artifactVersionId) return null;
  const comparison = manifest.mediaComparisons.find(
    (item) =>
      item.after?.versionId === artifactVersionId ||
      (Boolean(versionRef) && item.after?.versionRef === versionRef) ||
      item.candidates.some(
        (candidate) =>
          candidate.versionId === artifactVersionId ||
          (Boolean(versionRef) && candidate.versionRef === versionRef),
      ),
  );
  if (!comparison) return null;
  const operationIds = new Set(comparison.operationIds);
  return (
    manifest.decisionGroups.find((group) =>
      group.operationIds.some((id) => operationIds.has(id)),
    ) ?? null
  );
}

export function reviewGroupForArtifact(
  manifest: ReviewManifest | null,
  artifact: ArtifactVersionView,
): ReviewDecisionGroup | null {
  if (!manifest) return null;
  const mediaGroup = reviewGroupForArtifactVersion(
    manifest,
    artifact.artifactVersionId,
    artifact.sourceRef,
  );
  if (mediaGroup) return mediaGroup;
  const operation = manifest.operations.find(
    (item) =>
      item.afterVersionRef === artifact.sourceRef ||
      item.id === artifact.reviewOperationId,
  );
  return operation
    ? manifest.decisionGroups.find(
        (group) => group.id === operation.decisionGroupId,
      ) ?? null
    : null;
}

export function artifactPresentationStatus(
  manifest: ReviewManifest | null,
  artifact: ArtifactVersionView,
): ArtifactPresentationStatus {
  const group = reviewGroupForArtifact(manifest, artifact);
  // Content review exists only after the transaction has sealed a Review
  // Manifest.  A merely unselected candidate (or an ACTIVE transaction) must
  // never be presented as something the user can review in AgentDock.
  if (!group)
    return artifact.freshnessStatus === "stale" ? "stale" : "accepted";
  if (group.decision === "PENDING" || group.decision === "REVISION_REQUESTED")
    return "pending";
  if (
    group?.decision === "REJECTED" ||
    group?.decision === "SUPERSEDED_BY_USER_EDIT"
  )
    return "stale";
  return "accepted";
}
