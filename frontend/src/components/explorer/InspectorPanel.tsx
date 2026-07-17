// The browser-side inspector: when a biological structure is clicked in the scene,
// show its current state, numerical values and a grounded biological explanation.
// When nothing is selected, offer the list of inspectable structures.

import type { InspectInfo, ObjectId } from "./inspect";

const OBJECT_LABELS: Record<string, string> = {
  membrane: "Membrane",
  cytosol: "Cytosol",
  nucleoid: "Nucleoid",
  transport: "Transporters",
  nutrients: "Nutrients",
  signalling: "Signalling",
  "energy.cytosol": "Energy · cytosol",
  "energy.nucleoid": "Energy · nucleoid",
  "energy.membrane_zone": "Energy · membrane",
};

function labelFor(id: ObjectId): string {
  return OBJECT_LABELS[id] ?? id;
}

interface InspectorPanelProps {
  info: InspectInfo | null;
  present: ObjectId[];
  selected: ObjectId | null;
  onSelect: (id: ObjectId) => void;
  onClear: () => void;
  onEnter?: () => void;
}

export function InspectorPanel({ info, present, selected, onSelect, onClear, onEnter }: InspectorPanelProps) {
  return (
    <div className="inspector" data-testid="inspector">
      <div className="inspector-chips">
        {present.map((id) => (
          <button
            key={id}
            className={`chip ${selected === id ? "chip-active" : ""}`}
            onClick={() => onSelect(id)}
          >
            {labelFor(id)}
          </button>
        ))}
      </div>

      {info ? (
        <div className="inspector-body">
          <div className="inspector-head">
            <div>
              <h3>{info.title}</h3>
              {info.subtitle ? <span className="inspector-sub">{info.subtitle}</span> : null}
            </div>
            <button className="btn btn-small" onClick={onClear} title="Deselect">
              ✕
            </button>
          </div>
          <dl className="inspector-values">
            {info.values.map((v) => (
              <div key={v.label} className="inspector-row">
                <dt>{v.label}</dt>
                <dd>{v.value}</dd>
              </div>
            ))}
          </dl>
          <p className="inspector-explain">{info.explanation}</p>
          {onEnter ? (
            <button className="btn btn-small btn-primary" onClick={onEnter} title="Enter this cell in the single-cell explorer">
              ⤵ Enter cell
            </button>
          ) : null}
        </div>
      ) : (
        <div className="inspector-empty">Click a structure in the scene to inspect it.</div>
      )}
    </div>
  );
}
