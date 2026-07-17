// A compact KPI tile: a big value with a label and optional sub-line/accent.

interface StatTileProps {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}

export function StatTile({ label, value, sub, accent }: StatTileProps) {
  return (
    <div className="stat-tile" style={accent ? { borderTopColor: accent } : undefined}>
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}
