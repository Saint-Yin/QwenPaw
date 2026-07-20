import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CreatorSessionResponse,
  CreatorSessionStatus,
  ExecutionAuthorizationView,
  ReviewManifest,
} from "@/contracts/creator";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useReviewManifestStore } from "@/store/reviewManifestStore";
import { useWorkspaceViewStore } from "@/store/workspaceViewStore";
import {
  assetView,
  composeView,
  envelope,
  headerView,
  planView,
  r2vView,
} from "@/test/creatorFixtures";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function response<T>(body: T, status = 200): Response {
  return {
    ok: true,
    status,
    statusText: "OK",
    json: async () => body,
  } as Response;
}

function creatorSession(
  sessionStatus: CreatorSessionStatus,
  lastEventSeq: number,
): CreatorSessionResponse {
  return {
    session: {
      id: "session-p1",
      projectId: "p1",
      status: sessionStatus,
      lastMessageSeq: 1,
      lastConsumedMessageSeq: 1,
      lastEventSeq,
    },
    agentStatusBar: {
      progress: {
        phase:
          sessionStatus === "PENDING_REVIEW" ? "review" : "unit_production",
        label: sessionStatus,
        sourceEventSeq: lastEventSeq,
        updatedAt: `event-${lastEventSeq}`,
      },
      badges: [],
    },
  };
}

function authorization(
  statusValue: ExecutionAuthorizationView["status"],
): ExecutionAuthorizationView {
  return {
    id: "authorization-1",
    transactionId: "tx-1",
    specialistRunId: "run-1",
    executionRequestId: "execution-1",
    targetRef: "unit:u1",
    scope: {},
    status: statusValue,
    authorizationToken: "authorization-token",
    provider: "dashscope",
    model: "wan2.7-r2v",
    estimatedCost: 1,
    currency: "CNY",
    maxCandidates: 1,
    createdAt: "now",
  };
}

function reviewManifest(
  transactionId: string,
  reviewRound: number,
): ReviewManifest {
  return {
    id: `manifest-${transactionId}-${reviewRound}`,
    transactionId,
    reviewRound,
    baseRevisionId: "revision-base",
    reviewRevisionId: `revision-${transactionId}-${reviewRound}`,
    manifestToken: `manifest-token-${transactionId}-${reviewRound}`,
    summary: `round ${reviewRound}`,
    journalSeqRange: { fromExclusive: 0, toInclusive: reviewRound },
    decisionGroups: [],
    operations: [],
    createdArtifactVersionRefs: [],
    mediaComparisons: [],
    integrationPreviews: [],
    createdAt: "now",
  };
}

