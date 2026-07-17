import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { injectDrug } from "../api/client";
import type { ActiveDrug, Drug, DrugDose } from "../api/types";

// Mock the API client so the panel's live-injection path is observable without a server.
vi.mock("../api/client", () => ({
  injectDrug: vi.fn(() => Promise.resolve({})),
  interpretDrug: vi.fn(() => Promise.resolve({})),
  listDrugs: vi.fn(() => Promise.resolve([])),
}));
import { dockFor, drugParticleCount, DRUG_DOCK } from "../components/explorer/cell/drugViz";
import { DrugStudioPanel } from "../components/pharmacology/DrugStudioPanel";
import {
  addDrug,
  exportRegimen,
  filterDrugs,
  isActive,
  removeDrug,
  setDose,
  summarizeRegimen,
} from "../components/pharmacology/drugStudio";

function drug(over: Partial<Drug> = {}): Drug {
  return {
    id: "nutrient-transport-inhibitor",
    name: "Nutrient Transport Inhibitor",
    description: "Blocks uptake so the cell is cut off from its food.",
    mechanism: "Scales nutrient uptake down → ATP depletion → death.",
    targets: ["membrane transporters"],
    channels: { transport: 0.12 },
    color: "#34d399",
    viz_target: "transport",
    confidence: "high",
    default_dose: 1,
    ...over,
  };
}

const LIB: Drug[] = [
  drug(),
  drug({ id: "ribosome-inhibitor", name: "Ribosome Inhibitor", targets: ["ribosome"], viz_target: "ribosome" }),
  drug({ id: "dna-replication-inhibitor", name: "DNA Replication Inhibitor", targets: ["DNA polymerase"], viz_target: "dna" }),
];

describe("drug studio logic", () => {
  it("searches across name / mechanism / targets", () => {
    expect(filterDrugs(LIB, "ribosome").map((d) => d.id)).toEqual(["ribosome-inhibitor"]);
    expect(filterDrugs(LIB, "polymerase").map((d) => d.id)).toEqual(["dna-replication-inhibitor"]);
    expect(filterDrugs(LIB, "").length).toBe(3);
  });

  it("adds, doses, and removes drugs (no duplicates)", () => {
    let reg: DrugDose[] = [];
    reg = addDrug(reg, LIB[0]);
    reg = addDrug(reg, LIB[0]); // duplicate ignored
    expect(reg).toHaveLength(1);
    expect(isActive(reg, LIB[0].id)).toBe(true);
    reg = setDose(reg, LIB[0].id, 5); // clamped to 2
    expect(reg[0].dose).toBe(2);
    reg = addDrug(reg, LIB[1]);
    expect(summarizeRegimen(reg, LIB)).toContain("Nutrient Transport Inhibitor 2.0×");
    reg = removeDrug(reg, LIB[0].id);
    expect(reg.map((r) => r.drug_id)).toEqual(["ribosome-inhibitor"]);
  });

  it("exports a JSON experiment record with resolved names", () => {
    const reg = addDrug([], LIB[2]);
    const rec = JSON.parse(exportRegimen(reg, LIB));
    expect(rec.kind).toBe("drug-interaction-experiment");
    expect(rec.drugs[0].name).toBe("DNA Replication Inhibitor");
    expect(rec.drugs[0].dose).toBe(1);
  });
});

describe("drug visualisation mapping", () => {
  it("maps every viz target to a dock, DNA on the ring", () => {
    for (const t of Object.keys(DRUG_DOCK) as (keyof typeof DRUG_DOCK)[]) {
      expect(dockFor(t).radius).toBeGreaterThan(0);
    }
    expect(dockFor("dna").ring).toBe(true);
    expect(dockFor("membrane").radius).toBeGreaterThan(0.9); // membrane drugs sit at the surface
  });

  it("particle count scales with how strongly the drug acts", () => {
    const weak: ActiveDrug = { id: "x", name: "x", color: "#fff", viz: "dna", dose: 1, strength: 0.2, targets: [], mechanism: "", confidence: "high" };
    const strong: ActiveDrug = { ...weak, strength: 2 };
    expect(drugParticleCount(strong)).toBeGreaterThan(drugParticleCount(weak));
    expect(drugParticleCount({ ...weak, strength: 0 })).toBeGreaterThanOrEqual(10);
  });
});

