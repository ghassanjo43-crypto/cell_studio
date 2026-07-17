// The Drug Interaction Studio panel: search + browse the drug library, build a regimen,
// inject / update-dose / remove drugs on a RUNNING simulation in real time, watch each
// drug's live status, and read a grounded AI interpretation. Rendered inside the existing
// right-rail accordion — it adds a panel, it does not redesign the workspace.

import { useEffect, useMemo, useRef, useState } from "react";
import { injectDrug, interpretDrug, listDrugs } from "../../api/client";
import type { Drug, DrugDose, DrugInterpretResult, FrameData } from "../../api/types";
import {
  addDrug,
  exportRegimen,
  filterDrugs,
  isActive,
  removeDrug,
  setDose,
} from "./drugStudio";

interface Props {
  regimen: DrugDose[];
  onRegimenChange: (regimen: DrugDose[]) => void;
  onApply?: (regimen: DrugDose[]) => void;
  frame?: FrameData | null; // current (treated) frame
  baselineFrame?: FrameData | null; // untreated baseline for comparison
  initialDrugs?: Drug[]; // injected in tests to skip the fetch
  simId?: number; // when running, live-inject into this simulation
  running?: boolean; // is the simulation currently running?
  status?: string; // the live simulation status (for display / debug)
}

const CONF_COLOR: Record<Drug["confidence"], string> = {
  high: "#4ade80",
  medium: "#fbbf24",
  low: "#fb7185",
};

