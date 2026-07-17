// Movie recording. Composites the rendered WebGL canvas with a title/metadata strip,
// a legend, the date, and the live narration onto a 2D canvas each frame, and records
// that canvas to a WebM via MediaRecorder — so the exported film contains the camera
// movements *and* the scientific HUD/titles/legend/metadata.

export interface RecordOverlay {
  title: string;
  subtitle: string;
  date: string;
  legend: { color: string; label: string }[];
  narration?: string;
}

/** Best supported video MIME (browsers reliably support WebM; MP4 rarely). */
export function pickVideoMime(): string {
  const candidates = [
    "video/mp4;codecs=avc1",
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/webm",
  ];
  const MR = typeof MediaRecorder !== "undefined" ? MediaRecorder : undefined;
  for (const c of candidates) {
    if (MR && MR.isTypeSupported && MR.isTypeSupported(c)) return c;
  }
  return "video/webm";
}

function drawOverlay(ctx: CanvasRenderingContext2D, w: number, h: number, s: number, o: RecordOverlay): void {
  const pad = 14 * s;
  // Title / metadata strip.
  ctx.fillStyle = "rgba(8,14,28,0.62)";
  ctx.fillRect(0, 0, w, 54 * s);
  ctx.fillStyle = "#e6edf7";
  ctx.font = `bold ${18 * s}px system-ui, sans-serif`;
  ctx.fillText(o.title, pad, 26 * s);
  ctx.fillStyle = "#94a3b8";
  ctx.font = `${12 * s}px system-ui, sans-serif`;
  ctx.fillText(o.subtitle, pad, 44 * s);
  ctx.textAlign = "right";
  ctx.fillText(o.date, w - pad, 26 * s);
  ctx.textAlign = "left";

  // Legend (bottom-left).
  ctx.font = `${12 * s}px system-ui, sans-serif`;
  let ly = h - pad - o.legend.length * 16 * s;
  for (const e of o.legend) {
    ctx.fillStyle = e.color;
    ctx.fillRect(pad, ly, 12 * s, 12 * s);
    ctx.fillStyle = "#cbd5e1";
    ctx.fillText(e.label, pad + 18 * s, ly + 11 * s);
    ly += 16 * s;
  }

  // Narration (bottom-centre).
  if (o.narration) {
    ctx.font = `${16 * s}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    const tw = ctx.measureText(o.narration).width;
    ctx.fillStyle = "rgba(8,14,28,0.7)";
    ctx.fillRect(w / 2 - tw / 2 - 12 * s, h - 40 * s, tw + 24 * s, 28 * s);
    ctx.fillStyle = "#e6edf7";
    ctx.fillText(o.narration, w / 2, h - 21 * s);
    ctx.textAlign = "left";
  }
}

export class ScreenRecorder {
  private raf = 0;
  private rec: MediaRecorder | null = null;
  private chunks: BlobPart[] = [];
  private mime = "video/webm";

  get recording(): boolean {
    return this.rec !== null;
  }

  start(source: HTMLCanvasElement, getOverlay: () => RecordOverlay): void {
    if (this.rec) return;
    const comp = document.createElement("canvas");
    comp.width = source.width;
    comp.height = source.height;
    const ctx = comp.getContext("2d");
    if (!ctx) return;
    const s = comp.width / 960; // scale overlays with resolution

    const draw = () => {
      ctx.drawImage(source, 0, 0, comp.width, comp.height);
      drawOverlay(ctx, comp.width, comp.height, s, getOverlay());
      this.raf = requestAnimationFrame(draw);
    };
    draw();

    this.mime = pickVideoMime();
    const stream = comp.captureStream(30);
    this.rec = new MediaRecorder(stream, { mimeType: this.mime });
    this.chunks = [];
    this.rec.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.rec.onstop = () => {
      const blob = new Blob(this.chunks, { type: this.mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cell-movie.${this.mime.includes("mp4") ? "mp4" : "webm"}`;
      a.click();
      URL.revokeObjectURL(url);
      cancelAnimationFrame(this.raf);
    };
    this.rec.start();
  }

  stop(): void {
    if (!this.rec) return;
    this.rec.stop();
    this.rec = null;
  }
}
