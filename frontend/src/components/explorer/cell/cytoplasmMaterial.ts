// The cytoplasm as a translucent volume: a depth-graded interior that reads as a dense,
// light-scattering gel rather than a flat tinted sphere. Rendered on the sphere's back
// faces so you look *into* the volume — brighter, denser core fading to a clearer rim,
// with a slow internal shimmer. Cheap (no textures, no lighting) and VR-safe (standard
// matrices only). Colour + glow are driven from the biology (status colour + metabolic
// activity), so it is not decorative.

import * as THREE from "three";

const VERT = /* glsl */ `
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  varying vec3 vLocal;
  void main() {
    vLocal = position;
    vec4 worldPos = modelMatrix * vec4(position, 1.0);
    vNormalW = normalize(mat3(modelMatrix) * normal);
    vViewDir = normalize(cameraPosition - worldPos.xyz);
    gl_Position = projectionMatrix * viewMatrix * worldPos;
  }
`;

const FRAG = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uCore;
  uniform float uTime;
  uniform float uActivity;
  uniform float uOpacity;
  uniform float uScale;
  uniform float uSeed;
  varying vec3 vNormalW;
  varying vec3 vViewDir;
  varying vec3 vLocal;

  // Cheap 3D value noise (no textures) → procedural cytoplasmic density.
  float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }
  float vnoise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i + vec3(0,0,0)), hash(i + vec3(1,0,0)), f.x),
                   mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
                   mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
  }
  float fbm(vec3 p) {
    return 0.6 * vnoise(p) + 0.3 * vnoise(p * 2.03 + 11.0) + 0.1 * vnoise(p * 4.1 + 37.0);
  }
  // Ridged/turbulent fbm — soft billowing structure (protein haze, not smooth cloud).
  float turb(vec3 p) {
    float f = 0.0, a = 0.55, w = 0.0;
    for (int i = 0; i < 4; i++) {
      f += a * abs(vnoise(p) - 0.5) * 2.0;
      w += a; p = p * 2.02 + 19.0; a *= 0.5;
    }
    return f / w;
  }

  void main() {
    // Back-face rim: thickest where we look through the most volume (edge-on) →
    // visibility naturally decreases with depth (no hard transparency).
    float facing = clamp(dot(normalize(vNormalW), normalize(vViewDir)), 0.0, 1.0);
    float depth = pow(1.0 - facing, 1.6);
    // Denser, brighter toward the geometric core.
    float core = smoothstep(1.0, 0.0, length(vLocal));
    // Domain-warped turbulent density — billowing, cloudy suspended-protein haze that
    // slowly churns (soft turbulence). uScale sets this layer's granularity, uSeed its
    // phase, so nested shells read as distinct density layers.
    vec3 q = vLocal * uScale + vec3(uSeed, uTime * 0.05, uTime * 0.03);
    float warp = fbm(q * 0.6);
    float dens = turb(q + warp);
    // Light scattering: brighter where density is high and we graze the surface. A
    // stronger, forward-scattering term so the gel glows softly with transmitted light
    // (a hydrogel lit from within), reading as a thick viscous medium not thin fog.
    float scatter = pow(dens, 1.4) * (0.5 + 0.7 * depth);
    // Slow internal shimmer — metabolism-gated glow.
    float shimmer = 0.5 + 0.5 * sin(vLocal.x * 5.0 + uTime * 0.6)
                              * sin(vLocal.y * 4.0 - uTime * 0.5);
    vec3 col = mix(uColor, uCore, core * 0.85);
    col += uCore * shimmer * 0.14 * uActivity;      // metabolic glow
    col += uCore * scatter * 0.42;                  // scattered light in dense regions
    col += uColor * (dens - 0.5) * 0.14;            // cloudy density tint
    float cloud = 0.62 + 0.85 * dens;               // local density variation (raised floor)
    // Alpha floor raised across the board so the medium is always present — even looking
    // straight through the middle there is thick gel, never a clear window of empty air.
    float a = uOpacity * (0.58 + 0.42 * depth + 0.34 * core) * cloud;
    gl_FragColor = vec4(col, clamp(a, 0.0, 0.97));
  }
`;

export interface CytoplasmOptions {
  color?: string;
  scale?: number;   // noise granularity for this density layer
  seed?: number;    // phase offset so nested layers differ
  opacity?: number;
}

export function makeCytoplasmMaterial(opts: CytoplasmOptions = {}): THREE.ShaderMaterial {
  const { color = "#191a42", scale = 3, seed = 0, opacity = 0.22 } = opts;
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uCore: { value: new THREE.Color("#2a6ad0") },
      uTime: { value: 0 },
      uActivity: { value: 1 },
      uOpacity: { value: opacity },
      uScale: { value: scale },
      uSeed: { value: seed },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,
    side: THREE.BackSide,
    blending: THREE.NormalBlending,
    toneMapped: false,
  });
}
