// The hover tooltip: a compact card following the cursor that names the structure
// under it and shows its top live values (from the same grounded inspect data as the
// panel). Clicking it opens the full inspector. Browser-only — VR uses the 3D panel.

import type { FrameData } from "../../api/types";
import { buildInspect, hoverTip } from "./inspect";
import type { ObjectId } from "./inspect";

interface Props {
  id: ObjectId;
  x: number;
  y: number;
  frame: FrameData | null;
  onClick: () => void;
}

export function HoverTooltip({ id, x, y, frame, onClick }: Props) {
  const info = buildInspect(id, frame);
  if (!info) return null;
  const tip = hoverTip(info);
  return (
    <div className="hover-tip" style={{ left: x + 16, top: y + 16 }} onClick={onClick}>
      <div className="hover-tip-title">{info.title}</div>
      {tip ? <div className="hover-tip-desc">{tip}</div> : null}
      {info.values.slice(0, 3).map((v) => (
        <div key={v.label} className="hover-tip-row">
          <span>{v.label}</span>
          <b>{v.value}</b>
        </div>
      ))}
      <div className="hover-tip-hint">click to inspect</div>
    </div>
  );
}
