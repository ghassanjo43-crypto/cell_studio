// Scientific narration — the biological story generated *entirely from simulation
// state*. Pure: scans the recorded frames + events and emits captioned lines when
// notable things change (replication start/progress, transport, mutation, survival
// mode, division, death, colony events, …). Never invents biology; every line is a
// statement about a value or event that actually occurred.
//
// The narration MODE only changes phrasing/verbosity, not the facts.

import type { Frame, SimEvent } from "../../../api/types";

export type NarrationMode = "research" | "teaching" | "presentation" | "investor";

export interface NarrationLine {
  step: number;
  kind: string;
  text: string;
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Pick a phrasing variant by mode (falls back to teaching). */
function say(mode: NarrationMode, v: { research?: string; teaching: string; investor?: string }): string {
  if (mode === "research" && v.research) return v.research;
  if (mode === "investor" && v.investor) return v.investor;
  return v.teaching; // teaching + presentation share the plain voice
}

function eventText(e: SimEvent, mode: NarrationMode): string | null {
  switch (e.type) {
    case "mutation":
      return say(mode, {
        research: `Mutation detected: ${e.data.target ?? "genotype"} changed.`,
        teaching: "A mutation has occurred in the genome.",
        investor: "The evolutionary engine introduced a heritable mutation.",
      });
    case "replication_start":
      return say(mode, { teaching: "DNA replication has started." });
    case "replication_complete":
      return say(mode, { teaching: "DNA replication is complete." });
    case "division":
      return say(mode, {
        research: `Cell division (cytokinesis) at step ${e.step}; genome partitioned to two daughters.`,
        teaching: "Cytokinesis has completed — the daughter cells inherited the genome.",
        investor: "The synthetic cell autonomously divided, passing its designed genome to two daughters.",
      });
    case "survival_mode_entered":
      return say(mode, {
        research: "Signalling crossed threshold — survival mode engaged (transport up, replication paused).",
        teaching: "The cell has entered survival mode.",
        investor: "Adaptive signalling triggered a survival response — the cell reprogrammed itself to endure stress.",
      });
    case "survival_mode_exited":
      return say(mode, { teaching: "The cell has exited survival mode." });
    case "membrane_rupture":
      return say(mode, { teaching: "The membrane has ruptured." });
    case "death":
      return say(mode, {
        research: `The cell died at step ${e.step}.`,
        teaching: "The cell has died.",
        investor: "The digital twin reached the end of its viable lifespan.",
      });
    case "clone_expansion":
      return say(mode, {
        research: `Clone #${e.data.lineage ?? "?"} is expanding (${e.data.size ?? "?"} cells).`,
        teaching: "A clone is expanding across the population.",
        investor: "Natural selection is favouring a fitter lineage — it is outcompeting the others.",
      });
    case "colony_founded":
      return null; // too frequent at t0 to narrate individually
    case "colony_extinct":
      return say(mode, { teaching: "A colony has gone extinct." });
    case "biofilm_confluent":
      return say(mode, { teaching: "The biofilm has become confluent." });
    case "population_extinct":
      return say(mode, {
        research: "All cells died — the population collapsed.",
        teaching: "The population has collapsed.",
        investor: "The culture exhausted its resources and the population collapsed — a predicted outcome.",
      });
    default:
      return null;
  }
}

function singleCellDeltas(
  prev: Frame["data"], curr: Frame["data"], step: number, mode: NarrationMode, out: NarrationLine[],
): void {
  const p = (k: string, t: string) => out.push({ step, kind: k, text: t });

  // Status transitions.
  if (curr.status !== prev.status) {
    if (curr.status === "GROWING") p("status", say(mode, {
      research: "Status: growing — metabolism is producing biomass and ATP.",
      teaching: "The cell is growing.",
      investor: "The cell is thriving — biomass and ATP output are rising.",
    }));
    else if (curr.status === "STRESSED") p("status", say(mode, { teaching: "The cell is under stress." }));
    else if (curr.status === "DYING") p("status", say(mode, { teaching: "The cell is dying." }));
  }

  // Transport ramp-up.
  const tPrev = prev.phenotype?.transport ?? 1;
  const tCurr = curr.phenotype?.transport ?? 1;
  if (tCurr > 1.3 && tPrev <= 1.3) {
    p("transport", say(mode, {
      research: `Transport up-regulated to ${tCurr.toFixed(2)}× — transporters are scavenging glucose.`,
      teaching: "The membrane transporters are actively importing glucose.",
      investor: "Transport machinery scaled up to import more nutrient.",
    }));
  }

  // ATP / growth-rate increase (from the biomass slope).
  const dt = Math.max(1e-6, (curr.mass ?? 0) - (prev.mass ?? 0));
  if (dt > 0) {
    const gPrev = prev.mass ?? 0;
    const rel = gPrev > 0 ? ((curr.mass ?? 0) - gPrev) / gPrev : 0;
    if (rel > 0.03 && (prev.status !== "GROWING")) {
      p("atp", say(mode, { teaching: "ATP production has increased.", research: "Specific growth rate rising — ATP flux increasing." }));
    }
  }

  // Replication milestones.
  const rp = prev.replication;
  const rc = curr.replication;
  if (rc?.replicating && !rp?.replicating) {
    p("replication", say(mode, {
      research: "DNA replication initiated — a replication fork is traversing the chromosome.",
      teaching: "DNA replication has started.",
      investor: "The cell began copying its genome ahead of division.",
    }));
  }
  if (rc?.replicating) {
    const milestones = [0.25, 0.5, 0.75];
    for (const m of milestones) {
      if ((rc.progress ?? 0) >= m && (rp?.progress ?? 0) < m) {
        p("replication", `Replication is now ${pct(rc.progress)} complete.`);
      }
    }
  }
  if (rc?.complete && !rp?.complete) {
    p("replication", say(mode, { teaching: "DNA replication is complete — the cell is ready to divide." }));
  }

  // Membrane integrity thresholds.
  const iPrev = prev.membrane_integrity ?? 1;
  const iCurr = curr.membrane_integrity ?? 1;
  if (iCurr < 0.5 && iPrev >= 0.5) {
    p("membrane", say(mode, {
      research: `Membrane integrity dropped to ${pct(iCurr)} — repair may not keep pace.`,
      teaching: "Membrane integrity is dropping.",
    }));
  }
}

function aggregateDeltas(
  prev: Frame["data"], curr: Frame["data"], step: number, mode: NarrationMode, out: NarrationLine[],
): void {
  const p = (k: string, t: string) => out.push({ step, kind: k, text: t });
  const cp = curr.petri;
  const pp = prev.petri;
  if (cp && pp) {
    // Occupancy milestones.
    for (const m of [0.25, 0.5, 0.75]) {
      if (cp.occupancy >= m && pp.occupancy < m) {
        p("colony", say(mode, {
          research: `Dish occupancy reached ${pct(cp.occupancy)} — colonies are merging.`,
          teaching: "The colonies are spreading across the dish.",
          investor: "The colony is expanding rapidly across the culture.",
        }));
      }
    }
  }
  const cop = curr.population;
  const pop = prev.population;
  if (cop && pop && cop.dominant_lineage !== pop.dominant_lineage && cop.dominant_lineage != null) {
    p("colony", say(mode, {
      research: `Lineage ${cop.dominant_lineage} became dominant (${pct(cop.dominant_fraction)}).`,
      teaching: "A new lineage has become dominant.",
      investor: "Selection shifted dominance to a fitter lineage.",
    }));
  }
}

/** Build the full narration log for a run (chronological). */
export function buildNarrationLog(frames: Frame[], events: SimEvent[], mode: NarrationMode): NarrationLine[] {
  const out: NarrationLine[] = [];
  for (let i = 1; i < frames.length; i++) {
    const prev = frames[i - 1].data;
    const curr = frames[i].data;
    const step = frames[i].step;
    if (curr.petri || curr.population) aggregateDeltas(prev, curr, step, mode, out);
    else singleCellDeltas(prev, curr, step, mode, out);
  }
  for (const e of events) {
    const text = eventText(e, mode);
    if (text) out.push({ step: e.step, kind: e.type, text });
  }
  out.sort((a, b) => a.step - b.step);
  // Bound memory: keep the most recent lines.
  return out.length > 400 ? out.slice(out.length - 400) : out;
}

/** The narration lines that have occurred up to (and including) the given step. */
export function narrationUpTo(log: NarrationLine[], step: number, limit = 40): NarrationLine[] {
  const shown = log.filter((l) => l.step <= step);
  return shown.slice(Math.max(0, shown.length - limit));
}
