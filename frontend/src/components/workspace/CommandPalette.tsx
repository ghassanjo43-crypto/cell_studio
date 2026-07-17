// A professional command palette (Ctrl/Cmd+K): fuzzy-search and run any workspace
// command. Keyboard-navigable.

import { useEffect, useMemo, useRef, useState } from "react";
import { filterCommands, type Command } from "./commands";

export function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useMemo(() => filterCommands(commands, query), [commands, query]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);
  useEffect(() => {
    setActive(0);
  }, [query]);

  function run(cmd: Command | undefined) {
    if (cmd && cmd.enabled) {
      onClose();
      cmd.run();
    }
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(results.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(results[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  return (
    <div className="cmd-overlay" onClick={onClose}>
      <div className="cmd-palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cmd-input"
          placeholder="Type a command…  (e.g. focus genome, export figure, presentation)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKey}
        />
        <div className="cmd-list">
          {results.length ? (
            results.map((c, i) => (
              <button
                key={c.id}
                className={`cmd-item ${i === active ? "is-active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => run(c)}
                disabled={!c.enabled}
              >
                <span className="cmd-title">{c.title}</span>
                <span className="cmd-meta">
                  {c.shortcut ? <kbd>{c.shortcut}</kbd> : null}
                  <span className="cmd-group">{c.group}</span>
                </span>
              </button>
            ))
          ) : (
            <div className="cmd-empty">No matching commands</div>
          )}
        </div>
        <div className="cmd-hint">↑↓ navigate · ↵ run · Esc close</div>
      </div>
    </div>
  );
}
