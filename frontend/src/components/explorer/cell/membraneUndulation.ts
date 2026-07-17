// Shared membrane undulation: patches a MeshStandardMaterial (via onBeforeCompile so
// it keeps full PBR lighting + shadows + stereo/VR) with the same subtle sine
// displacement used by the Fresnel rim shader, so every membrane layer — outer
// leaflet, inner wall, rim — wobbles as one coherent surface. The amplitude is driven
// from the simulation (thermal base + extra sway when membrane integrity drops).

import * as THREE from "three";

// Multi-octave surface displacement: a slow large undulation (loss of tension) +
// mid-frequency wrinkles + fine thermal ripples. `uAmp` scales tension loss (∝ 1 −
// integrity, so damaged membranes visibly slacken); `uRipple` scales the fast
// active-transport shimmer. The result reads as a living, wrinkling bilayer rather
// than a smooth sphere.
const UNDULATE_GLSL = /* glsl */ `
  float _w1 = sin(position.x * 6.0 + uTime * 1.3)
            * sin(position.y * 5.0 + uTime * 1.1)
            * sin(position.z * 6.0 + uTime * 0.9);
  float _w2 = sin(position.x * 14.0 - uTime * 2.1)
            * sin(position.y * 13.0 + uTime * 1.7)
            * sin(position.z * 15.0 - uTime * 1.9);
  float _w3 = sin(position.x * 27.0 + uTime * 3.4)
            * sin(position.z * 24.0 - uTime * 2.9);
  float _disp = _w1 * uAmp + _w2 * uAmp * 0.45 + _w3 * (uAmp * 0.25 + uRipple);
  transformed += normal * _disp;
`;

/**
 * Patch a MeshStandardMaterial with multi-octave vertex undulation and return a setter
 * to drive the `uTime`/`uAmp`/`uRipple` uniforms each frame. The material must be
 * re-created (or have `needsUpdate = true`) after patching so the shader recompiles.
 */
export function applyMembraneUndulation(
  mat: THREE.MeshStandardMaterial,
): (time: number, amp: number, ripple: number) => void {
  const uniforms = { uTime: { value: 0 }, uAmp: { value: 0 }, uRipple: { value: 0 } };
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = uniforms.uTime;
    shader.uniforms.uAmp = uniforms.uAmp;
    shader.uniforms.uRipple = uniforms.uRipple;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nuniform float uTime;\nuniform float uAmp;\nuniform float uRipple;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\n" + UNDULATE_GLSL);
  };
  // Distinguish this program from the un-patched standard material in three's cache.
  mat.customProgramCacheKey = () => "membrane-undulate-v2";
  return (time: number, amp: number, ripple: number) => {
    uniforms.uTime.value = time;
    uniforms.uAmp.value = amp;
    uniforms.uRipple.value = ripple;
  };
}
