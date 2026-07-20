import { create } from "zustand";
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
import {
  getAssetView,
  getFinalComposeView,
  getHeaderView,
  getPlanView,
  getSectionComposeView,
  getSectionView,
  getWorkbenchView,
} from "@/api/creator";

export function presentationOf<T>(envelope: ViewEnvelope<T> | null): T | null {
  if (!envelope) return null;
  const candidate = envelope.view as
    | T
    | { presentationVersion: string; view: T };
  return candidate &&
    typeof candidate === "object" &&
    "presentationVersion" in candidate
    ? candidate.view
    : (candidate as T);
}

interface WorkspaceViewState {
  projectId: string | null;
  header: ViewEnvelope<ProjectHeaderView> | null;
  plan: ViewEnvelope<PlanView> | null;
  sections: Record<string, ViewEnvelope<SectionView>>;
  workbenches: Record<
    string,
    ViewEnvelope<R2VWorkbenchView | EditWorkbenchView>
  >;
  assets: ViewEnvelope<AssetLibraryView> | null;
  sectionCompose: Record<string, ViewEnvelope<ComposeView>>;
  finalCompose: ViewEnvelope<ComposeView> | null;
  loading: Record<string, boolean>;
  errors: Record<string, string>;
  clipHighlights: Record<string, string[]>;
  reset: (projectId?: string) => void;
  loadHeader: (projectId: string) => Promise<void>;
  loadPlan: (projectId: string) => Promise<void>;
  loadSection: (projectId: string, sectionId: string) => Promise<void>;
  loadWorkbench: (projectId: string, unitId: string) => Promise<void>;
  loadAssets: (projectId: string) => Promise<void>;
  loadSectionCompose: (projectId: string, sectionId: string) => Promise<void>;
  loadFinalCompose: (projectId: string) => Promise<void>;
  revalidateLoaded: (projectId: string) => Promise<void>;
  setClipHighlights: (unitId: string, clipIds: string[]) => void;
  clearClipHighlights: (unitId: string) => void;
  invalidate: (keys?: string[]) => void;
}

const base = (projectId: string | null = null) => ({
  projectId,
  header: null,
  plan: null,
  sections: {},
  workbenches: {},
  assets: null,
  sectionCompose: {},
  finalCompose: null,
  loading: {},
  errors: {},
  clipHighlights: {} as Record<string, string[]>,
});

interface WorkspaceRequestToken {
  epoch: number;
  requestId: number;
  projectId: string;
  key: string;
}

