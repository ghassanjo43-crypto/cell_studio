// The mapping layer: convert real simulation frame data into concrete visual
// parameters (particle counts, activity levels, colours). This is the single place
// where "biology → graphics" is defined, so every rendered element is provably
// data-driven. Pure and unit-tested.

import type { FrameData } from "../../../api/types";
import { statusColor } from "../../theme";

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
/** Saturating map x -> [0, cap) that grows quickly then plateaus (Michaelis-like). */
const saturate = (x: number, half: number, cap: number) => cap * (x / (x + half));

export interface CellVisual {
  radius: number;
  color: string;
  integrity: number; // membrane integrity 0..1
  permeability: number; // = integrity, gates transport
  transportActivity: number; // phenotype.transport, clamped [0.3, 2.2]
  membraneRepair: number; // phenotype.membrane (>1 = repairing)
  metabolicActivity: number; // 0..1 (growth-rate derived; caller supplies)

  // Data-driven molecular counts (pre-LOD; renderer scales by a detail factor).
  glucoseCount: number; // extracellular glucose streaming to transporters
  atpCount: number; // ATP produced by metabolism / held in compartments
  ribosomeCount: number; // translation machinery ∝ protein synthesis
  transcriptionFoci: number; // active transcription ∝ mRNA
  metaboliteCount: number; // internal metabolite pool
  vesicleCount: number; // membrane-lipid trafficking ∝ membrane synthesis
  crowdingCount: number; // macromolecular crowding of the cytoplasm ∝ biomass + protein
  proteinCount: number; // free folded proteins ∝ protein synthesis
  enzymeCount: number; // metabolic enzymes ∝ metabolic activity + internal substrate pool

  // Genome
  replicationProgress: number;
  replicating: boolean;
  replicationComplete: boolean;

  // Signalling (optional; only for the signalling scenario)
  signalling?: {
    starvation: number;
    growth: number;
    membraneStress: number;
    survival: boolean;
    mode: string | null;
  };

  // Compartment ATP pools (optional; compartment scenario)
  compartments?: Record<string, { energy: number; stressed: boolean }>;
}

export function radiusForMass(mass: number): number {
  return 0.6 + Math.cbrt(Math.max(mass, 0)) * 0.7;
}

/**
 * Build the full visual state for a cell frame. `metabolicActivity` (0..1) is the
 * growth-rate signal the caller derives from the biomass slope across frames — a
 * real, data-driven measure of how hard metabolism is working.
 */
export function buildCellVisual(frame: FrameData, metabolicActivity = 0): CellVisual {
  const mass = frame.mass ?? 0.001;
  const integrity = clamp(frame.membrane_integrity ?? 1, 0, 1);
  const transport = clamp(frame.phenotype?.transport ?? 1, 0.3, 2.2);
  const membraneRepair = frame.phenotype?.membrane ?? 1;
  const env = frame.env_glucose ?? frame.nutrients?.glc?.surface ?? 0;
  const pool = frame.pool_glucose ?? 0;
  const protein = frame.expression?.protein ?? 0;
  const mrna = frame.expression?.mrna ?? 0;
  const act = clamp(metabolicActivity, 0, 1);
  const alive = frame.alive !== false;

  // ATP: from metabolic activity, boosted by any compartment energy pool.
  const compEnergy = frame.compartments
    ? Object.values(frame.compartments).reduce((s, c) => s + c.energy, 0)
    : 0;
  const atp = alive ? Math.round(saturate(act * 30 + compEnergy, 12, 46)) : 0;

  return {
    radius: radiusForMass(mass),
    color: statusColor(frame.status),
    integrity,
    permeability: integrity,
    transportActivity: transport,
    membraneRepair,
    metabolicActivity: act,

    glucoseCount: alive ? Math.round(saturate(env, 6, 50) * (transport / 1.4)) : 0,
    atpCount: atp,
    ribosomeCount: alive ? Math.round(saturate(protein, 360, 64)) : 0,
    transcriptionFoci: alive ? clamp(Math.round(saturate(mrna, 30, 8)), 0, 8) : 0,
    metaboliteCount: alive ? Math.round(saturate(pool, 1.5, 40)) : 0,
    // Vesicles bud during growth and membrane repair (lipid trafficking).
    vesicleCount: alive ? clamp(Math.round((act + Math.max(0, membraneRepair - 1)) * 5), 0, 14) : 0,
    // Macromolecular crowding: the cytoplasm is packed — density tracks biomass + protein.
    // Real cells are extremely crowded (the interior is a solid mass of macromolecules),
    // so this saturates high (many hundreds of instances), scaled down at range/low tiers
    // by the LOD × densityScale factor.
    crowdingCount: alive ? Math.round(saturate(mass * 60 + protein * 0.06, 70, 1000)) : 0,
    proteinCount: alive ? Math.round(saturate(protein, 420, 120)) : 0,
    // Metabolic enzymes: abundant where metabolism is active and substrate is present.
    enzymeCount: alive ? Math.round(saturate(act * 45 + pool * 6, 22, 110)) : 0,

    replicationProgress: clamp(frame.replication?.progress ?? 0, 0, 1),
    replicating: frame.replication?.replicating ?? false,
    replicationComplete: frame.replication?.complete ?? false,

    signalling: frame.signalling
      ? {
          starvation: frame.signalling.signals.starvation,
          growth: frame.signalling.signals.growth,
          membraneStress: frame.signalling.signals.membrane_stress,
          survival: frame.signalling.survival,
          mode: frame.signalling.mode,
        }
      : undefined,
    compartments: frame.compartments,
  };
}

/**
 * Growth-rate-derived metabolic activity (0..1) from the biomass slope between two
 * frames — how fast the cell is building biomass, i.e. how active metabolism is.
 */
export function metabolicActivityFrom(
  massNow: number,
  massBefore: number,
  dt: number,
): number {
  if (dt <= 0 || massNow <= 0) return 0;
  const relGrowth = (massNow - massBefore) / dt / massNow; // specific growth rate
  return clamp(relGrowth * 12, 0, 1);
}
