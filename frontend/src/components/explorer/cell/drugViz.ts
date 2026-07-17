// Pure mapping for the drug-molecule visualisation: where each drug's particles dock
// inside the cell (by its viz target) and how many appear (by how strongly it is acting).
// Nothing here is decorative — particles only exist for drugs the frame reports active,
// and they gather at the structure the drug actually targets.

import type { ActiveDrug, DrugVizTarget } from "../../../api/types";

export interface DrugDock {
  /** Radius as a fraction of the cell radius where the drug accumulates. */
  radius: number;
  /** Radial spread (0 = tight shell, 1 = filling that region). */
  spread: number;
  /** Flatten toward the DNA ring plane (for the nucleoid-associated drugs). */
  ring: boolean;
}

// Each viz target → where that drug's molecules gather. DNA inhibitors hug the genome
// ring, membrane drugs sit in the membrane, transport inhibitors dock at the surface,
// ribosome inhibitors gather in the ribosome shell, etc.
export const DRUG_DOCK: Record<DrugVizTarget, DrugDock> = {
  dna: { radius: 0.44, spread: 0.12, ring: true },
  membrane: { radius: 0.99, spread: 0.06, ring: false },
  transport: { radius: 0.99, spread: 0.05, ring: false },
  ribosome: { radius: 0.42, spread: 0.35, ring: false },
  protein: { radius: 0.6, spread: 0.5, ring: false },
  signalling: { radius: 0.9, spread: 0.4, ring: false },
  cytoplasm: { radius: 0.5, spread: 0.7, ring: false },
};

export function dockFor(target: DrugVizTarget): DrugDock {
  return DRUG_DOCK[target] ?? DRUG_DOCK.cytoplasm;
}

/** How many drug molecules to draw — scales with how strongly the drug is acting. */
export function drugParticleCount(drug: ActiveDrug, densityScale = 1): number {
  const base = 10 + Math.round(Math.min(2, Math.max(0, drug.strength)) * 26);
  return Math.max(0, Math.round(base * densityScale));
}
