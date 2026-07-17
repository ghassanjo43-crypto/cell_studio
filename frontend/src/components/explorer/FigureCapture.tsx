// Scientific figure export. Lives inside the Canvas so it can read the renderer and
// camera; on demand it composites the rendered frame with a title/metadata strip, a
// legend, and (for the Petri dish) a projected scale bar, then downloads a PNG.
// The Canvas must use `preserveDrawingBuffer: true` for the capture to be non-blank.

import { useThree } from "@react-three/fiber";
import { useEffect, type MutableRefObject } from "react";
import * as THREE from "three";
import { DISH_WORLD } from "./petri";
import { scaleBar, type LegendEntry } from "./figure";

export interface FigureMeta {
  title: string;
  subtitle: string;
}

interface Props {
  registerRef: MutableRefObject<(() => void) | null>;
  meta: FigureMeta;
  legend: LegendEntry[];
  petriGridW?: number; // grid width in sites → enables the scale bar
}

interface OverlayOpts {
  w: number;
  h: number;
  s: number; // device-pixel scale
  meta: FigureMeta;
  legend: LegendEntry[];
  bar: { units: number; px: number } | null;
}

function drawOverlays(ctx: CanvasRenderingContext2D, o: OverlayOpts): void {
  const { w, h, s, meta, legend, bar } = o;
  const pad = 14 * s;

  // Title / metadata strip.
  ctx.fillStyle = "rgba(8,14,28,0.6)";
  ctx.fillRect(0, 0, w, 52 * s);
  ctx.fillStyle = "#e6edf7";
  ctx.font = `bold ${18 * s}px system-ui, sans-serif`;
  ctx.fillText(meta.title, pad, 26 * s);
  ctx.fillStyle = "#94a3b8";
  ctx.font = `${12 * s}px system-ui, sans-serif`;
  ctx.fillText(meta.subtitle, pad, 44 * s);

  // Legend (bottom-left).
  ctx.font = `${12 * s}px system-ui, sans-serif`;
  let ly = h - pad - legend.length * 16 * s;
  for (const e of legend) {
    ctx.fillStyle = e.color;
    ctx.fillRect(pad, ly, 12 * s, 12 * s);
    ctx.fillStyle = "#cbd5e1";
    ctx.fillText(e.label, pad + 18 * s, ly + 11 * s);
    ly += 16 * s;
  }

  // Scale bar (bottom-right).
  if (bar && bar.px > 4) {
    const bx = w - pad - bar.px;
    const by = h - pad - 6 * s;
    ctx.strokeStyle = "#e6edf7";
    ctx.lineWidth = 3 * s;
    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.lineTo(bx + bar.px, by);
    ctx.moveTo(bx, by - 5 * s);
    ctx.lineTo(bx, by + 5 * s);
    ctx.moveTo(bx + bar.px, by - 5 * s);
    ctx.lineTo(bx + bar.px, by + 5 * s);
    ctx.stroke();
    ctx.fillStyle = "#e6edf7";
    ctx.textAlign = "center";
    ctx.fillText(`${bar.units} sites`, bx + bar.px / 2, by - 9 * s);
    ctx.textAlign = "start";
  }
}

export function FigureCapture({ registerRef, meta, legend, petriGridW }: Props) {
  const gl = useThree((st) => st.gl);
  const camera = useThree((st) => st.camera);
  const size = useThree((st) => st.size);

  useEffect(() => {
    registerRef.current = () => {
      const src = gl.domElement;
      const w = src.width;
      const h = src.height;
      const out = document.createElement("canvas");
      out.width = w;
      out.height = h;
      const ctx = out.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(src, 0, 0);

      let bar: { units: number; px: number } | null = null;
      if (petriGridW) {
        const worldPerSite = DISH_WORLD / petriGridW;
        const p0 = new THREE.Vector3(0, 0, 0).project(camera);
        const p1 = new THREE.Vector3(worldPerSite, 0, 0).project(camera);
        const pxPerSite = (Math.abs(p1.x - p0.x) / 2) * w;
        bar = scaleBar(pxPerSite, w * 0.12);
      }

      drawOverlays(ctx, { w, h, s: w / Math.max(1, size.width), meta, legend, bar });
      out.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "cell-figure.png";
        a.click();
        URL.revokeObjectURL(url);
      });
    };
    return () => {
      registerRef.current = null;
    };
  }, [gl, camera, size, meta, legend, petriGridW, registerRef]);

  return null;
}
