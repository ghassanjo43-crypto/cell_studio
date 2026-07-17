import { describe, expect, it } from "vitest";
import {
  hasPostFX,
  nextAutoQuality,
  qualitySettings,
  resolveQuality,
} from "../components/explorer/cell/quality";

describe("quality tiers", () => {
  it("scales effects and particle density with the tier", () => {
    const low = qualitySettings("low");
    const high = qualitySettings("high");
    expect(low.bloom).toBe(false);
    expect(low.ssao).toBe(false);
    expect(high.bloom && high.dof && high.ssao).toBe(true);
    expect(high.densityScale).toBeGreaterThan(low.densityScale);
    expect(high.dpr).toBeGreaterThanOrEqual(low.dpr);
  });

  it("reports whether the post-processing composer should mount", () => {
    expect(hasPostFX(qualitySettings("low"))).toBe(false); // no effects → no composer
    expect(hasPostFX(qualitySettings("medium"))).toBe(true);
    expect(hasPostFX(qualitySettings("high"))).toBe(true);
  });

  it("steps auto quality down on low fps and up with headroom (with hysteresis)", () => {
    expect(nextAutoQuality("high", 20)).toBe("medium");
    expect(nextAutoQuality("medium", 20)).toBe("low");
    expect(nextAutoQuality("low", 20)).toBe("low"); // can't go lower
    expect(nextAutoQuality("low", 60)).toBe("medium");
    expect(nextAutoQuality("high", 60)).toBe("high"); // can't go higher
    expect(nextAutoQuality("medium", 45)).toBe("medium"); // dead-band → no change
  });

  it("resolves the mode, honouring the auto tier", () => {
    expect(resolveQuality("high", "low")).toBe("high");
    expect(resolveQuality("auto", "medium")).toBe("medium");
  });
});
