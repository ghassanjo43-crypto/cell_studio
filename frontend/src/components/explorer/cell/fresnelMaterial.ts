// A lightweight Fresnel rim shader — the view-dependent edge glow that reads as a
// translucent cell membrane / cytoplasm boundary in scientific illustrations. Cheap
// (no lighting, no textures) and VR-safe.

import * as THREE from "three";

const VERT = /* glsl */ `
  uniform float uTime;
  uniform float uAmp;
  uniform float uRipple;
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  void main() {
    // Multi-octave membrane undulation (tension loss + wrinkles + thermal ripple),
    // matching membraneUndulation.ts so the rim rides the same living surface.
    float w1 = sin(position.x * 6.0 + uTime * 1.3)
             * sin(position.y * 5.0 + uTime * 1.1)
             * sin(position.z * 6.0 + uTime * 0.9);
    float w2 = sin(position.x * 14.0 - uTime * 2.1)
             * sin(position.y * 13.0 + uTime * 1.7)
             * sin(position.z * 15.0 - uTime * 1.9);
    float w3 = sin(position.x * 27.0 + uTime * 3.4)
             * sin(position.z * 24.0 - uTime * 2.9);
    vec3 disp = position + normal * (w1 * uAmp + w2 * uAmp * 0.45 + w3 * (uAmp * 0.25 + uRipple));
    vec4 worldPos = modelMatrix * vec4(disp, 1.0);
    vNormalW = normalize(mat3(modelMatrix) * normal);
    vViewDir = normalize(cameraPosition - worldPos.xyz);
    gl_Position = projectionMatrix * viewMatrix * worldPos;
  }
`;

const FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform float uPower;
  uniform float uIntensity;
  uniform float uOpacity;
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  void main() {
    float facing = clamp(dot(normalize(vNormalW), normalize(vViewDir)), 0.0, 1.0);
    // Fresnel rim + a soft internal glow (thin translucent-shell scatter) toward the
    // centre, so the membrane reads as a glowing translucent surface, not a hard edge.
    float f = pow(1.0 - facing, uPower);
    float innerGlow = pow(facing, 3.0) * 0.18;
    gl_FragColor = vec4(uColor * uIntensity, (f + innerGlow) * uOpacity);
  }
`;

export function makeFresnelMaterial(color = "#60a5fa"): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uPower: { value: 2.4 },
      uIntensity: { value: 1.0 },
      uOpacity: { value: 0.6 },
      uTime: { value: 0 },
      uAmp: { value: 0 },
      uRipple: { value: 0 },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,
    side: THREE.FrontSide,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
  });
}
