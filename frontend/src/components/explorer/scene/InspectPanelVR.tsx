// In VR there is no DOM overlay, so the inspector read-out for the selected
// structure is shown as a floating billboard panel next to the cell. In the browser
// the DOM InspectorPanel is used instead, so this only renders inside a session.

import { useXR } from "@react-three/xr";
import type { FrameData } from "../../../api/types";
import { LabelPanel } from "../../vr/LabelPanel";
import { buildInspect } from "../inspect";
import type { ObjectId } from "../inspect";
import { radiusForMass } from "./geometry";

export function InspectPanelVR({ frame, selected }: { frame: FrameData; selected: ObjectId | null }) {
  const inXR = useXR((s) => !!s.session);
  if (!inXR || !selected) return null;
  const info = buildInspect(selected, frame);
  if (!info) return null;

  const lines = [
    ...(info.subtitle ? [info.subtitle] : []),
    ...info.values.map((v) => `${v.label}: ${v.value}`),
  ];
  // Colony frames have no single-cell biomass; place the panel at a fixed offset.
  const offset = frame.population ? 3 : radiusForMass(frame.mass) + 1.2;
  return <LabelPanel panel={{ title: info.title, lines }} position={[offset, 0.6, 0]} width={1.4} />;
}
