import type {
  AssetLibraryView,
  ComposeView,
  EditWorkbenchView,
  PlanView,
  ProjectHeaderView,
  R2VWorkbenchView,
  SectionView,
  ViewEnvelope,
} from "@/contracts/creator";
import { creatorRequest } from "./client";

const project = (id: string) => `/projects/${encodeURIComponent(id)}`;

export function getHeaderView(
  projectId: string,
): Promise<ViewEnvelope<ProjectHeaderView>> {
  return creatorRequest(`${project(projectId)}/header`);
}

export function getPlanView(
  projectId: string,
): Promise<ViewEnvelope<PlanView>> {
  return creatorRequest(`${project(projectId)}/plan`);
}

export function getSectionView(
  projectId: string,
  sectionId: string,
): Promise<ViewEnvelope<SectionView>> {
  return creatorRequest(
    `${project(projectId)}/sections/${encodeURIComponent(sectionId)}`,
  );
}

export function getWorkbenchView(
  projectId: string,
  unitId: string,
): Promise<ViewEnvelope<R2VWorkbenchView | EditWorkbenchView>> {
  return creatorRequest(
    `${project(projectId)}/units/${encodeURIComponent(unitId)}/workbench`,
  );
}

export function getAssetView(
  projectId: string,
): Promise<ViewEnvelope<AssetLibraryView>> {
  return creatorRequest(`${project(projectId)}/assets`);
}

export function getSectionComposeView(
  projectId: string,
  sectionId: string,
): Promise<ViewEnvelope<ComposeView>> {
  return creatorRequest(
    `${project(projectId)}/post/sections/${encodeURIComponent(sectionId)}`,
  );
}

export function getFinalComposeView(
  projectId: string,
): Promise<ViewEnvelope<ComposeView>> {
  return creatorRequest(`${project(projectId)}/post/final`);
}

export function getHistoricalView<T>(
  projectId: string,
  revisionId: string,
  viewName: string,
): Promise<ViewEnvelope<T>> {
  return creatorRequest(
    `${project(projectId)}/revisions/${encodeURIComponent(
      revisionId,
    )}/${encodeURIComponent(viewName)}`,
  );
}
