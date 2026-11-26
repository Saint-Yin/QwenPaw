import { describe, expect, it } from "vitest";

import { storyboardTierForElement } from "../storyboardTier";

const creation = (over: Record<string, unknown> = {}) => ({
  type: "r2v",
  scene_ref: "scene:stop",
  character_refs: ["char:boy"],
  prop_refs: [] as string[],
  continuity: "承接上一段…",
  video_prompt: "男孩站在顶棚下低头看手机。",
  narrative: "男孩看手机。",
  force_storyboard: false,
  ...over,
});

const el = (
  id: string,
  start: number,
  duration: number,
  over: Record<string, unknown> = {},
) => ({
  element_id: id,
  enabled: true,
  span: { start_tick: start, duration_tick: duration },
  creation: creation(over),
});

const project = (elements: unknown[], settings: Record<string, unknown> = {}) =>
  ({
    settings: { video_continuity: null, ...settings },
    timelines: {
      items: {
        "timeline:main": {
          ticks_per_second: 10,
          elements_by_id: Object.fromEntries(
            (elements as any[]).map((item) => [item.element_id, item]),
          ),
        },
      },
    },
  }) as any;

describe("storyboardTierForElement", () => {
  it("first segment is plain", () => {
    const p = project([el("e1", 0, 50)]);
    expect(storyboardTierForElement(p, "e1")).toBe("plain");
  });

  it("simple anchored segment is none", () => {
    const p = project([el("e1", 0, 50), el("e2", 50, 50)]);
    expect(storyboardTierForElement(p, "e2")).toBe("none");
  });

  it("long anchored segment is combined", () => {
    const p = project([el("e1", 0, 50), el("e2", 50, 120)]);
    expect(storyboardTierForElement(p, "e2")).toBe("combined");
  });

  it("multi-person, camera move and beats are combined", () => {
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50, { character_refs: ["char:a", "char:b"] }),
          el("e2", 50, 50, { character_refs: ["char:a", "char:b"] }),
        ]),
        "e2",
      ),
    ).toBe("combined");
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50),
          el("e2", 50, 50, { video_prompt: "镜头缓推向站台。" }),
        ]),
        "e2",
      ),
    ).toBe("combined");
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50),
          el("e2", 50, 50, { video_prompt: "男孩看手机，随后抬头。" }),
        ]),
        "e2",
      ),
    ).toBe("combined");
  });

  it("prop state change only counts with prop refs", () => {
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50),
          el("e2", 50, 50, { video_prompt: "伞撑开在两人头顶。" }),
        ]),
        "e2",
      ),
    ).toBe("none");
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50, {
            character_refs: ["char:boy", "char:girl"],
            prop_refs: ["prop:umbrella"],
          }),
          el("e2", 50, 50, {
            video_prompt: "伞撑开在头顶。",
            prop_refs: ["prop:umbrella"],
            character_refs: ["char:boy", "char:girl"],
          }),
        ]),
        "e2",
      ),
    ).toBe("combined");
  });

  it("scene change, cut continuity and throughput dial fall back to plain", () => {
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50),
          el("e2", 50, 50, { scene_ref: "scene:inside" }),
        ]),
        "e2",
      ),
    ).toBe("plain");
    expect(
      storyboardTierForElement(
        project([
          el("e1", 0, 50),
          el("e2", 50, 50, { continuity: "切到另一机位" }),
        ]),
        "e2",
      ),
    ).toBe("plain");
    expect(
      storyboardTierForElement(
        project([el("e1", 0, 50), el("e2", 50, 50)], {
          video_continuity: "throughput",
        }),
        "e2",
      ),
    ).toBe("plain");
  });

  it("force_storyboard pins combined", () => {
    const p = project([el("e1", 0, 50), el("e2", 50, 50)]);
    (
      p.timelines.items["timeline:main"] as any
    ).elements_by_id.e2.creation.force_storyboard = true;
    expect(storyboardTierForElement(p, "e2")).toBe("combined");
  });

  it("explicit transition between neighbours demotes to plain", () => {
    const transition = {
      element_id: "t1",
      enabled: true,
      span: { start_tick: 50, duration_tick: 1 },
      creation: {
        type: "transition",
        from_element_id: "e1",
        to_element_id: "e2",
        transition_kind: "fade",
      },
    };
    const p = project([el("e1", 0, 50), el("e2", 50, 50), transition]);
    expect(storyboardTierForElement(p, "e2")).toBe("plain");
  });
});
