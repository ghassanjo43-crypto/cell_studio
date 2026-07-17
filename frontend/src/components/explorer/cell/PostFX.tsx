// Post-processing for a professional scientific look: bloom (emissive molecules /
// signalling glow), ambient occlusion, depth of field and a subtle vignette, tuned by
// the active quality tier.
//
// IMPORTANT: the EffectComposer is NOT compatible with a WebXR session (it renders a
// fullscreen pass that breaks stereo rendering), so it is disabled while in VR — the
// scene then renders normally through the headset.

import { Bloom, DepthOfField, EffectComposer, SSAO, Vignette } from "@react-three/postprocessing";
import { useXR } from "@react-three/xr";
import { BlendFunction } from "postprocessing";
import type { ReactElement } from "react";
import type { QualitySettings } from "./quality";

export function PostFX({ settings, cinematic = false }: { settings: QualitySettings; cinematic?: boolean }) {
  const inXR = useXR((s) => !!s.session);
  // In cinematic mode, bloom + DoF turn on even at lower tiers for immersion.
  const bloom = settings.bloom || cinematic;
  const dof = settings.dof || cinematic;
  if (inXR || (!settings.ssao && !bloom && !dof && !settings.vignette)) return null;

  const effects: ReactElement[] = [];
  if (settings.ssao) {
    effects.push(
      <SSAO
        key="ssao"
        blendFunction={BlendFunction.MULTIPLY}
        samples={16}
        radius={0.08}
        intensity={14}
        luminanceInfluence={0.6}
        worldDistanceThreshold={20}
        worldDistanceFalloff={5}
        worldProximityThreshold={0.4}
        worldProximityFalloff={0.1}
      />,
    );
  }
  if (bloom) {
    effects.push(
      <Bloom key="bloom" intensity={cinematic ? 1.7 : 1.15} luminanceThreshold={cinematic ? 0.2 : 0.28} luminanceSmoothing={0.35} mipmapBlur />,
    );
  }
  if (dof) {
    effects.push(<DepthOfField key="dof" focusDistance={0.025} focalLength={cinematic ? 0.05 : 0.045} bokehScale={cinematic ? 4.6 : 3} />);
  }
  if (settings.vignette || cinematic) {
    effects.push(<Vignette key="vig" eskil={false} offset={cinematic ? 0.22 : 0.3} darkness={cinematic ? 0.82 : 0.62} />);
  }

  // Re-key so the composer rebuilds when the enabled effect set changes.
  const key = `${settings.ssao}-${bloom}-${dof}-${settings.vignette || cinematic}`;
  return (
    <EffectComposer key={key} enableNormalPass={settings.ssao} multisampling={settings.ssao ? 0 : 4}>
      {effects}
    </EffectComposer>
  );
}
