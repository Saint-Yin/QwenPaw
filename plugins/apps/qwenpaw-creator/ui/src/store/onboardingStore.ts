import { create } from "zustand";

/**
 * 新手引导状态：首页 Tour、项目工作区 Tour 与各类一次性情境提示。
 * 全部为纯前端状态，持久化在 localStorage，不触碰任何项目数据。
 * key 带版本号，未来引导内容大改时递增版本即可整体重新触发。
 */
export const ONBOARDING_STORAGE_KEY = "qwenpaw-creator:onboarding:v2";

export type OnboardingHintKey =
  | "executionAuthorization"
  | "review"
  | "mention"
  | "addToConversation";

interface PersistedOnboarding {
  homeTourDone: boolean;
  projectTourDone: boolean;
  assetsTourDone: boolean;
  hints: Partial<Record<OnboardingHintKey, boolean>>;
}

const DEFAULT_PERSISTED: PersistedOnboarding = {
  homeTourDone: false,
  projectTourDone: false,
  assetsTourDone: false,
  hints: {},
};

// 惰性获取：测试环境会替换 window.localStorage，不在模块加载时捕获引用。
function getStorage(): Pick<Storage, "getItem" | "setItem"> | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

function readPersisted(): PersistedOnboarding {
  try {
    const raw = getStorage()?.getItem(ONBOARDING_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PERSISTED };
    const parsed = JSON.parse(raw) as Partial<PersistedOnboarding>;
    return {
      homeTourDone: parsed.homeTourDone === true,
      projectTourDone: parsed.projectTourDone === true,
      assetsTourDone: parsed.assetsTourDone === true,
      hints:
        parsed.hints && typeof parsed.hints === "object" ? parsed.hints : {},
    };
  } catch {
    return { ...DEFAULT_PERSISTED };
  }
}

function persist(state: PersistedOnboarding) {
  try {
    getStorage()?.setItem(
      ONBOARDING_STORAGE_KEY,
      JSON.stringify({
        homeTourDone: state.homeTourDone,
        projectTourDone: state.projectTourDone,
        assetsTourDone: state.assetsTourDone,
        hints: state.hints,
      }),
    );
  } catch {
    // 存储不可用（如隐私模式）时静默降级为会话级状态。
  }
}

interface OnboardingState extends PersistedOnboarding {
  /** 帮助入口手动重看 Tour 的运行时请求，不持久化。 */
  homeTourRequested: boolean;
  projectTourRequested: boolean;
  assetsTourRequested: boolean;
  completeHomeTour: () => void;
  requestHomeTour: () => void;
  completeProjectTour: () => void;
  requestProjectTour: () => void;
  completeAssetsTour: () => void;
  requestAssetsTour: () => void;
  markHintSeen: (key: OnboardingHintKey) => void;
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  ...readPersisted(),
  homeTourRequested: false,
  projectTourRequested: false,
  assetsTourRequested: false,
  completeHomeTour: () => {
    set({ homeTourDone: true, homeTourRequested: false });
    persist(get());
  },
  requestHomeTour: () => set({ homeTourRequested: true }),
  completeProjectTour: () => {
    set({ projectTourDone: true, projectTourRequested: false });
    persist(get());
  },
  requestProjectTour: () => set({ projectTourRequested: true }),
  completeAssetsTour: () => {
    set({ assetsTourDone: true, assetsTourRequested: false });
    persist(get());
  },
  requestAssetsTour: () => set({ assetsTourRequested: true }),
  markHintSeen: (key) => {
    if (get().hints[key]) return;
    set((state) => ({ hints: { ...state.hints, [key]: true } }));
    persist(get());
  },
}));
