// The Scientific Narration side panel: a live, auto-scrolling log of the biological
// story, generated entirely from simulation state (see narration.ts).

import { useEffect, useRef } from "react";
import type { NarrationLine } from "./narration";

export function NarrationPanel({ lines, mode }: { lines: NarrationLine[]; mode: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines.length]);

  return (
    <div className="narration" data-testid="narration">
      <div className="narration-title">◈ Scientific Narration <span className="narration-mode">{mode}</span></div>
      <div className="narration-log" ref={ref}>
        {lines.length ? (
          lines.map((l, i) => (
            <div key={`${l.step}-${i}`} className={`narration-line n-${l.kind}`}>
              <span className="narration-step">t{l.step}</span> {l.text}
            </div>
          ))
        ) : (
          <div className="muted">The story will appear here as the cell lives.</div>
        )}
      </div>
    </div>
  );
}
