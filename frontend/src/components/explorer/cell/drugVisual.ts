// The DrugVisualController: maps a treated frame's active-drug channels + the biological
// variables they affect into a set of renderer "response states" (intensities 0..1). This
// is the single place that decides how a drug reads on screen, so every effect is provably
// data-driven — nothing is invented. Effects ramp with the drug's PK strength and the
// resulting biology (progressive onset) and fall back to zero on washout (recovery).
//
// Pure and unit-tested; a lightweight React context broadcasts the state to the renderer.

import { createContext, useContext } from "react";
import type { FrameData } from "../../../api/types";

export interface DrugVisualState {
  active: boolean;
  // Membrane disruptor / oxidative.
  membraneDamage: number; // wrinkles, rupture regions, membrane flashes
  membraneRepair: number; // repair vesicles rush to damage
  leakage: number; // leakage particles escaping the envelope
  // ATP inhibitor.
  motion: number; // GLOBAL molecular-motion multiplier (1 = normal, <1 = slowed)
  atpDim: number; // ATP particles dim
  ribosomeStall: number; // ribosomes gradually stop
  // Transport inhibitor.
  transportBlock: number; // transporter animation slows + glucose accumulates outside
  starvation: number; // starvation signalling intensifies (passthrough of the real signal)
  // DNA inhibitor.
  forkFreeze: number; // replication fork freezes
  dnaGlowDown: number; // DNA glow decreases
  polymeraseFade: number; // polymerase / DNA-binding traffic disappears
  // Oxidative stress.
  ros: number; // ROS particles + oxidation flashes
  mutationSparks: number; // mutation sparks increase near the genome
  tints: string[]; // active-drug colours (used for flashes)
}

export const INACTIVE_DRUG_VISUAL: DrugVisualState = {
  active: false,
  membraneDamage: 0,
  membraneRepair: 0,
  leakage: 0,
  motion: 1,
  atpDim: 0,
  ribosomeStall: 0,
  transportBlock: 0,
  starvation: 0,
  forkFreeze: 0,
  dnaGlowDown: 0,
  polymeraseFade: 0,
  ros: 0,
  mutationSparks: 0,
  tints: [],
};

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/**
 * Build the drug visual-response state from a frame. Reads the active drugs' channels
 * (which effect the drug has) and the *resulting* biology variables (how strongly it is
 * biting — membrane integrity, phenotype factors, signalling), so the response is grounded
 * in measured state, not asserted.
 */
export function buildDrugVisual(frame: FrameData | null | undefined): DrugVisualState {
  const drugs = frame?.drugs ?? [];
  if (!frame || drugs.length === 0) return INACTIVE_DRUG_VISUAL;

  // Strongest strength among drugs whose effect on `channel` satisfies `pred`.
  const channel = (ch: string, pred: (eff: number) => boolean): number => {
    let s = 0;
    for (const d of drugs) {
      const eff = d.channels?.[ch];
      if (eff !== undefined && pred(eff)) s = Math.max(s, clamp01(d.strength));
    }
    return s;
  };
  const inhibits = (ch: string) => channel(ch, (e) => e < 1);
  const lysisDrug = channel("membrane_lysis", (e) => e > 0);
  const mutagen = channel("mutation", (e) => e > 1);

  const pheno = frame.phenotype ?? {};
  const integrity = frame.membrane_integrity ?? 1;

  // Deviation of the affected biology variable (progressive; recovers as it heals).
  const membraneVar = clamp01(1 - integrity);
  const transportVar = clamp01(1 - (pheno.transport ?? 1));
  const metabolismVar = clamp01(1 - (pheno.metabolism ?? 1));

  const membraneDrug = Math.max(lysisDrug, inhibits("membrane"));
  const membraneDamage = membraneDrug > 0 ? clamp01(0.35 * membraneDrug + 0.9 * membraneVar) : 0;
  const membraneRepair = membraneDrug > 0 ? clamp01((pheno.membrane ?? 1) - 1) : 0;

  const metabolismDrug = inhibits("metabolism");
  const atpDim = metabolismDrug > 0 ? clamp01(0.4 * metabolismDrug + 0.9 * metabolismVar) : 0;
  const motion = 1 - 0.6 * atpDim;

  const expressionDrug = inhibits("expression");
  const ribosomeStall = clamp01(Math.max(expressionDrug, 0.7 * atpDim));

  const transportDrug = inhibits("transport");
  const transportBlock = transportDrug > 0 ? clamp01(0.4 * transportDrug + 0.9 * transportVar) : 0;

  const replicationDrug = inhibits("replication");
  const forkFreeze = clamp01(replicationDrug);
  const dnaGlowDown = clamp01(Math.max(replicationDrug, expressionDrug));
  const polymeraseFade = forkFreeze;

  const ros = clamp01(mutagen);

  return {
    active: true,
    membraneDamage,
    membraneRepair,
    leakage: membraneDamage,
    motion,
    atpDim,
    ribosomeStall,
    transportBlock,
    starvation: frame.signalling?.signals.starvation ?? 0,
    forkFreeze,
    dnaGlowDown,
    polymeraseFade,
    ros,
    mutationSparks: ros,
    tints: drugs.map((d) => d.color),
  };
}

// Context so any renderer component can read the current response without prop-drilling.
const DrugFxContext = createContext<DrugVisualState>(INACTIVE_DRUG_VISUAL);
export const DrugFxProvider = DrugFxContext.Provider;
export function useDrugFx(): DrugVisualState {
  return useContext(DrugFxContext);
}
