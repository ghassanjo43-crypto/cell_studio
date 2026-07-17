import { render, renderHook } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { FrameData } from "../api/types";
import { HoverTooltip } from "../components/explorer/HoverTooltip";
import { HoverProvider, useHoverHandlers } from "../components/explorer/cell/interact";
import { buildInspect, hoverTip, type ObjectId } from "../components/explorer/inspect";

function frame(over: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1.2, alive: true, status: "GROWING", metabolism_status: "optimal",
    divisions: 2, generation: 3, lineage: "0", env_glucose: 24, pool_glucose: 3,
    membrane_integrity: 0.9,
    phenotype: { transport: 1.4, membrane: 1.2 },
    expression: { mrna: 40, protein: 260 },
    replication: { progress: 0.5, replicating: true, complete: false },
    ...over,
  } as FrameData;
}

// Every biological element the tooltip must name, with a live value we can check.
const CASES: { id: ObjectId; title: string; needle: string }[] = [
  { id: "membrane", title: "Membrane", needle: "integrity" },
  { id: "lipid", title: "Lipid bilayer", needle: "integrity" },
  { id: "channel", title: "Glucose channel", needle: "aperture" },
  { id: "receptor", title: "Receptor", needle: "starvation" },
  { id: "cytosol", title: "Cytosol", needle: "internal glucose" },
  { id: "nucleoid", title: "Nucleoid", needle: "replication" },
  { id: "fork", title: "Replication fork", needle: "progress" },
  { id: "mutation", title: "Mutation site", needle: "transport" },
  { id: "division", title: "Division furrow", needle: "divisions" },
  { id: "transport", title: "Transport proteins", needle: "activity" },
  { id: "ribosome", title: "Ribosome", needle: "protein pool" },
  { id: "protein", title: "Protein", needle: "protein pool" },
  { id: "enzyme", title: "Enzyme", needle: "metabolism" },
  { id: "atp", title: "ATP", needle: "internal glucose" },
  { id: "glucose", title: "Glucose molecule", needle: "medium glucose" },
  { id: "metabolite", title: "Metabolite", needle: "internal glucose" },
  { id: "vesicle", title: "Vesicle", needle: "repair drive" },
];

describe("tooltip label generation", () => {
  const f = frame({
    signalling: { mode: "NORMAL", survival: false, signals: { starvation: 0.3, growth: 0.6, membrane_stress: 0.1 } },
    genotype: { transport: 1.1, yield: 0.95 },
    compartments: { cytosol: { energy: 12, stressed: false } },
  });

  it("names every element with a short description and live values", () => {
    for (const c of CASES) {
      const info = buildInspect(c.id, f);
      expect(info, c.id).not.toBeNull();
      expect(info!.title).toBe(c.title);
      expect(hoverTip(info!).length, `${c.id} tip`).toBeGreaterThan(0);
      const labels = info!.values.map((v) => v.label);
      expect(labels, `${c.id} value`).toContain(c.needle);
    }
  });

  it("uses live simulation values, not invented ones", () => {
    const g = buildInspect("glucose", f)!;
    // medium glucose must reflect the frame's env_glucose (24 mM).
    expect(g.values.find((v) => v.label === "medium glucose")!.value).toContain("24");
    const fork = buildInspect("fork", f)!;
    expect(fork.values.find((v) => v.label === "progress")!.value).toBe("50%"); // replication.progress 0.5
    const atp = buildInspect("atp", f)!;
    expect(atp.values.some((v) => v.label === "ATP energy")).toBe(true); // from compartment energy
  });

  it("falls back to the first sentence of the explanation when no explicit tip", () => {
    const membrane = buildInspect("membrane", f)!;
    expect(membrane.tip).toBeUndefined();
    const tip = hoverTip(membrane);
    expect(tip.length).toBeGreaterThan(0);
    expect(tip.endsWith(".")).toBe(true); // a single clean sentence
  });

  it("degrades gracefully with no frame or absent data", () => {
    expect(buildInspect("ribosome", null)).toBeNull();
    // receptor still resolves without a signalling network (generic sensor).
    expect(buildInspect("receptor", frame())).not.toBeNull();
  });
});

describe("HoverTooltip component", () => {
  it("renders name, description and live value, and follows the cursor", () => {
    const { container, getByText } = render(
      createElement(HoverTooltip, { id: "ribosome", x: 100, y: 200, frame: frame(), onClick: () => {} }),
    );
    expect(getByText("Ribosome")).toBeTruthy();
    expect(container.querySelector(".hover-tip-desc")?.textContent).toMatch(/translate/i);
    expect(container.querySelector(".hover-tip-row")).toBeTruthy();
    // Positioned at cursor (+16 offset).
    const tip = container.querySelector<HTMLElement>(".hover-tip")!;
    expect(tip.style.left).toBe("116px");
    expect(tip.style.top).toBe("216px");
  });

  it("opens the inspector when clicked", () => {
    const onClick = vi.fn();
    const { container } = render(
      createElement(HoverTooltip, { id: "atp", x: 0, y: 0, frame: frame(), onClick }),
    );
    container.querySelector<HTMLElement>(".hover-tip")!.click();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("renders nothing when there is no data", () => {
    const { container } = render(
      createElement(HoverTooltip, { id: "ribosome", x: 0, y: 0, frame: null, onClick: () => {} }),
    );
    expect(container.querySelector(".hover-tip")).toBeNull();
  });
});

describe("hover-state behavior (useHoverHandlers)", () => {
  it("raises the element id + cursor on over/move and clears on out", () => {
    const calls: [ObjectId | null, number?, number?][] = [];
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(HoverProvider, { value: (id, x, y) => calls.push([id, x, y]) }, children);
    const { result } = renderHook(() => useHoverHandlers("ribosome"), { wrapper });

    const ev = (x: number, y: number) =>
      ({ stopPropagation: () => {}, nativeEvent: { clientX: x, clientY: y } }) as never;
    result.current.onPointerOver(ev(5, 7));
    result.current.onPointerMove(ev(9, 11));
    result.current.onPointerOut({ stopPropagation: () => {} } as never);

    expect(calls[0]).toEqual(["ribosome", 5, 7]);
    expect(calls[1]).toEqual(["ribosome", 9, 11]);
    expect(calls[2][0]).toBeNull(); // hover cleared on leave
  });
});
