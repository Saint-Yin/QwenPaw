import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import type { ComposeView, PlanView } from "@/contracts/creator";
import PlanPage from "@/pages/PlanPage";
import { NavigationRuntime } from "@/routing/navigation";
import {
  selectPlanDetail,
  selectPlanTerms,
  selectPlanTotalDuration,
} from "@/selectors/planViewSelectors";
import {
  composeView,
  envelope,
  headerView,
  planView,
} from "@/test/creatorFixtures";
import { installMockFetch } from "@/test/mockFetch";
import { useWorkspaceViewStore } from "@/store/workspaceViewStore";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useCreatorTaskViewStore } from "@/store/creatorTaskViewStore";

const fidelityPlan: PlanView = {
  ...planView,
  sections: [
    {
      ...planView.sections[0],
      units: [
        {
          ...planView.sections[0].units[0],
          storyboardPrompt: "雪夜公路，电影感构图",
          storyboardImageUrl: "/creator/media/artifacts/storyboard-v1",
          videoPrompt: "汽车沿公路稳定驶过",
        },
      ],
    },
  ],
};

const finalView: ComposeView = {
  ...composeView,
  kind: "final",
  sectionId: undefined,
  sectionNumber: undefined,
  sectionTitle: undefined,
  sections: [{ id: "s1", number: 1, title: "开场" }],
  candidates: [
    {
      ...composeView.candidates[0],
      id: "section-v1",
      name: "开场",
      artifactVersionId: "section-v1",
      ownerRef: "project://section/s1",
      sourceRef: "artifact://section-slot@section-v1",
      slotId: "section-slot",
      kind: "section_video",
      uiLocator: {
        page: "section-compose",
        sectionId: "s1",
        versionId: "section-v1",
      },
    },
  ],
  selections: [],
  targetVersion: "ov-final",
  uiLocator: { page: "final-compose" },
};

