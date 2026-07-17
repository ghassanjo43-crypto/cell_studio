// Pure inspection layer for the Cell Explorer. Given an object id and the current
// frame, produce the read-out shown when the user clicks a biological structure:
// current state, numerical values, and a grounded biological explanation.
//
// Everything here is derived from actual simulation data (never invented) so it can
// be unit-tested without React or Three.

import type { FrameData } from "../../api/types";

export interface InspectValue {
  label: string;
  value: string;
}

export interface InspectInfo {
  id: string;
  title: string;
  subtitle?: string;
  //: A short (one-line) scientific description for the hover tooltip.
  tip?: string;
  values: InspectValue[];
  explanation: string;
}

/** Stable ids for the clickable / hoverable biological structures. */
export type ObjectId =
  | "membrane"
  | "lipid"
  | "channel"
  | "receptor"
  | "cytosol"
  | "nucleoid"
  | "fork"
  | "mutation"
  | "division"
  | "transport"
  | "ribosome"
  | "protein"
  | "enzyme"
  | "atp"
  | "glucose"
  | "metabolite"
  | "vesicle"
  | "nutrients"
  | "signalling"
  | "population"
  | "petri"
  | `energy.${string}`
  | `cell.${number}`
  | `petricell.${number}`;

function fmt(v: number, digits = 3): string {
  if (!isFinite(v)) return "—";
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1000 || a < 0.01) return v.toExponential(2);
  if (a >= 10) return v.toFixed(1);
  return v.toFixed(digits);
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

/**
 * The short scientific description shown in the hover tooltip: an explicit `tip` if the
 * structure defines one, otherwise the first sentence of its full explanation. Pure so
 * it can be unit-tested.
 */
export function hoverTip(info: InspectInfo): string {
  if (info.tip) return info.tip;
  const first = info.explanation.split(/(?<=[.!?])\s/)[0] ?? info.explanation;
  return first.length > 160 ? first.slice(0, 157) + "…" : first;
}

/** The transport phenotype factor (1.0 = baseline); >1 means up-regulated uptake. */
export function transportActivity(frame: FrameData): number {
  return frame.phenotype?.transport ?? 1.0;
}

/** Which structures are present (clickable) for this frame's scenario. */
export function presentObjects(frame: FrameData | null): ObjectId[] {
  if (!frame) return [];
  if (frame.petri) return ["petri"]; // dish: cells are clicked in-scene
  if (frame.population) return ["population"]; // colony: cells are clicked in-scene
  const ids: ObjectId[] = ["membrane", "cytosol", "nucleoid", "transport"];
  if (frame.field_glc || frame.nutrients) ids.push("nutrients");
  if (frame.signalling) ids.push("signalling");
  if (frame.compartments) {
    for (const name of Object.keys(frame.compartments)) ids.push(`energy.${name}`);
  }
  return ids;
}