export function DrugStudioPanel({
  regimen, onRegimenChange, onApply, frame, baselineFrame, initialDrugs, simId, running, status,
}: Props) {
  const [drugs, setDrugs] = useState<Drug[]>(initialDrugs ?? []);
  const [query, setQuery] = useState("");
  const [interpretation, setInterpretation] = useState<DrugInterpretResult | null>(null);
  const [busy, setBusy] = useState(false);
  const live = Boolean(running && simId);
  const liveBaseline = useRef<FrameData | null>(null);

  useEffect(() => {
    if (initialDrugs) return;
    let ok = true;
    listDrugs().then((d) => ok && setDrugs(d)).catch(() => {});
    return () => {
      ok = false;
    };
  }, [initialDrugs]);

  const byId = useMemo(() => new Map(drugs.map((d) => [d.id, d])), [drugs]);
  const activeById = useMemo(
    () => new Map((frame?.drugs ?? []).map((a) => [a.id, a])),
    [frame],
  );
  const shown = useMemo(() => filterDrugs(drugs, query), [drugs, query]);
  const doseOf = (id: string) => regimen.find((r) => r.drug_id === id)?.dose ?? 1;

  // Live status of a drug: acting (with strength) once the worker has applied it, queued
  // right after injection, or staged (design-time, not yet running).
  function statusOf(id: string): { label: string; color: string } {
    const a = activeById.get(id);
    if (a) return { label: `Acting · ${Math.round(Math.min(1, a.strength) * 100)}%`, color: "#4ade80" };
    if (live) return { label: "Queued…", color: "#fbbf24" };
    return { label: "Staged", color: "#94a3b8" };
  }

  // Add / remove also inject into the running simulation (the worker applies it between
  // batches; particles + response appear in the next streamed frames).
  function inject(command: Parameters<typeof injectDrug>[1]) {
    if (live && simId) {
      if (command.action === "add" && !liveBaseline.current) liveBaseline.current = frame ?? null;
      injectDrug(simId, command).catch(() => {});
    }
  }
  function add(d: Drug) {
    onRegimenChange(addDrug(regimen, d));
    inject({ action: "add", drug_id: d.id, dose: d.default_dose });
  }
  function remove(id: string) {
    onRegimenChange(removeDrug(regimen, id));
    inject({ action: "remove", drug_id: id });
  }
  function changeDose(id: string, dose: number) {
    onRegimenChange(setDose(regimen, id, dose)); // local only — committed via Update Dose
  }
  function updateDose(id: string) {
    inject({ action: "update", drug_id: id, dose: doseOf(id) });
  }

  function download() {
    const blob = new Blob([exportRegimen(regimen, drugs)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "drug-experiment.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  const compareBaseline = liveBaseline.current ?? baselineFrame ?? null;

  async function runInterpret() {
    if (!frame || !compareBaseline) return;
    setBusy(true);
    try {
      setInterpretation(
        await interpretDrug({
          drugs: regimen.map((r) => r.drug_id),
          untreated: compareBaseline,
          treated: frame,
        }),
      );
    } catch {
      setInterpretation(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="drug-studio">
      <div className={`drug-mode ${live ? "is-live" : ""}`}>
        {live ? "● Live — inject into the running cell" : "Start the run (status RUNNING) to inject live"}
      </div>
      {/* TEMP DEBUG: shows the exact status value + whether live injection is enabled. */}
      <div className="drug-debug">
        Simulation status: <b>{status ?? "—"}</b>
        <br />
        Live injection enabled: <b>{live ? "yes" : "no"}</b>
      </div>
      <input
        className="drug-search"
        placeholder="Search drugs…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search drugs"
      />

      {/* Active drug list — each drug with its live status, dose slider + controls. */}
      {regimen.length > 0 && (
        <div className="drug-active">
          <div className="drug-active-title">Active drugs ({regimen.length})</div>
          {regimen.map((r) => {
            const d = byId.get(r.drug_id);
            const status = statusOf(r.drug_id);
            return (
              <div className="drug-active-row" key={r.drug_id}>
                <div className="drug-active-head">
                  <span className="drug-dot" style={{ background: d?.color ?? "#fff" }} />
                  <span className="drug-name">{d?.name ?? r.drug_id}</span>
                  <span className="drug-status" style={{ color: status.color }}>{status.label}</span>
                </div>
                <label className="drug-dose">
                  Dose {doseOf(r.drug_id).toFixed(1)}×
                  <input
                    type="range" min={0} max={2} step={0.1}
                    value={doseOf(r.drug_id)}
                    onChange={(e) => changeDose(r.drug_id, Number(e.target.value))}
                    aria-label={`Dose for ${d?.name ?? r.drug_id}`}
                  />
                </label>
                <div className="drug-row-actions">
                  {live && (
                    <button className="tb-btn tb-text" onClick={() => updateDose(r.drug_id)}>
                      Update Dose
                    </button>
                  )}
                  <button className="tb-btn tb-text" onClick={() => remove(r.drug_id)}>Remove</button>
                </div>
              </div>
            );
          })}
          <div className="drug-active-actions">
            {onApply && (
              <button className="tb-btn tb-text" onClick={() => onApply(regimen)}>Apply to run ▶</button>
            )}
            <button className="tb-btn tb-text" onClick={download}>Export</button>
            {frame && compareBaseline && (
              <button className="tb-btn tb-text" onClick={runInterpret} disabled={busy}>
                {busy ? "Analysing…" : "Interpret"}
              </button>
            )}
          </div>
          <div className="drug-hint">💊 injections are marked in the Lifecycle Events timeline.</div>
        </div>
      )}

      {/* Drug library. */}
      <div className="drug-list">
        {shown.map((d) => {
          const active = isActive(regimen, d.id);
          return (
            <div key={d.id} className={`drug-card ${active ? "is-active" : ""}`}>
              <div className="drug-card-head">
                <span className="drug-dot" style={{ background: d.color }} />
                <span className="drug-name">{d.name}</span>
                <span className="drug-conf" style={{ color: CONF_COLOR[d.confidence] }}>{d.confidence}</span>
                {active ? (
                  <span className="drug-active-tag">✓ active</span>
                ) : (
                  <button className="tb-btn tb-text" onClick={() => add(d)}>
                    {live ? "Inject" : "Add"}
                  </button>
                )}
              </div>
              <div className="drug-mech">{d.mechanism}</div>
            </div>
          );
        })}
      </div>

      {interpretation && (
        <div className="drug-interpret">
          <div className="drug-interpret-title">AI Scientist — pharmacology</div>
          <ul>
            {interpretation.statements.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
          <div className="drug-prediction">{interpretation.prediction}</div>
        </div>
      )}
    </div>
  );
}
