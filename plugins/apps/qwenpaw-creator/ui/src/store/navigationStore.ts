import { create } from "zustand";

/**
 * 跨上下文跳转位置栈（设计文档 3.2，迭代计划 1.5）。
 *
 * 跳转前保存来源位置的完整状态（路由、选中对象、滚动位置），
 * 跳转后顶部渲染返回条；用户主动导航时清栈。
 */
export interface SavedLocation {
  /** hash 路由路径，如 /project/xxx/assets */
  path: string;
  /** 来源描述，如 "资产库 / 产品主视觉" */
  description: string;
  /** 选中对象标识（asset:xxx / unit:xxx / section:xxx） */
  selectedRef?: string;
  /** 主滚动容器 scrollTop */
  scrollTop?: number;
  savedAt: number;
}

export interface ReviewFocusRequest {
  path: string;
  ref: string;
  query: Record<string, string>;
  nonce: number;
}

interface NavigationStore {
  stack: SavedLocation[];
  /** 恢复位置后待应用的选中/滚动状态（由目标页面消费） */
  pendingRestore: SavedLocation | null;
  /** 最近一次审阅定位请求；同一路由重复点击也会递增 nonce 触发目标页重放闪烁。 */
  reviewFocus: ReviewFocusRequest | null;
  /**
   * 最近一次经 navigateToRef / returnToSavedLocation 跳转的目标路径（不含 query）。
   * 用于区分"受控跳转"与"用户主动导航"——后者应清空位置栈。
   */
  expectedPath: string | null;
  pushLocation: (location: Omit<SavedLocation, "savedAt">) => void;
  popLocation: () => SavedLocation | null;
  setExpectedPath: (path: string | null) => void;
  setReviewFocus: (request: Omit<ReviewFocusRequest, "nonce">) => void;
  clear: () => void;
  consumeRestore: () => SavedLocation | null;
}

export const useNavigationStore = create<NavigationStore>((set, get) => ({
  stack: [],
  pendingRestore: null,
  reviewFocus: null,
  expectedPath: null,

  pushLocation: (location) => {
    set((state) => ({
      stack: [...state.stack, { ...location, savedAt: Date.now() }].slice(-10),
    }));
  },

  popLocation: () => {
    const { stack } = get();
    if (stack.length === 0) return null;
    const top = stack[stack.length - 1];
    set({ stack: stack.slice(0, -1), pendingRestore: top });
    return top;
  },

  setExpectedPath: (path) => set({ expectedPath: path }),
  setReviewFocus: (request) =>
    set({ reviewFocus: { ...request, nonce: Date.now() } }),

  clear: () =>
    set({
      stack: [],
      pendingRestore: null,
      reviewFocus: null,
      expectedPath: null,
    }),

  consumeRestore: () => {
    const { pendingRestore } = get();
    if (pendingRestore) set({ pendingRestore: null });
    return pendingRestore;
  },
}));
