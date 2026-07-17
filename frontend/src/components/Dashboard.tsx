// Live dashboard: KPI tiles + time-series charts derived from the frame stream.

import type { Frame } from "../api/types";
import { LineChart, formatValue, type Series } from "./charts/LineChart";
import { StatTile } from "./charts/StatTile";
import { cloneCounts, lineageColor } from "./explorer/colony";
import { cloneColorRGB } from "./explorer/petri";
import { palette, statusColor } from "./theme";

export type DashboardVariant = "full" | "metrics" | "charts";

interface DashboardProps {
  frames: Frame[];
  variant?: DashboardVariant;
}

function PetriDashboard({ frames, variant = "full" }: DashboardProps) {
  const showMetrics = variant !== "charts";
  const showCharts = variant !== "metrics";
  const latest = frames.length ? frames[frames.length - 1].data.petri ?? null : null;
  const aliveSeries: Series = { label: "cells", color: palette.mass, values: frames.map((f) => f.data.petri?.alive ?? 0) };
  const occSeries: Series = { label: "occupancy", color: palette.membrane, values: frames.map((f) => f.data.petri?.occupancy ?? 0) };
  const nutrientSeries: Series = { label: "nutrient", color: palette.glucoseEnv, values: frames.map((f) => f.data.petri?.total_nutrient ?? 0) };
  const nClones = latest?.n_clones ?? 0;

  return (
    <div className="dashboard">
      {showMetrics && <div className="stat-row">
        <StatTile label="Living cells" value={latest?.alive ?? 0} accent={palette.mass} sub={`${latest?.born ?? 0} born · ${latest?.died ?? 0} died`} />
        <StatTile label="Colonies" value={latest ? `${latest.colonies} / ${latest.n_clones}` : "—"} sub="alive / founded" />
        <StatTile
          label="Dominant clone"
          value={latest && latest.dominant_clone >= 0 ? `#${latest.dominant_clone}` : "—"}
          sub={latest ? `${Math.round(latest.dominant_fraction * 100)}% of dish` : undefined}
        />
        <StatTile label="Occupancy" value={latest ? `${Math.round(latest.occupancy * 100)}%` : "—"} accent={palette.membrane} sub="biofilm density" />
        <StatTile label="Generations" value={latest?.generations ?? 0} />
        <StatTile label="Nutrient" value={latest ? formatValue(latest.total_nutrient) : "—"} accent={palette.glucoseEnv} sub="total remaining" />
      </div>}

      {showCharts && <div className="chart-row">
        <LineChart title="Population size" series={[aliveSeries]} unit="cells" />
        <LineChart title="Dish occupancy" series={[occSeries]} />
        <LineChart title="Nutrient remaining" series={[nutrientSeries]} unit="mmol" />
      </div>}

      {showMetrics && nClones > 0 ? (
        <div className="genotype-row">
          <span className="genotype-title">Colonies (founder clones)</span>
          {Array.from({ length: nClones }, (_, c) => {
            const [r, g, b] = cloneColorRGB(c);
            const dominant = latest?.dominant_clone === c;
            return (
              <span key={c} className={`geno-chip ${dominant ? "geno-mutated" : ""}`} style={{ borderColor: `rgb(${r},${g},${b})` }}>
                <span className="legend-swatch" style={{ background: `rgb(${r},${g},${b})` }} /> #{c}
                {dominant ? " ★" : ""}
              </span>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function PopulationDashboard({ frames, variant = "full" }: DashboardProps) {
  const showMetrics = variant !== "charts";
  const showCharts = variant !== "metrics";
  const latest = frames.length ? frames[frames.length - 1].data.population ?? null : null;
  const aliveSeries: Series = { label: "alive", color: palette.mass, values: frames.map((f) => f.data.population?.alive ?? 0) };
  const mediumSeries: Series = { label: "glucose", color: palette.glucoseEnv, values: frames.map((f) => f.data.population?.medium_glucose ?? 0) };
  const biomassSeries: Series = { label: "biomass", color: palette.glucosePool, values: frames.map((f) => f.data.population?.total_biomass ?? 0) };
  const clones = latest ? cloneCounts(latest.cells) : [];

  return (
    <div className="dashboard">
      {showMetrics && <div className="stat-row">
        <StatTile label="Living cells" value={latest?.alive ?? 0} accent={palette.mass} sub={`${latest?.total_ever ?? 0} ever`} />
        <StatTile label="Dead" value={latest?.dead ?? 0} accent={palette.neutral} />
        <StatTile label="Births / Deaths" value={`${latest?.born ?? 0} / ${latest?.died ?? 0}`} />
        <StatTile label="Generations" value={latest?.generations ?? 0} />
        <StatTile
          label="Dominant clone"
          value={latest?.dominant_lineage ? `#${latest.dominant_lineage}` : "—"}
          sub={latest ? `${Math.round(latest.dominant_fraction * 100)}% of colony` : undefined}
        />
        <StatTile label="Medium glucose" value={latest ? formatValue(latest.medium_glucose) : "—"} accent={palette.glucoseEnv} sub="shared pool" />
      </div>}

      {showCharts && <div className="chart-row">
        <LineChart title="Population size" series={[aliveSeries]} unit="cells" />
        <LineChart title="Shared glucose (competition)" series={[mediumSeries]} unit="mmol" />
        <LineChart title="Total biomass" series={[biomassSeries]} unit="gDW" />
      </div>}

      {showMetrics && clones.length ? (
        <div className="genotype-row">
          <span className="genotype-title">Clones (living)</span>
          {clones.slice(0, 10).map((c) => (
            <span key={c.root} className="geno-chip" style={{ borderColor: lineageColor(c.root, true) }}>
              <span className="legend-swatch" style={{ background: lineageColor(c.root, true) }} /> #{c.root}: {c.count}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function Dashboard({ frames, variant = "full" }: DashboardProps) {
  const showMetrics = variant !== "charts";
  const showCharts = variant !== "metrics";
  const latest = frames.length ? frames[frames.length - 1].data : null;

  if (latest?.petri) return <PetriDashboard frames={frames} variant={variant} />;
  if (latest?.population) return <PopulationDashboard frames={frames} variant={variant} />;

  const massSeries: Series = { label: "biomass", color: palette.mass, values: frames.map((f) => f.data.mass) };
  const glucoseSeries: Series[] = [
    { label: "medium", color: palette.glucoseEnv, values: frames.map((f) => f.data.env_glucose) },
    { label: "internal", color: palette.glucosePool, values: frames.map((f) => f.data.pool_glucose) },
  ];
  const membraneSeries: Series = {
    label: "integrity",
    color: palette.membrane,
    values: frames.map((f) => f.data.membrane_integrity),
  };

  return (
    <div className="dashboard">
      {showMetrics && <div className="stat-row">
        <StatTile
          label="Status"
          value={latest?.status ?? "—"}
          accent={statusColor(latest?.status)}
          sub={latest?.alive === false ? "not viable" : "viable"}
        />
        <StatTile label="Biomass (gDW)" value={latest ? formatValue(latest.mass) : "—"} accent={palette.mass} />
        <StatTile label="Divisions" value={latest?.divisions ?? 0} />
        <StatTile label="Generation" value={latest?.generation ?? 0} />
        <StatTile label="Lineage" value={latest?.lineage ?? "—"} sub="tracked cell" />
        <StatTile
          label="Membrane"
          value={latest ? `${Math.round(latest.membrane_integrity * 100)}%` : "—"}
          accent={palette.membrane}
        />
      </div>}

      {showCharts && <div className="chart-row">
        <LineChart title="Biomass" series={[massSeries]} unit="gDW" />
        <LineChart title="Glucose (medium vs internal)" series={glucoseSeries} unit="mmol" />
        <LineChart title="Membrane integrity" series={[membraneSeries]} />
      </div>}

      {showMetrics && latest?.nutrients ? (
        <div className="nutrient-row">
          <span className="genotype-title">Nutrients</span>
          {Object.entries(latest.nutrients).map(([n, v]) => (
            <span key={n} className={`geno-chip ${latest.limiting === `met.${n}` ? "geno-mutated" : ""}`}>
              {n}: surface {formatValue(v.surface)} mM
            </span>
          ))}
          {latest.limiting ? <span className="muted">limiting: {latest.limiting.replace("met.", "")}</span> : null}
        </div>
      ) : null}

      {showMetrics && latest?.compartments ? (
        <div className="nutrient-row">
          <span className="genotype-title">Compartments (energy)</span>
          {Object.entries(latest.compartments).map(([c, v]) => (
            <span key={c} className={`geno-chip ${v.stressed ? "geno-mutated" : ""}`}>
              {c.replace("_", " ")}: {formatValue(v.energy)}{v.stressed ? " ⚠" : ""}
            </span>
          ))}
        </div>
      ) : null}

      {showMetrics && latest?.signalling ? (
        <div className="nutrient-row">
          <span className="genotype-title">Signalling</span>
          <span className={`geno-chip ${latest.signalling.survival ? "geno-mutated" : ""}`}>
            mode: {latest.signalling.mode ?? "—"}
          </span>
          <span className="geno-chip">starvation: {formatValue(latest.signalling.signals.starvation)}</span>
          <span className="geno-chip">growth: {formatValue(latest.signalling.signals.growth)}</span>
          <span className="geno-chip">mem-stress: {formatValue(latest.signalling.signals.membrane_stress)}</span>
        </div>
      ) : null}

      {showCharts && latest?.field_glc ? (
        <div className="chart-row">
          <LineChart
            title="Glucose gradient (surface → bulk)"
            series={[{ label: "shell", color: palette.glucoseEnv, values: latest.field_glc }]}
            unit="mM"
          />
        </div>
      ) : null}

      {showMetrics && latest?.genotype ? (
        <div className="genotype-row">
          <span className="genotype-title">Genotype factors</span>
          {Object.entries(latest.genotype).map(([k, v]) => (
            <span key={k} className={`geno-chip ${v !== 1 ? "geno-mutated" : ""}`}>
              {k}: {v.toFixed(3)}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
