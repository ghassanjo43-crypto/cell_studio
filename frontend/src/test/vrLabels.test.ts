import { describe, expect, it } from "vitest";
import type { FrameData } from "../api/types";
import { buildPanels } from "../components/vr/labels";

function frame(overrides: Partial<FrameData> = {}): FrameData {
  return {
    mass: 1.5,
    alive: true,
    status: "GROWING",
    metabolism_status: "optimal",
    divisions: 2,
    generation: 2,
    lineage: "0.0",
    env_glucose: 30,
    pool_glucose: 1.2,
    membrane_integrity: 0.9,
    ...overrides,
  };
}

describe("buildPanels", () => {
  it("shows an awaiting panel when there is no frame", () => {
    const panels = buildPanels(null);
    expect(panels).toHaveLength(1);
    expect(panels[0].lines[0]).toMatch(/awaiting/i);
  });

  it("always includes a vitals panel with mass, status and generation", () => {
    const panels = buildPanels(frame());
    const vitals = panels.find((p) => p.title === "Vitals")!;
    expect(vitals.lines.join(" ")).toMatch(/status: GROWING/);
    expect(vitals.lines.join(" ")).toMatch(/biomass:/);
    expect(vitals.lines.join(" ")).toMatch(/generation: 2/);
  });

  it("shows a glucose panel for non-spatial scenarios", () => {
    const panels = buildPanels(frame());
    expect(panels.some((p) => p.title === "Glucose")).toBe(true);
  });

  it("shows a nutrients panel with the limiting nutrient for spatial scenarios", () => {
    const panels = buildPanels(
      frame({ nutrients: { glc: { pool: 1, surface: 2 }, nh4: { pool: 0.5, surface: 0.3 } }, limiting: "met.nh4" }),
    );
    const n = panels.find((p) => p.title === "Nutrients")!;
    expect(n.lines.some((l) => l.includes("glc"))).toBe(true);
    expect(n.lines.some((l) => l.includes("limiting: nh4"))).toBe(true);
  });

  it("shows a compartments panel with a stress marker", () => {
    const panels = buildPanels(
      frame({
        compartments: {
          cytosol: { energy: 20, stressed: false },
          nucleoid: { energy: 0.1, stressed: true },
          membrane_zone: { energy: 5, stressed: false },
        },
      }),
    );
    const c = panels.find((p) => p.title.startsWith("Compartments"))!;
    expect(c.lines.some((l) => l.includes("nucleoid") && l.includes("⚠"))).toBe(true);
  });
});
