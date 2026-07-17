// Per-simulation scientific notes, auto-saved to localStorage.

import { useEffect, useState } from "react";

export function ScientificNotes({ simId }: { simId: number }) {
  const key = `vcs_notes_${simId}`;
  const [text, setText] = useState(() => (typeof localStorage !== "undefined" ? localStorage.getItem(key) ?? "" : ""));

  useEffect(() => {
    const t = window.setTimeout(() => {
      try {
        localStorage.setItem(key, text);
      } catch {
        /* storage unavailable */
      }
    }, 400);
    return () => window.clearTimeout(t);
  }, [text, key]);

  return (
    <textarea
      className="sci-notes"
      placeholder="Observations, hypotheses, notes… (saved locally)"
      value={text}
      onChange={(e) => setText(e.target.value)}
    />
  );
}
