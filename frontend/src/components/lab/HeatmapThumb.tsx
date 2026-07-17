// A small heat-map thumbnail drawn to a canvas — used to compare Petri dish runs
// side by side. Reuses the colour maps from the Cell Explorer's petri helpers.

import { useEffect, useRef } from "react";
import { cloneColorRGB, viridis } from "../explorer/petri";

interface HeatmapThumbProps {
  values: number[];
  rows: number;
  cols: number;
  mode: "viridis" | "clone";
  size?: number; // rendered pixel size
}

export function HeatmapThumb({ values, rows, cols, mode, size = 120 }: HeatmapThumbProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(cols, rows);
    const max = Math.max(1e-6, ...values);
    for (let i = 0; i < rows * cols; i++) {
      let r: number, g: number, b: number, a = 255;
      if (mode === "clone") {
        [r, g, b] = cloneColorRGB(values[i]);
        a = values[i] < 0 ? 30 : 255;
      } else {
        [r, g, b] = viridis(values[i] / max);
      }
      img.data[i * 4] = r;
      img.data[i * 4 + 1] = g;
      img.data[i * 4 + 2] = b;
      img.data[i * 4 + 3] = a;
    }
    ctx.putImageData(img, 0, 0);
  }, [values, rows, cols, mode]);

  return (
    <canvas
      ref={ref}
      width={cols}
      height={rows}
      style={{ width: size, height: size, imageRendering: "pixelated", borderRadius: 4, background: "#0b1220" }}
    />
  );
}
