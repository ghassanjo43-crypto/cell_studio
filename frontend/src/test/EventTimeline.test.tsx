import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SimEvent } from "../api/types";
import { EventTimeline } from "../components/EventTimeline";
import { eventStyle, statusColor } from "../components/theme";

describe("EventTimeline", () => {
  it("shows an empty state with no events", () => {
    render(<EventTimeline events={[]} />);
    expect(screen.getByText(/No events yet/i)).toBeInTheDocument();
  });

  it("renders lifecycle events with labels and details", () => {
    const events: SimEvent[] = [
      { step: 50, time: 5, type: "gene_activated", data: { gene: "repInit" } },
      { step: 90, time: 9, type: "division", data: { daughter_lineages: ["0.0", "0.1"] } },
      { step: 110, time: 11, type: "mutation", data: { target: "geno.metabolism", old: 1, new: 0.9 } },
      { step: 120, time: 12, type: "death", data: { cause: "starvation" } },
    ];
    render(<EventTimeline events={events} />);
    expect(screen.getByText(/Lifecycle events \(4\)/)).toBeInTheDocument();
    expect(screen.getByText("Division")).toBeInTheDocument();
    expect(screen.getByText("Mutation")).toBeInTheDocument();
    expect(screen.getByText(/cause: starvation/)).toBeInTheDocument();
    expect(screen.getByText(/geno.metabolism/)).toBeInTheDocument();
  });
});

describe("theme mappings", () => {
  it("maps statuses to distinct colors", () => {
    expect(statusColor("GROWING")).not.toBe(statusColor("DEAD"));
  });

  it("provides a style for every known event type", () => {
    for (const t of ["division", "mutation", "death", "replication_start"]) {
      expect(eventStyle(t).label.length).toBeGreaterThan(0);
    }
  });
});
