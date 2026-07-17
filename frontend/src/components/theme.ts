// Shared visual palette + status/event mappings, so the dashboard, timeline, and
// 3D viewer read as one consistent system.

export const palette = {
  mass: "#4ade80", // green
  glucoseEnv: "#fbbf24", // amber
  glucosePool: "#38bdf8", // sky
  membrane: "#a78bfa", // violet
  neutral: "#94a3b8",
};

export function statusColor(status: string | null | undefined): string {
  switch (status) {
    case "GROWING":
      return palette.mass;
    case "STRESSED":
      return "#fbbf24";
    case "DYING":
      return "#fb923c";
    case "DEAD":
      return "#94a3b8";
    default:
      return "#60a5fa";
  }
}

export interface EventStyle {
  color: string;
  icon: string;
  label: string;
}

export function eventStyle(type: string): EventStyle {
  switch (type) {
    case "gene_activated":
      return { color: "#38bdf8", icon: "◆", label: "Gene activated" };
    case "replication_start":
      return { color: "#a78bfa", icon: "◐", label: "Replication start" };
    case "replication_complete":
      return { color: "#a78bfa", icon: "●", label: "Replication complete" };
    case "division":
      return { color: "#4ade80", icon: "⧉", label: "Division" };
    case "mutation":
      return { color: "#f472b6", icon: "✳", label: "Mutation" };
    case "membrane_rupture":
      return { color: "#fb7185", icon: "◌", label: "Membrane rupture" };
    case "death":
      return { color: "#94a3b8", icon: "✕", label: "Death" };
    case "cell_birth":
      return { color: "#4ade80", icon: "✚", label: "Cell born" };
    case "cell_death":
      return { color: "#94a3b8", icon: "✕", label: "Cell died" };
    case "clone_expansion":
      return { color: "#38bdf8", icon: "⇗", label: "Clone expansion" };
    case "population_extinct":
      return { color: "#fb7185", icon: "☠", label: "Extinction" };
    case "colony_founded":
      return { color: "#4ade80", icon: "❋", label: "Colony founded" };
    case "colony_extinct":
      return { color: "#fb7185", icon: "☠", label: "Colony extinct" };
    case "clone_dominant":
      return { color: "#38bdf8", icon: "♛", label: "Clone dominant" };
    case "biofilm_confluent":
      return { color: "#a78bfa", icon: "▦", label: "Biofilm confluent" };
    case "drug_injected":
      return { color: "#c4b5fd", icon: "💊", label: "Drug injected" };
    case "drug_dose_changed":
      return { color: "#c4b5fd", icon: "💊", label: "Dose changed" };
    case "drug_removed":
      return { color: "#94a3b8", icon: "💊", label: "Drug removed" };
    default:
      return { color: palette.neutral, icon: "•", label: type };
  }
}