/** Build the inspector read-out for a clicked structure. Returns null if absent. */
export function buildInspect(id: ObjectId, frame: FrameData | null): InspectInfo | null {
  if (!frame) return null;

  if (id === "petri") {
    const p = frame.petri;
    if (!p) return null;
    return {
      id,
      title: "Petri dish",
      subtitle: `${p.alive} cells · ${p.colonies}/${p.n_clones} colonies`,
      values: [
        { label: "living cells", value: `${p.alive}` },
        { label: "occupancy", value: pct(p.occupancy) },
        { label: "colonies alive", value: `${p.colonies} / ${p.n_clones}` },
        { label: "dominant clone", value: p.dominant_clone >= 0 ? `#${p.dominant_clone} (${pct(p.dominant_fraction)})` : "—" },
        { label: "births / deaths", value: `${p.born} / ${p.died}` },
        { label: "generations", value: `${p.generations}` },
        { label: "total nutrient", value: fmt(p.total_nutrient) },
        { label: "mean transport", value: `${fmt(p.mean_genotype.transport ?? 1)}×` },
      ],
      explanation:
        "A spatial lab culture: founder colonies expand into empty sites, competing " +
        "for a diffusing nutrient. Colony cores deplete their neighbourhood (nutrient-" +
        "limited) while fronts advance; fitter clones dominate and weaker colonies go " +
        "extinct. Toggle the heat maps to see population, nutrient, mutation and ATP fields.",
    };
  }

  if (id.startsWith("petricell.")) {
    const i = Number(id.slice("petricell.".length));
    const p = frame.petri;
    if (!p || i < 0 || i >= p.cells.count) return null;
    const c = p.cells;
    // Local nutrient from the coarse field at this cell's bin.
    const [gh, gw] = p.grid;
    const [rows, cols] = p.hm_size;
    const br = Math.max(0, Math.min(rows - 1, Math.floor((c.y[i] / gh) * rows)));
    const bc = Math.max(0, Math.min(cols - 1, Math.floor((c.x[i] / gw) * cols)));
    const localNutrient = p.heatmaps.nutrient[br * cols + bc];
    return {
      id,
      title: `Cell @ (${c.x[i]}, ${c.y[i]})`,
      subtitle: `clone #${c.clone[i]}`,
      values: [
        { label: "clone", value: `#${c.clone[i]}` },
        { label: "position", value: `${c.x[i]}, ${c.y[i]}` },
        { label: "ATP energy", value: fmt(c.energy[i]) },
        { label: "local nutrient", value: fmt(localNutrient) },
        { label: "mutations", value: `${c.mut[i]}` },
      ],
      explanation:
        "One cell in the dish. Its ATP energy reflects the local nutrient it can reach; " +
        "its mutation count is the load accumulated along its lineage. Enter it to view " +
        "the full single-cell explorer for a representative cell of this colony.",
    };
  }

  if (id === "population") {
    const p = frame.population;
    if (!p) return null;
    return {
      id,
      title: "Colony",
      subtitle: `${p.alive} alive · ${p.dead} dead`,
      values: [
        { label: "living cells", value: `${p.alive}` },
        { label: "total ever", value: `${p.total_ever}` },
        { label: "births / deaths", value: `${p.born} / ${p.died}` },
        { label: "generations", value: `${p.generations}` },
        { label: "clones", value: `${p.lineages}` },
        { label: "dominant", value: p.dominant_lineage ? `#${p.dominant_lineage} (${pct(p.dominant_fraction)})` : "—" },
        { label: "medium glucose", value: `${fmt(p.medium_glucose)} mmol` },
        { label: "total biomass", value: `${fmt(p.total_biomass)} gDW` },
      ],
      explanation:
        "Founder cells grow, divide into daughter cells, and compete for one shared " +
        "glucose pool. Faster/fitter genotypes divide more and their clones expand; " +
        "when glucose is exhausted, cells starve and lineages go extinct.",
    };
  }

  if (id.startsWith("cell.")) {
    const cellId = Number(id.slice("cell.".length));
    const cell = frame.population?.cells.find((c) => c.id === cellId);
    if (!cell) return null;
    return {
      id,
      title: `Cell #${cell.id}`,
      subtitle: cell.alive ? `clone #${cell.root}` : "dead",
      values: [
        { label: "lineage", value: cell.lineage },
        { label: "clone (root)", value: `#${cell.root}` },
        { label: "generation", value: `${cell.generation}` },
        { label: "biomass", value: `${fmt(cell.mass)} gDW` },
        { label: "state", value: cell.alive ? "alive" : "dead" },
      ],
      explanation:
        "A single cell in the colony. Its lineage id records its division history from " +
        "the founder clone; it inherits the parent genotype (with mutation) and competes " +
        "for shared glucose with every other cell.",
    };
  }

  if (id === "membrane") {
    const integrity = frame.membrane_integrity;
    const repairing = (frame.phenotype?.membrane ?? 1) > 1.05;
    return {
      id,
      title: "Membrane",
      subtitle: "phospholipid bilayer",
      values: [
        { label: "integrity", value: pct(integrity) },
        { label: "repair drive", value: fmt(frame.phenotype?.membrane ?? 1) + "×" },
        { label: "status", value: frame.status ?? "—" },
      ],
      explanation:
        "The bilayer encloses the cell and hosts transport proteins. Integrity falls " +
        "under stress and is restored by lipid synthesis; the cell dies if it ruptures." +
        (repairing ? " Repair is currently up-regulated." : ""),
    };
  }

  if (id === "cytosol") {
    return {
      id,
      title: "Cytosol",
      subtitle: "internal aqueous compartment",
      values: [
        { label: "biomass", value: `${fmt(frame.mass)} gDW` },
        { label: "internal glucose", value: `${fmt(frame.pool_glucose)} mmol` },
        { label: "metabolism", value: frame.metabolism_status ?? "—" },
      ],
      explanation:
        "Imported nutrients accumulate in the cytosol, where central metabolism " +
        "converts them to biomass and ATP. Particle density here tracks the internal " +
        "glucose pool.",
    };
  }

  if (id === "nucleoid") {
    const rep = frame.replication;
    return {
      id,
      title: "Nucleoid",
      subtitle: "genome / chromosome",
      values: [
        { label: "generation", value: `${frame.generation}` },
        { label: "divisions", value: `${frame.divisions}` },
        { label: "replication", value: rep ? pct(rep.progress) : "—" },
        { label: "state", value: rep?.replicating ? "replicating" : rep?.complete ? "complete" : "idle" },
      ],
      explanation:
        "The chromosome carries the genome. When the cell reaches initiation mass a " +
        "replication fork traverses it; once complete the cell can divide. Mutation " +
        "events perturb genotype factors that shape phenotype.",
    };
  }

  if (id === "transport") {
    const act = transportActivity(frame);
    return {
      id,
      title: "Transport proteins",
      subtitle: "membrane transporters",
      values: [
        { label: "activity", value: `${fmt(act)}×` },
        { label: "medium glucose", value: `${fmt(frame.env_glucose)} mM` },
        { label: "internal glucose", value: `${fmt(frame.pool_glucose)} mmol` },
        { label: "limiting", value: frame.limiting ? frame.limiting.replace("met.", "") : "—" },
      ],
      explanation:
        "Transporters import nutrients across the membrane following Michaelis–Menten " +
        "kinetics. Their visible activity scales with the transport phenotype factor, " +
        "which signalling raises under starvation.",
    };
  }

  if (id === "nutrients") {
    const values: InspectValue[] = [];
    if (frame.nutrients) {
      for (const [n, v] of Object.entries(frame.nutrients)) {
        values.push({ label: `${n} surface`, value: `${fmt(v.surface)} mM` });
      }
    } else {
      values.push({ label: "medium glucose", value: `${fmt(frame.env_glucose)} mM` });
    }
    if (frame.field_glc && frame.field_glc.length > 1) {
      const surf = frame.field_glc[0];
      const bulk = frame.field_glc[frame.field_glc.length - 1];
      values.push({ label: "gradient", value: `${fmt(surf)} → ${fmt(bulk)} mM` });
    }
    if (frame.limiting) values.push({ label: "limiting", value: frame.limiting.replace("met.", "") });
    return {
      id,
      title: "Nutrient field",
      subtitle: "extracellular gradient",
      values,
      explanation:
        "Nutrients diffuse through the medium while surface uptake depletes them near " +
        "the cell, forming a radial gradient (inner shells lower than the bulk). The " +
        "scarcest resource limits growth.",
    };
  }

  if (id === "signalling") {
    const s = frame.signalling;
    if (!s) return null;
    return {
      id,
      title: "Signalling network",
      subtitle: s.survival ? "survival mode active" : "sensing",
      values: [
        { label: "mode", value: s.mode ?? "—" },
        { label: "starvation", value: fmt(s.signals.starvation) },
        { label: "growth", value: fmt(s.signals.growth) },
        { label: "membrane stress", value: fmt(s.signals.membrane_stress) },
      ],
      explanation:
        "Receptors sense nutrient status and membrane stress and integrate them into " +
        "signalling variables. When starvation crosses threshold the cell enters " +
        "survival mode: slowing replication, boosting transport and membrane repair.",
    };
  }

  if (id === "lipid") {
    return {
      id,
      title: "Lipid bilayer",
      subtitle: "membrane leaflets",
      tip: "Two leaflets of phospholipids in constant thermal motion — the sheet that forms the membrane.",
      values: [
        { label: "integrity", value: pct(frame.membrane_integrity) },
        { label: "repair drive", value: fmt(frame.phenotype?.membrane ?? 1) + "×" },
        { label: "status", value: frame.status ?? "—" },
      ],
      explanation:
        "The phospholipid bilayer is a fluid mosaic of lipid heads and embedded proteins. Its " +
        "packing (and the visible undulation) loosens as integrity falls under stress and tightens " +
        "as lipid synthesis repairs it.",
    };
  }

  if (id === "channel") {
    return {
      id,
      title: "Glucose channel",
      subtitle: "membrane pore",
      tip: "A passive membrane pore whose aperture tracks membrane integrity, letting glucose diffuse inward.",
      values: [
        { label: "aperture", value: pct(frame.membrane_integrity) },
        { label: "medium glucose", value: `${fmt(frame.env_glucose)} mM` },
        { label: "status", value: frame.status ?? "—" },
      ],
      explanation:
        "Channels are passive pores that let solutes move down their gradient. The rendered aperture " +
        "scales with membrane integrity, so a stressed membrane restricts flux.",
    };
  }

  if (id === "receptor") {
    const s = frame.signalling;
    const values: InspectValue[] = s
      ? [
          { label: "starvation", value: fmt(s.signals.starvation) },
          { label: "growth", value: fmt(s.signals.growth) },
          { label: "membrane stress", value: fmt(s.signals.membrane_stress) },
        ]
      : [
          { label: "medium glucose", value: `${fmt(frame.env_glucose)} mM` },
          { label: "status", value: frame.status ?? "—" },
        ];
    return {
      id,
      title: "Receptor",
      subtitle: "membrane sensor",
      tip: "A membrane sensor that reads nutrient status and membrane stress and relays it to signalling.",
      values,
      explanation:
        "Receptors detect the cell's nutrient and stress state at the surface and feed the signalling " +
        "network, which can switch the cell into survival mode.",
    };
  }

  if (id === "ribosome") {
    return {
      id,
      title: "Ribosome",
      subtitle: "translation machinery",
      tip: "The 60S/40S complex that translates mRNA into protein; its abundance tracks protein synthesis.",
      values: [
        { label: "protein pool", value: fmt(frame.expression?.protein ?? 0) },
        { label: "mRNA", value: fmt(frame.expression?.mrna ?? 0) },
        { label: "metabolism", value: frame.metabolism_status ?? "—" },
      ],
      explanation:
        "Ribosomes translate mRNA into protein. The number rendered scales with the protein-synthesis " +
        "level, and each one is animated with a translation throb.",
    };
  }

  if (id === "protein") {
    return {
      id,
      title: "Protein",
      subtitle: "folded macromolecule",
      tip: "A folded functional macromolecule; the free-protein pool reflects gene expression.",
      values: [
        { label: "protein pool", value: fmt(frame.expression?.protein ?? 0) },
        { label: "mRNA", value: fmt(frame.expression?.mrna ?? 0) },
      ],
      explanation:
        "Free folded proteins carry out the cell's functions. Their density in the cytoplasm reflects " +
        "the current gene-expression (protein) level.",
    };
  }

  if (id === "enzyme") {
    return {
      id,
      title: "Enzyme",
      subtitle: "metabolic catalyst",
      tip: "A metabolic catalyst; enzyme abundance rises with metabolic activity and available substrate.",
      values: [
        { label: "metabolism", value: frame.metabolism_status ?? "—" },
        { label: "internal glucose", value: `${fmt(frame.pool_glucose)} mmol` },
        { label: "biomass", value: `${fmt(frame.mass)} gDW` },
      ],
      explanation:
        "Enzymes catalyse the reactions of central metabolism. Their rendered abundance tracks metabolic " +
        "activity and the internal substrate pool available to them.",
    };
  }

  if (id === "atp") {
    const comp = frame.compartments
      ? Object.values(frame.compartments).reduce((s, c) => s + c.energy, 0)
      : null;
    const values: InspectValue[] = [
      { label: "metabolism", value: frame.metabolism_status ?? "—" },
      { label: "internal glucose", value: `${fmt(frame.pool_glucose)} mmol` },
    ];
    if (comp !== null) values.push({ label: "ATP energy", value: fmt(comp) });
    return {
      id,
      title: "ATP",
      subtitle: "energy currency",
      tip: "Adenosine triphosphate — the cell's energy currency, made by metabolism and spent on growth, transport and repair.",
      values,
      explanation:
        "ATP is produced by central metabolism from imported glucose and distributed outward to power " +
        "biosynthesis, active transport and membrane repair. Its production rate tracks metabolic activity.",
    };
  }

  if (id === "glucose") {
    return {
      id,
      title: "Glucose molecule",
      subtitle: "carbon substrate",
      tip: "The primary carbon/energy substrate, imported by transporters and consumed by metabolism.",
      values: [
        { label: "medium glucose", value: `${fmt(frame.env_glucose)} mM` },
        { label: "internal glucose", value: `${fmt(frame.pool_glucose)} mmol` },
        { label: "transport", value: `${fmt(transportActivity(frame))}×` },
      ],
      explanation:
        "Glucose is imported from the medium across the membrane by transporters, then fed into central " +
        "metabolism. The influx you see scales with the medium concentration and transporter activity.",
    };
  }

  if (id === "metabolite") {
    return {
      id,
      title: "Metabolite",
      subtitle: "metabolic intermediate",
      tip: "Intracellular intermediates flowing through central metabolism toward biomass and ATP.",
      values: [
        { label: "internal glucose", value: `${fmt(frame.pool_glucose)} mmol` },
        { label: "metabolism", value: frame.metabolism_status ?? "—" },
        { label: "biomass", value: `${fmt(frame.mass)} gDW` },
      ],
      explanation:
        "Metabolites are the intermediates of central metabolism. Their internal pool reflects how much " +
        "substrate has been imported and is being processed into biomass and energy.",
    };
  }

  if (id === "vesicle") {
    const repairing = (frame.phenotype?.membrane ?? 1) > 1.05;
    return {
      id,
      title: "Vesicle",
      subtitle: "lipid transport carrier",
      tip: "A membrane-bound carrier trafficking lipids to the surface; budding rises during growth and repair.",
      values: [
        { label: "repair drive", value: fmt(frame.phenotype?.membrane ?? 1) + "×" },
        { label: "integrity", value: pct(frame.membrane_integrity) },
        { label: "status", value: frame.status ?? "—" },
      ],
      explanation:
        "Vesicles carry newly synthesised lipids to the plasma membrane. Trafficking increases during " +
        "growth and when membrane repair is up-regulated." + (repairing ? " Repair is currently active." : ""),
    };
  }

  if (id === "fork") {
    const rep = frame.replication;
    return {
      id,
      title: "Replication fork",
      subtitle: "DNA synthesis",
      tip: "The site where the chromosome is being copied; it traverses the genome once per cell cycle.",
      values: [
        { label: "progress", value: rep ? pct(rep.progress) : "—" },
        { label: "state", value: rep?.replicating ? "replicating" : rep?.complete ? "complete" : "idle" },
        { label: "generation", value: `${frame.generation}` },
      ],
      explanation:
        "At the replication fork the parental DNA is unwound and copied, with the daughter strand built " +
        "behind it. Once the fork completes a full traverse, the cell is ready to divide.",
    };
  }

  if (id === "mutation") {
    const geno = frame.genotype;
    const values: InspectValue[] = geno
      ? Object.entries(geno).slice(0, 3).map(([k, v]) => ({ label: k, value: `${fmt(v)}×` }))
      : [
          { label: "generation", value: `${frame.generation}` },
          { label: "divisions", value: `${frame.divisions}` },
        ];
    return {
      id,
      title: "Mutation site",
      subtitle: "genome variation",
      tip: "A heritable change to a genotype factor; mutations perturb phenotype and pass to daughter cells.",
      values,
      explanation:
        "Mutation events perturb genotype factors (1.0 = unmutated) that scale phenotype — e.g. transport " +
        "or metabolic yield. Changes are inherited by daughter cells and drive evolution across lineages.",
    };
  }

  if (id === "division") {
    const rep = frame.replication;
    return {
      id,
      title: "Division furrow",
      subtitle: "cytokinesis",
      tip: "The constriction furrow that pinches the cell in two once the genome is fully replicated.",
      values: [
        { label: "genome", value: rep?.complete ? "replicated" : rep ? pct(rep.progress) : "—" },
        { label: "divisions", value: `${frame.divisions}` },
        { label: "status", value: frame.status ?? "—" },
      ],
      explanation:
        "After replication completes, a constriction furrow forms at the equator and deepens during " +
        "cytokinesis, pinching the mother cell into two daughters that inherit one chromosome each.",
    };
  }

  if (id.startsWith("energy.")) {
    const name = id.slice("energy.".length);
    const comp = frame.compartments?.[name];
    if (!comp) return null;
    return {
      id,
      title: `Energy · ${name.replace("_", " ")}`,
      subtitle: comp.stressed ? "energy-starved" : "compartment ATP pool",
      values: [
        { label: "ATP energy", value: fmt(comp.energy) },
        { label: "state", value: comp.stressed ? "stressed ⚠" : "sufficient" },
      ],
      explanation:
        "Compartments hold local ATP pools. The cytosol produces energy from " +
        "metabolism; it flows to the nucleoid and membrane zone to power replication " +
        "and repair. A depleted pool throttles the processes it feeds.",
    };
  }

  return null;
}
