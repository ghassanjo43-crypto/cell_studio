// A small dependency-free SVG line chart for time series. Renders one or more
// series on a shared y-domain, with a subtle baseline and last-value labels.

export interface Series {
  label: string;
  color: string;
  values: number[];
}

interface LineChartProps {
  title: string;
  series: Series[];
  height?: number;
  unit?: string;
}

const WIDTH = 320;
const PAD = 6;

function pathFor(values: number[], min: number, max: number, w: number, h: number): string {
  if (values.length === 0) return "";
  const span = max - min || 1;
  const step = values.length > 1 ? (w - 2 * PAD) / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = PAD + i * step;
      const y = h - PAD - ((v - min) / span) * (h - 2 * PAD);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function LineChart({ title, series, height = 90, unit }: LineChartProps) {
  const all = series.flatMap((s) => s.values);
  const min = all.length ? Math.min(...all) : 0;
  const max = all.length ? Math.max(...all) : 1;

  return (
    <div className="chart">
      <div className="chart-head">
        <span className="chart-title">{title}</span>
        <span className="chart-legend">
          {series.map((s) => {
            const last = s.values.length ? s.values[s.values.length - 1] : 0;
            return (
              <span key={s.label} className="legend-item">
                <span className="legend-swatch" style={{ background: s.color }} />
                {s.label}: {formatValue(last)}
                {unit ? ` ${unit}` : ""}
              </span>
            );
          })}
        </span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${height}`} width="100%" height={height} role="img" aria-label={title}>
        <rect x="0" y="0" width={WIDTH} height={height} className="chart-bg" />
        {series.map((s) => (
          <path
            key={s.label}
            d={pathFor(s.values, min, max, WIDTH, height)}
            fill="none"
            stroke={s.color}
            strokeWidth={1.75}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
      </svg>
    </div>
  );
}

export function formatValue(v: number): string {
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (abs >= 1000 || abs < 0.01) return v.toExponential(2);
  if (abs >= 10) return v.toFixed(1);
  return v.toFixed(3);
}
