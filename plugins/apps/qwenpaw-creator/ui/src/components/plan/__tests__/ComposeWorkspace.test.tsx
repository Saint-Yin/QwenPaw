import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ComposeView } from "@/contracts/creator";
import ComposeWorkspace from "@/components/plan/ComposeWorkspace";
import { composeView, envelope } from "@/test/creatorFixtures";
import { installMockFetch } from "@/test/mockFetch";

const secondCandidate = {
  ...composeView.candidates[0],
  id: "art-v2",
  name: "Unit 2 video",
  artifactVersionId: "art-v2",
  ownerRef: "project://unit/u2",
  sourceRef: "artifact://slot-u2@art-v2",
  slotId: "slot-u2",
  uiLocator: { page: "workbench", unitId: "u2", versionId: "art-v2" },
};

function selectedView(): ComposeView {
  return {
    ...composeView,
    candidates: [composeView.candidates[0], secondCandidate],
    selections: [
      {
        sourceRef: "project://unit/u1",
        artifactVersionId: "art-v1",
        artifactRef: "artifact://slot-u1@art-v1",
        slotId: "slot-u1",
        order: 1000,
        uiLocator: {},
      },
      {
        sourceRef: "project://unit/u2",
        artifactVersionId: "art-v2",
        artifactRef: "artifact://slot-u2@art-v2",
        slotId: "slot-u2",
        order: 2000,
        uiLocator: {},
      },
    ],
  };
}

describe("ComposeWorkspace", () => {
  it("preserves origin clip reordering while submitting explicit owner and Artifact Version refs", async () => {
    const view = selectedView();
    const { calls } = installMockFetch([
      {
        match: "/commands",
        response: { json: { commandId: "c1", status: "APPLIED", eventSeq: 1 } },
      },
    ]);
    render(
      <ComposeWorkspace
        projectId="p1"
        envelope={envelope(view)}
        view={view}
        reload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByTitle("上移")[1]);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      type: "SET_SECTION_COMPOSE_SELECTION",
      targetRef: "post:s1",
      arguments: {
        selections: [
          {
            sourceRef: "project://unit/u2",
            artifactVersionId: "art-v2",
            artifactRef: "artifact://slot-u2@art-v2",
            order: 0,
          },
          {
            sourceRef: "project://unit/u1",
            artifactVersionId: "art-v1",
            artifactRef: "artifact://slot-u1@art-v1",
            order: 1,
          },
        ],
      },
    });
  });

  it("focuses the exact Compose artifact and replays repeated review pulses", () => {
    Element.prototype.scrollIntoView = vi.fn();
    const view = selectedView();
    const { rerender } = render(
      <ComposeWorkspace
        projectId="p1"
        envelope={envelope(view)}
        view={view}
        reload={vi.fn()}
        focusVersion="art-v1"
        focusPulse="1"
      />,
    );
    expect(
      document.querySelector('[data-artifact-version="art-v1"]'),
    ).toHaveClass("review-flash");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    rerender(
      <ComposeWorkspace
        projectId="p1"
        envelope={envelope(view)}
        view={view}
        reload={vi.fn()}
        focusVersion="art-v1"
        focusPulse="2"
      />,
    );
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(2);
  });

  it("streams a rendered file artifact through the authenticated media route", () => {
    const view: ComposeView = {
      ...selectedView(),
      renderedVideoRef: "artifact://section-video@rendered-v1",
      renderedVideoUrl: "file:///private/runtime/rendered-v1.mp4",
      resolvedRefs: [
        {
          ref: "artifact://section-video@rendered-v1",
          name: "Rendered section",
          type: "artifact",
          artifactVersionId: "rendered-v1",
          slotId: "section-video",
          uiLocator: {},
        },
      ],
    };
    const { container } = render(
      <ComposeWorkspace
        projectId="p1"
        envelope={envelope(view)}
        view={view}
        reload={vi.fn()}
      />,
    );
    const video = container.querySelector(
      'video[data-artifact-version="rendered-v1"]',
    );
    expect(video).toHaveAttribute(
      "src",
      "/api/qwenpaw-creator/media/artifacts/rendered-v1",
    );
    expect(video).not.toHaveAttribute(
      "src",
      expect.stringContaining("file://"),
    );
  });
});