describe("DrugStudioPanel", () => {
  it("renders the library and toggles a drug into the regimen", () => {
    const calls: DrugDose[][] = [];
    const { getByText, getAllByText } = render(
      createElement(DrugStudioPanel, {
        regimen: [],
        onRegimenChange: (r: DrugDose[]) => calls.push(r),
        initialDrugs: LIB,
      }),
    );
    expect(getByText("Ribosome Inhibitor")).toBeTruthy();
    // Click the first "Add" → the parent receives a one-drug regimen.
    getAllByText("Add")[0].click();
    const last = calls[calls.length - 1];
    expect(last).toHaveLength(1);
    expect(last[0].drug_id).toBe(LIB[0].id);
  });

  it("live-injects into a running simulation", () => {
    vi.mocked(injectDrug).mockClear();
    const { getAllByText } = render(
      createElement(DrugStudioPanel, {
        regimen: [],
        onRegimenChange: () => {},
        initialDrugs: LIB,
        simId: 42,
        running: true,
      }),
    );
    // In live mode the button reads "Inject" and fires the injection command.
    getAllByText("Inject")[0].click();
    expect(injectDrug).toHaveBeenCalledWith(42, { action: "add", drug_id: LIB[0].id, dose: 1 });
  });

  it("library buttons say Inject only when status is RUNNING, with a status debug line", () => {
    const props = (over: Record<string, unknown>) => ({
      regimen: [], onRegimenChange: () => {}, initialDrugs: LIB, simId: 5, ...over,
    });
    const { rerender, getAllByText, queryAllByText, container } = render(
      createElement(DrugStudioPanel, props({ running: false, status: "CREATED" })),
    );
    // Not RUNNING → buttons say "Add", none say "Inject".
    expect(queryAllByText("Inject")).toHaveLength(0);
    expect(getAllByText("Add").length).toBeGreaterThan(0);
    const debug = () => container.querySelector(".drug-debug")?.textContent ?? "";
    expect(debug()).toContain("CREATED");
    expect(debug()).toContain("no"); // Live injection enabled: no

    // Flip to RUNNING → buttons immediately say "Inject", debug flips to yes.
    rerender(createElement(DrugStudioPanel, props({ running: true, status: "RUNNING" })));
    expect(getAllByText("Inject").length).toBeGreaterThan(0);
    expect(queryAllByText("Add")).toHaveLength(0);
    expect(debug()).toContain("RUNNING");
    expect(debug()).toContain("yes");
  });

  it("shows an active-drug list with live status, Update Dose and Remove", () => {
    vi.mocked(injectDrug).mockClear();
    const frame = {
      drugs: [
        { id: LIB[0].id, name: LIB[0].name, color: "#fff", viz: "transport", dose: 1.5,
          strength: 1, targets: [], mechanism: "", confidence: "high" },
      ],
    } as unknown as import("../api/types").FrameData;
    const { getByText } = render(
      createElement(DrugStudioPanel, {
        regimen: [{ drug_id: LIB[0].id, dose: 1.5 }],
        onRegimenChange: () => {},
        initialDrugs: LIB,
        simId: 7,
        running: true,
        frame,
      }),
    );
    // Live drug status comes from the treated frame.
    expect(getByText(/Acting/)).toBeTruthy();
    getByText("Update Dose").click();
    expect(injectDrug).toHaveBeenCalledWith(7, { action: "update", drug_id: LIB[0].id, dose: 1.5 });
    getByText("Remove").click();
    expect(injectDrug).toHaveBeenCalledWith(7, { action: "remove", drug_id: LIB[0].id });
  });
});
