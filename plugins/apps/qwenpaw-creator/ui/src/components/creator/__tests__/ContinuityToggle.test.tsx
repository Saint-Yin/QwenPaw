import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useProjectSnapshotStore } from "@/store/projectSnapshotStore";
import ContinuityToggle from "../ContinuityToggle";

function seed(stored: unknown) {
  const settings: Record<string, unknown> = { aspect_ratio: "16:9" };
  if (stored !== "absent") settings.video_continuity = stored;
  useProjectSnapshotStore.setState({
    projectId: "p1",
    generation: 3,
    etag: '"sha256:g3"',
    project: {
      projectId: "p1",
      settings,
    } as never,
  });
}

describe("ContinuityToggle (TopNav segment-continuity switch)", () => {
  beforeEach(() => {
    useProjectSnapshotStore.getState().reset();
  });

  it("hides itself until a project is bound to the view", () => {
    const { container } = render(<ContinuityToggle />);
    expect(container).toBeEmptyDOMElement();
  });

  it("defaults to ON and persists throughput through the CAS patch channel", async () => {
    seed(null);
    const patch = vi.fn().mockResolvedValue(undefined);
    useProjectSnapshotStore.setState({ patch });
    render(<ContinuityToggle />);
    const toggle = screen.getByRole("switch");
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith("p1", [
      {
        op: "replace",
        path: "/settings/video_continuity",
        before: null,
        missingBefore: false,
        value: "throughput",
      },
    ]);
  });

  it("shows OFF for throughput and switches back to continuity", async () => {
    seed("throughput");
    const patch = vi.fn().mockResolvedValue(undefined);
    useProjectSnapshotStore.setState({ patch });
    render(<ContinuityToggle />);
    const toggle = screen.getByRole("switch");
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch.mock.calls[0][1][0]).toMatchObject({
      op: "replace",
      value: "continuity",
    });
  });
});
