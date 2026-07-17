// The cell viewer: a normal browser 3D scene that can also be entered in immersive
// VR (WebXR via @react-three/xr). The same scene graph is used for both — the
// browser renders it directly; "Enter VR" starts an immersive session that renders
// the identical scene, with the headset driving the camera.

import { Canvas } from "@react-three/fiber";
import { XR, XROrigin, createXRStore } from "@react-three/xr";
import { useEffect, useMemo, useState } from "react";
import type { FrameData } from "../api/types";
import { CellScene } from "./vr/CellScene";

interface CellViewerProps {
  frame: FrameData | null;
}

export function CellViewer({ frame }: CellViewerProps) {
  // One XR store per viewer instance; drives the immersive session. The browser
  // XR emulator is disabled (it conflicts with R3F v8's zustand) — real-headset VR
  // via navigator.xr is unaffected.
  const store = useMemo(() => createXRStore({ emulate: false }), []);
  const [vrSupported, setVrSupported] = useState<boolean | null>(null);

  useEffect(() => {
    const xr = (navigator as unknown as { xr?: { isSessionSupported?: (m: string) => Promise<boolean> } }).xr;
    if (!xr?.isSessionSupported) {
      setVrSupported(false);
      return;
    }
    xr.isSessionSupported("immersive-vr").then(setVrSupported).catch(() => setVrSupported(false));
  }, []);

  return (
    <div className="cell-viewer-wrap">
      <div className="viewer-toolbar">
        <button
          className="btn btn-small vr-btn"
          disabled={!vrSupported}
          onClick={() => store.enterVR()}
          title={vrSupported ? "Enter immersive VR" : "No VR headset / WebXR detected"}
        >
          🥽 {vrSupported ? "Enter VR" : "VR unavailable"}
        </button>
        <span className="viewer-hint">drag to orbit · scroll to zoom</span>
      </div>
      <div className="cell-viewer" data-testid="cell-viewer">
        <Canvas camera={{ position: [0, 0, 7], fov: 45 }}>
          <XR store={store}>
            {/* In VR, place the player a few metres back and at eye height so the
                cell sits ahead of them; ignored in the browser. */}
            <XROrigin position={[0, 1.2, 4]} />
            <CellScene frame={frame} />
          </XR>
        </Canvas>
      </div>
    </div>
  );
}
