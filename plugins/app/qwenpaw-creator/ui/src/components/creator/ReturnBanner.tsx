import { useEffect, useRef } from 'react';
import { usePathname } from '@/routing/navigation';
import { ArrowLeft, X } from 'lucide-react';
import { useNavigationStore } from '@/store/navigationStore';
import { returnToSavedLocation } from '@/routing/locators';

/**
 * 跨上下文跳转返回条（设计文档 3.2，迭代计划 1.5）。
 * 经 navigateToRef 跳转后出现在主工作区顶部；用户主动导航（路由变化
 * 与受控跳转目标不一致）时自动清栈消失。
 */
export default function ReturnBanner() {
  const pathname = usePathname();
  const stack = useNavigationStore((s) => s.stack);
  const expectedPath = useNavigationStore((s) => s.expectedPath);
  const clear = useNavigationStore((s) => s.clear);
  const lastPathRef = useRef(pathname);

  useEffect(() => {
    if (pathname === lastPathRef.current) return;
    lastPathRef.current = pathname;
    const state = useNavigationStore.getState();
    if (state.stack.length === 0) return;
    // 路由变化但不是 navigateToRef / 返回条触发的 → 用户主动导航，清栈
    if (state.expectedPath !== pathname) {
      state.clear();
    } else {
      state.setExpectedPath(null);
    }
  }, [pathname]);

  if (stack.length === 0) return null;
  // 刚触发受控跳转但路由尚未生效时也渲染（避免闪烁）
  if (expectedPath && expectedPath !== pathname) return null;

  const top = stack[stack.length - 1];
  const sourceDescription = top.description === '决策中心' ? '审阅/决策' : top.description;

  return (
    <div className="flex items-center justify-between gap-3 border-b border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/40 dark:text-blue-200">
      <span className="min-w-0 truncate">
        已跳转到新上下文，来自 <b className="font-semibold">{sourceDescription}</b>
      </span>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={() => returnToSavedLocation()}
          className="inline-flex items-center gap-1.5 rounded-md border border-blue-300 bg-white px-2.5 py-1 text-xs font-medium text-blue-700 transition-colors hover:bg-blue-100 dark:border-blue-800 dark:bg-transparent dark:text-blue-300 dark:hover:bg-blue-900/40"
        >
          <ArrowLeft className="h-3 w-3" />
          返回刚刚的位置
        </button>
        <button
          type="button"
          onClick={() => clear()}
          aria-label="关闭返回条"
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-blue-500 transition-colors hover:bg-blue-100 dark:hover:bg-blue-900/40"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