describe("authoritative response ordering", () => {
  beforeEach(() => {
    useCreatorSessionStore.getState().reset();
    useReviewManifestStore.getState().reset();
    useWorkspaceViewStore.getState().reset();
  });

  it("keeps the newest Session refresh when an older authorization snapshot arrives last", async () => {
    const older = deferred<Response>();
    const newer = deferred<Response>();
    const requests = [older, newer];
    let index = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => requests[index++].promise),
    );
    useCreatorSessionStore.setState({
      projectId: "p1",
      session: creatorSession("RUNNING", 1).session,
      agentStatusBar: creatorSession("RUNNING", 1).agentStatusBar,
    });

    const olderRefresh = useCreatorSessionStore.getState().refreshSession();
    const newerRefresh = useCreatorSessionStore.getState().refreshSession();
    newer.resolve(response(creatorSession("PENDING_REVIEW", 10)));
    await newerRefresh;
    older.resolve(response(creatorSession("WAITING_EXECUTION_AUTH", 9)));
    await olderRefresh;

    expect(useCreatorSessionStore.getState().session?.status).toBe(
      "PENDING_REVIEW",
    );
    expect(useCreatorSessionStore.getState().session?.lastEventSeq).toBe(10);
    expect(
      useCreatorSessionStore.getState().agentStatusBar?.progress.sourceEventSeq,
    ).toBe(10);
  });

  it("does not let an in-flight Session response roll back a later durable SSE head", async () => {
    const pending = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => pending.promise),
    );
    useCreatorSessionStore.setState({
      projectId: "p1",
      session: creatorSession("RUNNING", 4).session,
      agentStatusBar: creatorSession("RUNNING", 4).agentStatusBar,
      lastEventSeq: 4,
    });

    const refresh = useCreatorSessionStore.getState().refreshSession();
    useCreatorSessionStore.getState().ingestEvent({
      eventId: "event-5",
      seq: 5,
      type: "session.status_changed",
      projectId: "p1",
      creatorSessionId: "session-p1",
      at: "now",
      data: { status: "PENDING_REVIEW" },
    });
    pending.resolve(response(creatorSession("WAITING_EXECUTION_AUTH", 4)));
    await refresh;

    expect(useCreatorSessionStore.getState().session?.status).toBe(
      "PENDING_REVIEW",
    );
    expect(useCreatorSessionStore.getState().session?.lastEventSeq).toBe(5);
  });

  it("keeps the newest working-head snapshot for each independent View key", async () => {
    const older = deferred<Response>();
    const newer = deferred<Response>();
    const requests = [older, newer];
    let index = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => requests[index++].promise),
    );

    const olderLoad = useWorkspaceViewStore.getState().loadPlan("p1");
    const newerLoad = useWorkspaceViewStore.getState().loadPlan("p1");
    newer.resolve(
      response(
        envelope(
          { ...planView, title: "new plan" },
          { workingHead: "head-new" },
        ),
      ),
    );
    await newerLoad;
    older.resolve(
      response(
        envelope(
          { ...planView, title: "old plan" },
          { workingHead: "head-old" },
        ),
      ),
    );
    await olderLoad;

    expect(useWorkspaceViewStore.getState().plan?.workingHead).toBe("head-new");
    expect(useWorkspaceViewStore.getState().plan?.view).toMatchObject({
      title: "new plan",
    });
    expect(useWorkspaceViewStore.getState().loading.plan).toBe(false);
  });

  it("discards an old-project View response after navigation", async () => {
    const projectOne = deferred<Response>();
    const projectTwo = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).includes("/projects/p1/")
          ? projectOne.promise
          : projectTwo.promise,
      ),
    );

    const oldLoad = useWorkspaceViewStore.getState().loadHeader("p1");
    const newLoad = useWorkspaceViewStore.getState().loadHeader("p2");
    projectTwo.resolve(
      response(
        envelope(
          { ...headerView, id: "p2", name: "project two" },
          { projectId: "p2", workingHead: "head-p2" },
        ),
      ),
    );
    await newLoad;
    projectOne.resolve(
      response(
        envelope(
          { ...headerView, name: "project one" },
          { workingHead: "head-p1" },
        ),
      ),
    );
    await oldLoad;

    expect(useWorkspaceViewStore.getState().projectId).toBe("p2");
    expect(useWorkspaceViewStore.getState().header?.projectId).toBe("p2");
    expect(useWorkspaceViewStore.getState().header?.view).toMatchObject({
      name: "project two",
    });
  });

  it("revalidates every loaded View key without loading absent Views", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/header"))
        return Promise.resolve(response(envelope(headerView)));
      if (url.endsWith("/plan"))
        return Promise.resolve(response(envelope(planView)));
      if (url.endsWith("/sections/s1")) {
        return Promise.resolve(response(envelope(planView.sections[0])));
      }
      if (url.endsWith("/units/u1/workbench"))
        return Promise.resolve(response(envelope(r2vView)));
      if (url.endsWith("/assets"))
        return Promise.resolve(response(envelope(assetView)));
      if (url.endsWith("/post/sections/s1"))
        return Promise.resolve(response(envelope(composeView)));
      throw new Error(`Unexpected View request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    useWorkspaceViewStore.setState({
      projectId: "p1",
      header: envelope(headerView),
      plan: envelope(planView),
      sections: { s1: envelope(planView.sections[0]) },
      workbenches: { u1: envelope(r2vView) },
      assets: envelope(assetView),
      sectionCompose: { s1: envelope(composeView) },
      finalCompose: null,
    });

    await useWorkspaceViewStore.getState().revalidateLoaded("p1");

    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls).toHaveLength(6);
    expect(urls).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/\/projects\/p1\/header$/),
        expect.stringMatching(/\/projects\/p1\/plan$/),
        expect.stringMatching(/\/projects\/p1\/sections\/s1$/),
        expect.stringMatching(/\/projects\/p1\/units\/u1\/workbench$/),
        expect.stringMatching(/\/projects\/p1\/assets$/),
        expect.stringMatching(/\/projects\/p1\/post\/sections\/s1$/),
      ]),
    );
    expect(urls.some((url) => url.endsWith("/post/final"))).toBe(false);
  });

  it("fences an in-flight PENDING authorization list with the approve response", async () => {
    const staleList = deferred<Response>();
    const approved = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST" && url.endsWith("/approve"))
          return approved.promise;
        if (url.includes("/execution-authorizations?status=PENDING"))
          return staleList.promise;
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    useReviewManifestStore.getState().bindTransaction("p1", "tx-1");
    useReviewManifestStore.setState({
      authorizations: [authorization("PENDING")],
    });

    const oldList = useReviewManifestStore.getState().loadAuthorizations();
    const approve = useReviewManifestStore
      .getState()
      .approveAuthorization("authorization-1", {
        authorizationToken: "authorization-token",
        provider: "dashscope",
        model: "wan2.7-r2v",
        maxCost: 1,
        maxCandidates: 1,
      });
    approved.resolve(response(authorization("APPROVED")));
    await approve;
    staleList.resolve(response({ items: [authorization("PENDING")] }));
    await oldList;

    expect(useReviewManifestStore.getState().authorizations).toEqual([
      authorization("APPROVED"),
    ]);
  });

  it("discards Review and authorization responses from a previously bound transaction", async () => {
    const responses = new Map<string, ReturnType<typeof deferred<Response>>>();
    for (const path of [
      "tx-1/review",
      "tx-1/auth",
      "tx-2/review",
      "tx-2/auth",
    ]) {
      responses.set(path, deferred<Response>());
    }
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        const transactionId = url.includes("/tx-1/") ? "tx-1" : "tx-2";
        const kind = url.endsWith("/review") ? "review" : "auth";
        return responses.get(`${transactionId}/${kind}`)!.promise;
      }),
    );

    const oldLoad = useReviewManifestStore.getState().load("p1", "tx-1");
    const newLoad = useReviewManifestStore.getState().load("p1", "tx-2");
    responses.get("tx-2/review")!.resolve(response(reviewManifest("tx-2", 2)));
    responses.get("tx-2/auth")!.resolve(response({ items: [] }));
    await newLoad;
    responses.get("tx-1/review")!.resolve(response(reviewManifest("tx-1", 1)));
    responses
      .get("tx-1/auth")!
      .resolve(response({ items: [authorization("PENDING")] }));
    await oldLoad;

    expect(useReviewManifestStore.getState().transactionId).toBe("tx-2");
    expect(useReviewManifestStore.getState().manifest?.transactionId).toBe(
      "tx-2",
    );
    expect(useReviewManifestStore.getState().manifest?.reviewRound).toBe(2);
    expect(useReviewManifestStore.getState().authorizations).toEqual([]);
    expect(useReviewManifestStore.getState().loading).toBe(false);
  });

  it("treats a transaction without an active Review Manifest as an empty review state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input).endsWith("/review")
          ? Promise.resolve(response(undefined, 204))
          : Promise.resolve(response({ items: [] })),
      ),
    );

    await useReviewManifestStore.getState().load("p1", "tx-without-review");

    const state = useReviewManifestStore.getState();
    expect(state.manifest).toBeNull();
    expect(state.authorizations).toEqual([]);
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });
});
