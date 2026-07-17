import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { experimentsApi } from "../api/endpoints";
import type { Experiment, ScenarioKind, SweepAxis } from "../api/types";
import { SWEEP_PARAMS, paramsForScenario, parseSweepValues } from "../components/lab/sweepParams";

const SCENARIOS: ScenarioKind[] = [
  "minimal", "lifecycle", "evolution", "spatial", "compartment", "signalling", "population", "petri",
];

export function ExperimentLabPage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const navigate = useNavigate();

  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [name, setName] = useState("Dose–response");
  const [scenario, setScenario] = useState<ScenarioKind>("lifecycle");
  const [maxSteps, setMaxSteps] = useState(300);
  const [axis1, setAxis1] = useState("glucose_mmol");
  const [values1, setValues1] = useState("10, 30, 60");
  const [axis2, setAxis2] = useState("");
  const [values2, setValues2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    experimentsApi.list(pid).then(setExperiments).catch((e) => setError(String(e)));
  }, [pid]);

  const params = paramsForScenario(scenario);

  useEffect(() => {
    const first = paramsForScenario(scenario)[0]?.field ?? "";
    setAxis1(first);
    setAxis2("");
  }, [scenario]);

  function buildAxis(field: string, raw: string, sweep: SweepAxis[]) {
    if (!field || !raw.trim()) return;
    const p = SWEEP_PARAMS.find((x) => x.field === field);
    const vals = parseSweepValues(raw, p?.kind ?? "number");
    if (vals.length) sweep.push({ param: field, values: vals });
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const sweep: SweepAxis[] = [];
      buildAxis(axis1, values1, sweep);
      buildAxis(axis2, values2, sweep);
      const exp = await experimentsApi.create(pid, name, { scenario, max_steps: maxSteps }, sweep);
      navigate(`/experiments/${exp.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  const example = (field: string) => SWEEP_PARAMS.find((p) => p.field === field)?.example ?? "";

  return (
    <div className="page">
      <button className="btn btn-small" onClick={() => navigate(`/projects/${pid}`)}>
        ← Project
      </button>
      <h1>🧪 Experiment Lab</h1>
      <p className="muted">
        Run a base design across a parameter sweep and compare outcomes side by side (dose–response,
        founder count, mutation rate, …).
      </p>

      <form className="design-form lab-form" onSubmit={create}>
        <div className="field">
          <label>Experiment name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="lab-row">
          <div className="field">
            <label>Base scenario</label>
            <select value={scenario} onChange={(e) => setScenario(e.target.value as ScenarioKind)}>
              {SCENARIOS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Max steps</label>
            <input type="number" value={maxSteps} onChange={(e) => setMaxSteps(Number(e.target.value))} />
          </div>
        </div>

        <div className="sweep-axis">
          <div className="field">
            <label>Sweep parameter</label>
            <select value={axis1} onChange={(e) => setAxis1(e.target.value)}>
              {params.map((p) => (
                <option key={p.field} value={p.field}>{p.label}</option>
              ))}
            </select>
          </div>
          <div className="field grow">
            <label>Values (comma-separated)</label>
            <input value={values1} onChange={(e) => setValues1(e.target.value)} placeholder={example(axis1)} />
          </div>
        </div>

        <div className="sweep-axis">
          <div className="field">
            <label>Second parameter (optional)</label>
            <select value={axis2} onChange={(e) => setAxis2(e.target.value)}>
              <option value="">— none —</option>
              {params.filter((p) => p.field !== axis1).map((p) => (
                <option key={p.field} value={p.field}>{p.label}</option>
              ))}
            </select>
          </div>
          <div className="field grow">
            <label>Values</label>
            <input value={values2} onChange={(e) => setValues2(e.target.value)} placeholder={example(axis2)} disabled={!axis2} />
          </div>
        </div>

        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create & configure"}
        </button>
      </form>

      {error ? <div className="form-error">{error}</div> : null}

      <h2>Experiments</h2>
      <ul className="card-list">
        {experiments.map((x) => (
          <li key={x.id} className="card design-card">
            <div>
              <strong>{x.name}</strong>
              <span className="muted"> — {x.base_config.scenario}, {x.n_runs} runs · {x.status}</span>
            </div>
            <button className="btn btn-primary btn-small" onClick={() => navigate(`/experiments/${x.id}`)}>
              Open
            </button>
          </li>
        ))}
        {experiments.length === 0 ? <li className="muted">No experiments yet — create one above.</li> : null}
      </ul>
    </div>
  );
}
