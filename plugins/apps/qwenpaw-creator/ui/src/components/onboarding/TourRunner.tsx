import { useEffect, useMemo, useState } from "react";
import { Tour, type TourProps } from "antd";

/**
 * 通用 Spotlight 导览执行器：按蓝图轮询等待锚点挂载后弹出 antd Tour，
 * 锚点缺失的步骤自动跳过。首页与项目工作区共用。
 */

export interface TourStepBlueprint {
  selectors: string[];
  title: string;
  description: React.ReactNode;
}

export function resolveTarget(selectors: string[]): HTMLElement | null {
  for (const selector of selectors) {
    const element = document.querySelector<HTMLElement>(selector);
    if (element) return element;
  }
  return null;
}

interface TourRunnerProps {
  steps: TourStepBlueprint[];
  /** 触发条件（首次进入或手动重看）；为 false 时不做任何事。 */
  shouldRun: boolean;
  /** 结束（完成或关闭）时回调，负责持久化完成标记。 */
  onFinish: () => void;
}

export default function TourRunner({
  steps,
  shouldRun,
  onFinish,
}: TourRunnerProps) {
  const [open, setOpen] = useState(false);
  const [anchorsReady, setAnchorsReady] = useState(false);
  const active = shouldRun && !open;

  // 锚点可能异步渲染（快照轮询 + 懒加载），轮询等待首个锚点挂载。
  useEffect(() => {
    if (!active) return;
    setAnchorsReady(false);
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      if (resolveTarget(steps[0].selectors)) {
        window.clearInterval(timer);
        setAnchorsReady(true);
        return;
      }
      // 最多等 30 秒；Agent 首次规划期间页面可能长时间处于骨架态。
      if (tries > 100) window.clearInterval(timer);
    }, 300);
    return () => window.clearInterval(timer);
  }, [active, steps]);

  useEffect(() => {
    if (active && anchorsReady) setOpen(true);
  }, [active, anchorsReady]);

  const tourSteps = useMemo<TourProps["steps"]>(() => {
    if (!open) return [];
    return steps
      .filter((step) => resolveTarget(step.selectors))
      .map((step) => ({
        title: step.title,
        description: step.description,
        target: () => resolveTarget(step.selectors) as HTMLElement,
      }));
  }, [open, steps]);

  const finish = () => {
    setOpen(false);
    setAnchorsReady(false);
    onFinish();
  };

  if (!open || !tourSteps || tourSteps.length === 0) return null;

  return (
    <Tour open={open} steps={tourSteps} onClose={finish} onFinish={finish} />
  );
}
