// The Drug Effect Storyboard engine: for the active drug, produce the ordered cascade of
// biological responses (target → primary → secondary → tertiary → fate) with each stage's
// progress read from an existing simulation variable (via the DrugVisualController and the
// frame's own fields). Nothing here is invented — a stage only advances because a measured
// variable moved. Pure and unit-tested.

import type { FrameData } from "../../api/types";
import { buildDrugVisual, type DrugVisualState } from "../explorer/cell/drugVisual";

export type StageStatus = "pending" | "active" | "done";

export interface StoryStage {
  key: string;
  label: string;
  progress: number; // 0..1, from a real variable (drives the animated bar)
  status: StageStatus;
}

export interface Storyboard {
  drugId: string;
  drugName: string;
  color: string;
  primaryTarget: string;
  stages: StoryStage[];
  currentIndex: number;
  currentLabel: string; // current biological response
  nextLabel: string | null; // next predicted response
  fate: string; // predicted fate
  eta: string; // estimated time to recovery or death
  otherActive: number; // how many further drugs are also acting
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

type Getter = (fx: DrugVisualState, frame: FrameData, strength: number) => number;
interface Template {
  target: string;
  fate: string;
  lethalByIntegrity: boolean; // ETA extrapolates membrane integrity → 0
  stages: { key: string; label: string; get: Getter }[];
}

// Classify a drug by the channels it acts on (order matters — most specific first).
export function classifyDrug(channels: Record<string, number> | undefined): string {
  const ch = channels ?? {};
  if ((ch.mutation ?? 1) > 1) return "oxidative";
  if (ch.replication !== undefined && ch.replication < 1) return "dna";
  if (ch.transport !== undefined && ch.transport < 1) return "transport";
  if (ch.expression !== undefined && ch.expression < 1) return "expression";
  if (ch.metabolism !== undefined && ch.metabolism < 1) return "atp";
  if ((ch.membrane_lysis ?? 0) > 0) return "disruptor";
  if (ch.membrane !== undefined && ch.membrane < 1) return "wall";
  if (ch.signalling !== undefined && ch.signalling < 1) return "signalling";
  return "generic";
}

const integrity = (f: FrameData) => f.membrane_integrity ?? 1;
const dead = (f: FrameData) => f.alive === false;

const TEMPLATES: Record<string, Template> = {
  wall: {
    target: "Cell-wall / membrane synthesis",
    fate: "Lysis (cell ruptures)",
    lethalByIntegrity: true,
    stages: [
      { key: "synth", label: "Wall synthesis slows", get: (_fx, _f, s) => s },
      { key: "repair", label: "Repair vesicles increase", get: (fx) => fx.membraneRepair },
      { key: "weaken", label: "Membrane weakens", get: (_fx, f) => (1 - integrity(f)) * 1.4 },
      { key: "rupture", label: "Rupture zones appear", get: (_fx, f) => (0.55 - integrity(f)) / 0.35 },
      { key: "lysis", label: "Lysis", get: (_fx, f) => (dead(f) ? 1 : (0.15 - integrity(f)) / 0.15) },
    ],
  },
  disruptor: {
    target: "Plasma membrane",
    fate: "Lysis (cell ruptures)",
    lethalByIntegrity: true,
    stages: [
      { key: "damage", label: "Membrane integrity falls", get: (fx) => fx.membraneDamage },
      { key: "repair", label: "Repair vesicles rush in", get: (fx) => fx.membraneRepair },
      { key: "rupture", label: "Rupture zones appear", get: (_fx, f) => (0.55 - integrity(f)) / 0.35 },
      { key: "lysis", label: "Leakage → lysis", get: (_fx, f) => (dead(f) ? 1 : (0.15 - integrity(f)) / 0.15) },
    ],
  },
  dna: {
    target: "Replication fork / genome",
    fate: "Division arrest (non-lethal)",
    lethalByIntegrity: false,
    stages: [
      { key: "fork", label: "Replication fork stalls", get: (fx) => fx.forkFreeze },
      { key: "poly", label: "Polymerases disappear", get: (fx) => fx.polymeraseFade },
      { key: "glow", label: "DNA glow fades", get: (fx) => fx.dnaGlowDown },
      { key: "nodiv", label: "No division", get: (fx) => fx.forkFreeze },
    ],
  },
  atp: {
    target: "Central metabolism / ATP",
    fate: "Death (energy crisis)",
    lethalByIntegrity: true,
    stages: [
      { key: "dim", label: "ATP output dims", get: (fx) => fx.atpDim },
      { key: "slow", label: "Molecular transport slows", get: (fx) => (1 - fx.motion) / 0.6 },
      { key: "ribo", label: "Ribosomes stop", get: (fx) => fx.ribosomeStall },
      { key: "crisis", label: "Energy crisis", get: (fx, f) => (f.signalling?.survival ? 1 : (fx.atpDim - 0.6) / 0.4) },
    ],
  },
  transport: {
    target: "Membrane transporters",
    fate: "Starvation death",
    lethalByIntegrity: true,
    stages: [
      { key: "accum", label: "Glucose accumulates outside", get: (fx) => fx.transportBlock },
      { key: "inactive", label: "Transporters become inactive", get: (fx) => fx.transportBlock * 1.15 },
      { key: "starv", label: "Starvation signalling increases", get: (fx) => fx.starvation },
      { key: "death", label: "Starvation → death", get: (fx, f) => (f.signalling?.survival ? 1 : (fx.starvation - 0.6) / 0.4) },
    ],
  },
  expression: {
    target: "Ribosomes / transcription",
    fate: "Growth arrest → death",
    lethalByIntegrity: true,
    stages: [
      { key: "stall", label: "Translation/transcription stalls", get: (fx) => fx.ribosomeStall },
      { key: "protein", label: "Protein synthesis collapses", get: (fx) => fx.ribosomeStall * 0.95 },
      { key: "growth", label: "Growth stalls", get: (fx, f) => (f.signalling?.survival ? 1 : fx.ribosomeStall * 0.8) },
    ],
  },
  oxidative: {
    target: "Whole cell (lipids · proteins · DNA)",
    fate: "Death (oxidative damage)",
    lethalByIntegrity: true,
    stages: [
      { key: "ros", label: "ROS appears", get: (fx) => fx.ros },
      { key: "spark", label: "Mutation sparks", get: (fx) => fx.mutationSparks },
      { key: "oxid", label: "Membrane oxidation", get: (fx) => fx.membraneDamage },
      { key: "dnadmg", label: "DNA damage", get: (fx) => fx.ros },
      { key: "death", label: "Cell death", get: (_fx, f) => (dead(f) ? 1 : (0.2 - integrity(f)) / 0.2) },
    ],
  },
  signalling: {
    target: "Signalling network",
    fate: "Adaptation blunted",
    lethalByIntegrity: false,
    stages: [
      { key: "bind", label: "Signal transduction blocked", get: (_fx, _f, s) => s },
      { key: "noadapt", label: "Stress response cannot fire", get: (_fx, _f, s) => s * 0.9 },
    ],
  },
  generic: {
    target: "Target",
    fate: "Cell perturbed",
    lethalByIntegrity: false,
    stages: [
      { key: "bind", label: "Drug binds target", get: (_fx, _f, s) => s },
      { key: "perturb", label: "Pathway perturbed", get: (_fx, _f, s) => s * 0.8 },
    ],
  },
};

function integritySlopePerFrame(history: FrameData[]): number {
  if (history.length < 2) return 0;
  const tail = history.slice(-12);
  const first = integrity(tail[0]);
  const last = integrity(tail[tail.length - 1]);
  return (last - first) / (tail.length - 1);
}

function estimateEta(frame: FrameData, history: FrameData[], tmpl: Template): string {
  if (dead(frame)) return "the cell has died";
  if (!tmpl.lethalByIntegrity) {
    return tmpl.fate.startsWith("Division") ? "no lethal endpoint (division halts)" : "—";
  }
  const slope = integritySlopePerFrame(history);
  const integ = integrity(frame);
  const fateShort = tmpl.fate.toLowerCase().includes("starv")
    ? "starvation death"
    : tmpl.fate.toLowerCase().includes("energy")
      ? "energy-crisis death"
      : "lysis";
  if (slope < -1e-4) {
    const steps = Math.max(1, Math.round(integ / -slope));
    return steps < 40 ? `imminent — ~${steps} steps to ${fateShort}` : `~${steps} steps to ${fateShort}`;
  }
  if (slope > 1e-4) return "recovering (integrity rising)";
  if (frame.signalling?.survival) return "stressed — death likely if maintained";
  return "stable for now";
}

/**
 * Build the storyboard for the strongest active drug in the frame (null if none). Pass the
 * recent frame history to get a data-derived time-to-death/recovery estimate.
 */
export function buildStoryboard(frame: FrameData | null | undefined, history: FrameData[] = []): Storyboard | null {
  const drugs = frame?.drugs ?? [];
  if (!frame || drugs.length === 0) return null;
  const drug = [...drugs].sort((a, b) => b.strength - a.strength)[0];
  const tmpl = TEMPLATES[classifyDrug(drug.channels)] ?? TEMPLATES.generic;
  const fx = buildDrugVisual(frame);
  const strength = clamp01(drug.strength);

  const stages: StoryStage[] = tmpl.stages.map((s) => ({
    key: s.key,
    label: s.label,
    progress: clamp01(s.get(fx, frame, strength)),
    status: "pending",
  }));

  // The furthest-reached stage is the current response; earlier ones are done.
  let currentIndex = 0;
  stages.forEach((s, i) => {
    if (s.progress > 0.12) currentIndex = i;
  });
  stages.forEach((s, i) => {
    if (i < currentIndex) s.status = "done";
    else if (i === currentIndex) s.status = s.progress >= 0.9 ? "done" : "active";
    else s.status = "pending";
  });

  const nextIndex = currentIndex + 1 < stages.length ? currentIndex + 1 : -1;
  return {
    drugId: drug.id,
    drugName: drug.name,
    color: drug.color,
    primaryTarget: tmpl.target,
    stages,
    currentIndex,
    currentLabel: stages[currentIndex].label,
    nextLabel: nextIndex >= 0 ? stages[nextIndex].label : null,
    fate: tmpl.fate,
    eta: estimateEta(frame, history, tmpl),
    otherActive: drugs.length - 1,
  };
}
