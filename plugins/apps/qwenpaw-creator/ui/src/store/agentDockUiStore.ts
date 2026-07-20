import { create } from "zustand";

export interface SelectionAttachment {
  text: string;
  ref: string | null;
  field: string | null;
  /** Exact RFC 6901 pointer to the canonical value in project.json, when available. */
  path?: string | null;
  start: number;
  end: number;
  label: string;
}

export type AgentDockTab = "conversation" | "activity" | "review";

export interface ReviewGroupContext {
  groupId: string;
  decisionToken: string;
  title: string;
  targetRef: string | null;
  selection?: { field: string; text: string };
}

export interface ReviewRevisionHandoff extends ReviewGroupContext {
  prepared: boolean;
}

interface AgentDockUiState {
  open: boolean;
  tab: AgentDockTab;
  width: number;
  height: number;
  runFilter: string;
  draft: string;
  selection: SelectionAttachment | null;
  reviewContext: ReviewGroupContext | null;
  reviewRevisionHandoff: ReviewRevisionHandoff | null;
  setOpen: (open: boolean) => void;
  setTab: (tab: AgentDockTab) => void;
  setSize: (width: number, height: number) => void;
  setRunFilter: (filter: string) => void;
  setDraft: (draft: string) => void;
  setSelection: (selection: SelectionAttachment | null) => void;
  setReviewContext: (context: ReviewGroupContext | null) => void;
  requestReviewRevision: (context: ReviewGroupContext) => void;
  markReviewRevisionPrepared: () => void;
  clearReviewRevisionHandoff: () => void;
  reset: () => void;
}

export const useAgentDockUiStore = create<AgentDockUiState>((set) => ({
  open: true,
  tab: "conversation",
  width: 440,
  height: 620,
  runFilter: "all",
  draft: "",
  selection: null,
  reviewContext: null,
  reviewRevisionHandoff: null,
  setOpen: (open) => set({ open }),
  setTab: (tab) => set({ tab, open: true }),
  setSize: (width, height) =>
    set({ width: Math.max(440, width), height: Math.max(320, height) }),
  setRunFilter: (runFilter) => set({ runFilter }),
  setDraft: (draft) => set({ draft }),
  setSelection: (selection) =>
    set({ selection, tab: "conversation", open: true }),
  setReviewContext: (reviewContext) => set({ reviewContext }),
  requestReviewRevision: (context) =>
    set({
      reviewContext: context,
      reviewRevisionHandoff: { ...context, prepared: false },
      tab: "conversation",
      open: true,
    }),
  markReviewRevisionPrepared: () =>
    set((state) => ({
      reviewRevisionHandoff: state.reviewRevisionHandoff
        ? { ...state.reviewRevisionHandoff, prepared: true }
        : null,
    })),
  clearReviewRevisionHandoff: () =>
    set({ reviewRevisionHandoff: null, reviewContext: null }),
  reset: () =>
    set({
      open: true,
      tab: "conversation",
      width: 440,
      height: 620,
      runFilter: "all",
      draft: "",
      selection: null,
      reviewContext: null,
      reviewRevisionHandoff: null,
    }),
}));