export const useWorkspaceViewStore = create<WorkspaceViewState>((set, get) => {
  let projectEpoch = 0;
  let nextRequestId = 0;
  const latestRequestByKey = new Map<string, number>();

  const resetProject = (projectId: string | null) => {
    projectEpoch += 1;
    latestRequestByKey.clear();
    set(base(projectId));
  };

  const ensureProject = (projectId: string) => {
    if (get().projectId !== projectId) resetProject(projectId);
  };

  const beginRequest = (
    projectId: string,
    key: string,
  ): WorkspaceRequestToken => {
    ensureProject(projectId);
    const requestId = ++nextRequestId;
    latestRequestByKey.set(key, requestId);
    const token = { epoch: projectEpoch, requestId, projectId, key };
    set((state) =>
      state.projectId === projectId
        ? {
            loading: { ...state.loading, [key]: true },
            errors: { ...state.errors, [key]: "" },
          }
        : {},
    );
    return token;
  };

  const isCurrent = (token: WorkspaceRequestToken, state = get()) =>
    token.epoch === projectEpoch &&
    latestRequestByKey.get(token.key) === token.requestId &&
    state.projectId === token.projectId;

  const loadView = async <T>(
    projectId: string,
    key: string,
    request: () => Promise<ViewEnvelope<T>>,
    commit: (
      state: WorkspaceViewState,
      result: ViewEnvelope<T>,
    ) => Partial<WorkspaceViewState>,
  ): Promise<void> => {
    const token = beginRequest(projectId, key);
    try {
      const result = await request();
      if (result.projectId !== projectId) {
        throw new Error(
          `View project mismatch: expected ${projectId}, received ${result.projectId}`,
        );
      }
      set((state) =>
        isCurrent(token, state)
          ? {
              ...commit(state, result),
              loading: { ...state.loading, [key]: false },
            }
          : {},
      );
    } catch (error) {
      set((state) =>
        isCurrent(token, state)
          ? {
              loading: { ...state.loading, [key]: false },
              errors: { ...state.errors, [key]: (error as Error).message },
            }
          : {},
      );
      throw error;
    }
  };

  return {
    ...base(),
    reset: (projectId = null) => resetProject(projectId),
    loadHeader: (projectId) =>
      loadView(
        projectId,
        "header",
        () => getHeaderView(projectId),
        (_state, result) => ({ header: result }),
      ),
    loadPlan: (projectId) =>
      loadView(
        projectId,
        "plan",
        () => getPlanView(projectId),
        (_state, result) => ({ plan: result }),
      ),
    loadSection: (projectId, sectionId) =>
      loadView(
        projectId,
        `section:${sectionId}`,
        () => getSectionView(projectId, sectionId),
        (state, result) => ({
          sections: { ...state.sections, [sectionId]: result },
        }),
      ),
    loadWorkbench: (projectId, unitId) =>
      loadView(
        projectId,
        `workbench:${unitId}`,
        () => getWorkbenchView(projectId, unitId),
        (state, result) => ({
          workbenches: { ...state.workbenches, [unitId]: result },
        }),
      ),
    loadAssets: (projectId) =>
      loadView(
        projectId,
        "assets",
        () => getAssetView(projectId),
        (_state, result) => ({ assets: result }),
      ),
    loadSectionCompose: (projectId, sectionId) =>
      loadView(
        projectId,
        `section-compose:${sectionId}`,
        () => getSectionComposeView(projectId, sectionId),
        (state, result) => ({
          sectionCompose: { ...state.sectionCompose, [sectionId]: result },
        }),
      ),
    loadFinalCompose: (projectId) =>
      loadView(
        projectId,
        "final-compose",
        () => getFinalComposeView(projectId),
        (_state, result) => ({ finalCompose: result }),
      ),
    setClipHighlights: (unitId, clipIds) =>
      set((state) => ({
        clipHighlights: {
          ...state.clipHighlights,
          [unitId]: [...new Set(clipIds)],
        },
      })),
    clearClipHighlights: (unitId) =>
      set((state) => ({
        clipHighlights: { ...state.clipHighlights, [unitId]: [] },
      })),
    revalidateLoaded: async (projectId) => {
      const current = get();
      if (current.projectId !== projectId) return;

      const requests: Promise<void>[] = [];
      if (current.header !== null) requests.push(current.loadHeader(projectId));
      if (current.plan !== null) requests.push(current.loadPlan(projectId));
      Object.keys(current.sections).forEach((sectionId) => {
        requests.push(current.loadSection(projectId, sectionId));
      });
      Object.keys(current.workbenches).forEach((unitId) => {
        requests.push(current.loadWorkbench(projectId, unitId));
      });
      if (current.assets !== null) requests.push(current.loadAssets(projectId));
      Object.keys(current.sectionCompose).forEach((sectionId) => {
        requests.push(current.loadSectionCompose(projectId, sectionId));
      });
      if (current.finalCompose !== null)
        requests.push(current.loadFinalCompose(projectId));

      await Promise.all(requests);
    },
    invalidate: (keys) => {
      if (!keys) {
        resetProject(get().projectId);
        return;
      }
      keys.forEach((key) => latestRequestByKey.set(key, ++nextRequestId));
      set((state) => {
        const patch: Partial<WorkspaceViewState> = {
          loading: {
            ...state.loading,
            ...Object.fromEntries(keys.map((key) => [key, false])),
          },
        };
        if (keys.includes("header")) patch.header = null;
        if (keys.includes("plan")) patch.plan = null;
        if (keys.includes("assets")) patch.assets = null;
        if (keys.includes("final-compose")) patch.finalCompose = null;
        return patch;
      });
    },
  };
});