describe("PlanPage origin/main fidelity", () => {
  beforeEach(() => {
    useWorkspaceViewStore.getState().reset();
    useWorkspaceViewStore.setState({
      header: envelope({ ...headerView, scenario: "general" }),
    });
    useCreatorSessionStore.setState({ events: [] });
    useCreatorTaskViewStore.getState().reset();
  });

  it("derives the real detail selection, duration, and origin scenario terms through plan selectors", () => {
    expect(selectPlanDetail(fidelityPlan, undefined, "u1")).toMatchObject({
      selectedSection: { id: "s1" },
      selectedUnit: { id: "u1" },
      detailOpen: true,
    });
    expect(selectPlanTotalDuration(fidelityPlan)).toBe(6);
    expect(selectPlanTerms("short_drama")).toEqual({
      structure: "剧本大纲",
      section: "集",
      unit: "Clip",
    });
    expect(selectPlanTerms("video_edit")).toEqual({
      structure: "剪辑方案",
      section: "剪辑段",
      unit: "剪辑片段",
    });
    expect(selectPlanTerms("general")).toEqual({
      structure: "视频结构",
      section: "Section",
      unit: "生成单元",
    });
  });

  it("renders an actionable initialization surface when the Project has no structure", async () => {
    installMockFetch([
      {
        match: "/projects/p1/plan",
        response: { json: envelope({ ...planView, sections: [] }) },
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("还没有视频结构")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "生成结构" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "导入剧本" }),
    ).toBeInTheDocument();
  });

  it("keeps the origin toolbar, cards, 36/64 detail layout, and retained R2V fields", async () => {
    installMockFetch([
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    const { container } = render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("视频方案")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /添加结构段/ })).toHaveClass(
      "!text-xs",
    );
    expect(screen.getByRole("button", { name: /最终合成/ })).toHaveClass(
      "!text-xs",
    );
    expect(screen.getByRole("button", { name: /Agent 规划任务/ })).toHaveClass(
      "!text-xs",
    );
    expect(
      screen.getByText(
        "先以视频结构组织整支片子，再从具体生成单元进入制作工作台。",
      ),
    ).toBeInTheDocument();
    const card = container.querySelector(
      '[data-creator-module="section-card"]',
    );
    expect(card).toHaveClass(
      "rounded-xl",
      "border",
      "bg-[var(--color-bg-card)]",
      "p-4",
    );
    fireEvent.click(screen.getByText("开场"));
    await waitFor(() =>
      expect(
        screen.getByText("Section定义整体叙事与约束，不直接进入制作工作台。"),
      ).toBeInTheDocument(),
    );
    const split = container.querySelector('[style*="minmax(0,36fr)"]');
    expect(split).toHaveStyle({
      gridTemplateColumns: "minmax(0,36fr) minmax(0,64fr)",
    });
    fireEvent.click(screen.getAllByText("01 Unit 1")[0]);
    await waitFor(() =>
      expect(screen.getByText("分镜 Prompt")).toBeInTheDocument(),
    );
    expect(screen.getByText("雪夜公路，电影感构图")).toBeInTheDocument();
    expect(screen.getByAltText("分镜图")).toHaveClass(
      "w-full",
      "rounded-lg",
      "border",
    );
    expect(screen.getByText("视频 Prompt")).toBeInTheDocument();
  });

  it("submits Agent planning through the PLAN_UNITS semantic command only", async () => {
    const { calls } = installMockFetch([
      {
        match: "/commands",
        response: {
          json: { commandId: "cmd-plan", status: "QUEUED", eventSeq: 7 },
        },
      },
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /Agent 规划任务/ }),
    );
    await waitFor(() =>
      expect(calls.some((call) => call.url.includes("/commands"))).toBe(true),
    );
    const command = calls.find((call) => call.url.includes("/commands"))!;
    expect(command.method).toBe("POST");
    expect(command.body).toMatchObject({
      type: "PLAN_UNITS",
      targetRef: "project:plan",
      arguments: {},
      expectedTargetVersions: [
        { ref: "project:plan", objectVersion: fidelityPlan.targetVersion },
      ],
    });
    expect(calls.some((call) => call.url.includes("/messages"))).toBe(false);
  });

  it("opens the origin 960px Final Compose modal with section grouping and transition controls", async () => {
    installMockFetch([
      {
        match: "/projects/p1/post/final",
        response: { json: envelope(finalView) },
      },
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    const { container } = render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: /最终合成/ }));
    expect(await screen.findByText("最终剪辑视频合成")).toBeInTheDocument();
    expect(screen.getByText("可选成片（按结构段分组）")).toBeInTheDocument();
    expect(screen.getByText("合成顺序（从上到下）")).toBeInTheDocument();
    expect(screen.getByText("拼接点平滑")).toBeInTheDocument();
    expect(container.ownerDocument.querySelector(".ant-modal")).toHaveStyle({
      width: "960px",
    });
  });

  it("keeps the origin Unit-video fallback and labels it as 单元成片", async () => {
    const unitFinalView: ComposeView = {
      ...finalView,
      candidates: [
        {
          ...finalView.candidates[0],
          id: "unit-v1",
          name: "Unit 1 video",
          artifactVersionId: "unit-v1",
          ownerRef: "project://unit/u1",
          sourceRef: "artifact://unit-slot@unit-v1",
          slotId: "unit-slot",
          kind: "unit_video",
          sourceKind: "unit",
          sectionId: "s1",
          uiLocator: { page: "workbench", unitId: "u1", versionId: "unit-v1" },
        },
      ],
      selections: [],
      blockers: [],
      readiness: { ready: true },
    };
    installMockFetch([
      {
        match: "/projects/p1/post/final",
        response: { json: envelope(unitFinalView) },
      },
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: /最终合成/ }));
    expect(await screen.findByText("01 Unit 1")).toBeInTheDocument();
    expect(screen.getByText("单元成片")).toBeInTheDocument();
    expect(screen.getByText(/已选 1 段/)).toBeInTheDocument();
  });

  it("retains completed task feedback for five seconds with the origin close action", async () => {
    useCreatorTaskViewStore.setState({
      projectId: "p1",
      tasks: [
        {
          id: "task-done",
          projectId: "p1",
          transactionId: null,
          specialistRunId: null,
          kind: "asset_ingest",
          targetRef: "project:p1",
          status: "SUCCEEDED",
          progress: 1,
          resultRefs: [],
          result: { summary: "素材已入库" },
          error: null,
          updatedAt: new Date().toISOString(),
        },
      ],
    });
    installMockFetch([
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("附件入库中")).toBeInTheDocument();
    expect(screen.getByText("素材已入库")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(screen.queryByText("素材已入库")).not.toBeInTheDocument();
  });

  it("renders measurable asset ingest progress as a percentage", async () => {
    useCreatorTaskViewStore.setState({
      projectId: "p1",
      tasks: [
        {
          id: "task-running",
          projectId: "p1",
          transactionId: null,
          specialistRunId: null,
          kind: "asset_ingest",
          targetRef: "project:p1",
          status: "RUNNING",
          progress: 0.42,
          resultRefs: [],
          result: null,
          error: null,
          updatedAt: new Date().toISOString(),
        },
      ],
    });
    installMockFetch([
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("进度 42%")).toBeInTheDocument();
  });

  it("does not invent percentage progress for opaque provider tasks", async () => {
    useCreatorTaskViewStore.setState({
      projectId: "p1",
      tasks: [
        {
          id: "task-image",
          projectId: "p1",
          transactionId: "tx1",
          specialistRunId: "run1",
          kind: "image_generation",
          targetRef: "project:assets",
          status: "RUNNING",
          progress: 0,
          resultRefs: [],
          result: null,
          error: null,
          updatedAt: new Date().toISOString(),
        },
      ],
    });
    installMockFetch([
      {
        match: "/projects/p1/plan",
        response: { json: envelope(fidelityPlan) },
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/project/p1/plan"]}>
        <NavigationRuntime />
        <Routes>
          <Route path="/project/:id/plan" element={<PlanPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("图片生成中")).toBeInTheDocument();
    expect(screen.getByText("处理中…")).toBeInTheDocument();
    expect(screen.queryByText("进度 0%")).not.toBeInTheDocument();
  });
});
