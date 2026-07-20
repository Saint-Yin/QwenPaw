import type {
  IntegrationPreview,
  MediaComparison,
  ReviewDecisionGroup,
  ReviewMediaVersion,
  ReviewOperation,
} from '@/contracts/creator';
import { reviewFieldForOperation } from './ReviewFieldText';

export interface ReviewNavigationTarget {
  locator: Record<string, string>;
  field?: string;
  targetRef: string | null;
}

function locatorForSemanticField(field: string, fallback: Record<string, string>): Record<string, string> {
  const shot = /^unit:([^/]+)\/shot:[^/]+\//.exec(field);
  if (shot) return { page: 'plan', unitId: shot[1] };
  const unit = /^unit:([^/]+)\//.exec(field);
  if (unit) return { page: 'plan', unitId: unit[1] };
  const section = /^section:([^/]+)\//.exec(field);
  if (section) return { page: 'plan', sectionId: section[1] };
  return fallback;
}

function focusForMedia(version?: ReviewMediaVersion | null): string | undefined {
  const kind = version?.artifactKind?.toLowerCase() ?? '';
  if (kind.includes('storyboard') || version?.mediaType === 'image') return 'storyboard';
  if (version?.mediaType === 'video') return 'video';
  return undefined;
}

function intersects(operationIds: Set<string>, values: string[]): boolean {
  return values.some((value) => operationIds.has(value));
}

/**
 * Resolve the front-end object represented by a review group.
 *
 * A group can contain dependency/support operations from several surfaces.
 * Navigation must therefore prefer a visible semantic field, or the selected
 * media version, instead of whichever immutable operation happened to be
 * serialized first.
 */
export function resolveReviewNavigationTarget({
  group,
  operations,
  mediaComparisons = [],
  integrationPreviews = [],
}: {
  group: ReviewDecisionGroup;
  operations: ReviewOperation[];
  mediaComparisons?: MediaComparison[];
  integrationPreviews?: IntegrationPreview[];
}): ReviewNavigationTarget | null {
  const groupOperationIds = new Set(group.operationIds);
  const groupOperations = operations.filter((operation) => groupOperationIds.has(operation.id));
  const integration = integrationPreviews.find((item) => intersects(groupOperationIds, item.operationIds));
  const comparison = mediaComparisons.find((item) => intersects(groupOperationIds, item.operationIds));
  const version = integration?.after
    ?? comparison?.after
    ?? comparison?.before
    ?? comparison?.candidates[0];

  if (integration?.uiLocator) {
    return {
      locator: {
        ...integration.uiLocator,
        ...(version?.versionId ? { versionId: version.versionId } : {}),
        ...(!integration.uiLocator.focus && focusForMedia(version)
          ? { focus: focusForMedia(version)! }
          : {}),
      },
      targetRef: integration.targetRef,
    };
  }

  const semanticOperation = groupOperations.find((operation) => (
    Boolean(operation.uiLocator) && Boolean(reviewFieldForOperation(operation))
  ));
  if (semanticOperation?.uiLocator) {
    const field = reviewFieldForOperation(semanticOperation);
    return {
      locator: field
        ? locatorForSemanticField(field, semanticOperation.uiLocator)
        : semanticOperation.uiLocator,
      field: field ?? undefined,
      targetRef: field?.split('/', 1)[0] ?? semanticOperation.targetRef,
    };
  }

  const mediaOperation = groupOperations.find((operation) => (
    Boolean(operation.uiLocator)
    && (comparison?.operationIds.includes(operation.id)
      || ['image', 'video'].includes(operation.artifactKind))
  ));
  if (mediaOperation?.uiLocator) {
    return {
      locator: {
        ...mediaOperation.uiLocator,
        ...(version?.versionId ? { versionId: version.versionId } : {}),
        ...(!mediaOperation.uiLocator.focus && focusForMedia(version)
          ? { focus: focusForMedia(version)! }
          : {}),
      },
      targetRef: mediaOperation.targetRef,
    };
  }

  const fallback = groupOperations.find((operation) => operation.uiLocator);
  if (!fallback?.uiLocator) return null;
  return {
    locator: fallback.uiLocator,
    field: reviewFieldForOperation(fallback) ?? fallback.uiLocator.field,
    targetRef: fallback.targetRef,
  };
}
