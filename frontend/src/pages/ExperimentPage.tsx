import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { experimentsApi } from "../api/endpoints";
import type { ExperimentResults, RunMetrics } from "../api/types";
import { LineChart, formatValue, type Series } from "../components/charts/LineChart";
import { AiScientist } from "../components/lab/AiScientist";
import { HeatmapThumb } from "../components/lab/HeatmapThumb";

const RUN_COLORS = [
  "#4ade80", "#38bdf8", "#f472b6", "#fbbf24", "#a78bfa", "#fb7185",
  "#22d3ee", "#facc15", "#c084fc", "#34d399", "#60a5fa", "#f87171",
];
const color = (i: number) => RUN_COLORS[i % RUN_COLORS.length];

const METRIC_COLS: { key: keyof RunMetrics; label: string; higherBetter?: boolean }[] = [
  { key: "outcome", label: "Outcome" },
  { key: "survival_time", label: "Survival", higherBetter: true },
  { key: "divisions", label: "Divisions", higherBetter: true },
  { key: "peak_population", label: "Peak pop.", higherBetter: true },
  { key: "biomass_peak", label: "Biomass peak", higherBetter: true },
  { key: "nutrient_depletion", label: "Nutrient used" },
  { key: "dominant_clone", label: "Dominant" },
  { key: "extinction_time", label: "Extinction" },
];

const BAR_METRICS: (keyof RunMetrics)[] = [
  "biomass_peak", "survival_time", "divisions", "peak_population", "nutrient_depletion",
];

const RUNNING = new Set(["QUEUED", "RUNNING"]);

function fmtMetric(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return formatValue(v);
  return String(v);
}

export function ExperimentPage() {
  const { experimentId } = useParams();
  const id = Number(experimentId);
  const navigate = useNavigate();

  const [results, setResults] = useState<ExperimentResults | null>(null);
  const [busy, setBusy] = useState(false);
  const [barMetric, setBarMetric] = useState<keyof RunMetrics>("biomass_peak");
  const [hmMode, setHmMode] = useState<"population" | "nutrient" | "clone">("population");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setResults(await experimentsApi.results(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while the sweep is running.
  const status = results?.experiment.status;
  useEffect(() => {
    if (!status || !RUNNING.has(status)) return;
    const t = setInterval(load, 1200);
    return () => clearInterval(t);
  }, [status, load]);

  async function runExperiment() {
    setBusy(true);
    setError(null);
    try {
      await experimentsApi.run(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!results) return <div className="page">{error ?? "Loading…"}</div>;
  const { experiment, runs } = results;
  const sweepParams = experiment.sweep.map((a) => a.param);
  const isPetri = experiment.base_config.scenario === "petri";
  const done = runs.filter((r) => r.status === "DONE").length;

  const popSeries: Series[] = runs
    .filter((r) => r.series && r.series.population.length)
    .map((r, i) => ({ label: r.label, color: color(i), values: r.series!.population }));

  const barValues = runs.map((r) => (typeof r.metrics?.[barMetric] === "number" ? (r.metrics[barMetric] as number) : 0));
  const barMax = Math.max(1e-6, ...barValues.map(Math.abs));

  // Which run is "best" per metric column (for a subtle highlight).
  function bestIdx(key: keyof RunMetrics, higher: boolean): number {
    let best = -1;
    let bestVal = higher ? -Infinity : Infinity;
    runs.forEach((r, i) => {
      const v = r.metrics?.[key];
      if (typeof v !== "number") return;
      if ((higher && v > bestVal) || (!higher && v < bestVal)) {
        bestVal = v;
        best = i;
      }
    });
    return best;
  }

  return (
    <div className="page">
      <button className="btn btn-small" onClick={() => navigate(`/projects/${experiment.project_id}/lab`)}>
        ← Lab
      </button>
      <div className="sim-header">
        <h1>{experiment.name}</h1>
        <div className="lab-actions">
          <span className={`status-badge status-${experiment.status.toLowerCase()}`}>{experiment.status}</span>
          <span className="muted">{done}/{experiment.n_runs} runs</span>
          <button className="btn btn-primary btn-small" onClick={runExperiment} disabled={busy || RUNNING.has(experiment.status)}>
            {RUNNING.has(experiment.status) ? "Running…" : "▶ Run sweep"}
          </button>
          <button className="btn btn-small" onClick={() => experimentsApi.export(id, "csv")}>⤓ CSV</button>
          <button className="btn btn-small" onClick={() => experimentsApi.export(id, "json")}>⤓ JSON</button>
        </div>
      </div>
      <p className="muted">
        base: {experiment.base_config.scenario} · swept: {sweepParams.join(", ") || "none"}
      </p>
      {error ? <div className="form-error">{error}</div> : null}

      {/* Results table */}
      <div className="lab-table-wrap">
        <table className="lab-table">
          <thead>
            <tr>
              <th>Run</th>
              {sweepParams.map((p) => <th key={p}>{p}</th>)}
              {METRIC_COLS.map((m) => <th key={m.key}>{m.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {runs.map((r, i) => (
              <tr key={r.idx}>
                <td><span className="run-swatch" style={{ background: color(i) }} /> #{r.idx}</td>
                {sweepParams.map((p) => <td key={p}>{fmtMetric((r.config as unknown as Record<string, unknown>)[p])}</td>)}
                {METRIC_COLS.map((m) => {
                  const best = m.higherBetter !== undefined && bestIdx(m.key, !!m.higherBetter) === i;
                  return (
                    <td key={m.key} className={best ? "cell-best" : ""}>
                      {r.status === "DONE" ? fmtMetric(r.metrics?.[m.key]) : r.status === "FAILED" ? "✕" : "…"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Comparison charts */}
      <div className="chart-row">
        {popSeries.length ? (
          <LineChart title="Population / biomass over time" series={popSeries} />
        ) : null}
        <div className="chart">
          <div className="chart-head">
            <span className="chart-title">Compare metric</span>
            <select value={barMetric} onChange={(e) => setBarMetric(e.target.value as keyof RunMetrics)}>
              {BAR_METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="bar-compare">
            {runs.map((r, i) => (
              <div key={r.idx} className="bar-row">
                <span className="bar-label">{r.label}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${(Math.abs(barValues[i]) / barMax) * 100}%`, background: color(i) }} />
                </div>
                <span className="bar-value">{formatValue(barValues[i])}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Heat map comparison (Petri dish) */}
      {isPetri && runs.some((r) => r.heatmaps) ? (
        <div className="chart">
          <div className="chart-head">
            <span className="chart-title">Heat-map comparison</span>
            <select value={hmMode} onChange={(e) => setHmMode(e.target.value as typeof hmMode)}>
              <option value="population">population</option>
              <option value="nutrient">nutrient</option>
              <option value="clone">clones</option>
            </select>
          </div>
          <div className="heatmap-grid">
            {runs.filter((r) => r.heatmaps).map((r) => {
              const hm = r.heatmaps!;
              const [rows, cols] = hm.hm_size;
              const values = hmMode === "clone" ? hm.clone_map : hm.heatmaps[hmMode];
              return (
                <div key={r.idx} className="heatmap-cell">
                  <HeatmapThumb values={values} rows={rows} cols={cols} mode={hmMode === "clone" ? "clone" : "viridis"} />
                  <span className="muted">{r.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* AI Scientist */}
      <AiScientist experimentId={id} projectId={experiment.project_id} ready={done > 0} />
    </div>
  );
}
