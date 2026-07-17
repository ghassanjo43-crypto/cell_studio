// Camera controls. Browser: OrbitControls with a small minimum distance so the user
// can zoom right into the nucleoid. In "explore" mode, WASD/QE fly the camera (and
// its orbit target) through the cytoplasm. Disabled inside VR, where the headset
// drives the camera.

import { useFrame, useThree } from "@react-three/fiber";
import { useXR } from "@react-three/xr";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface FocusRequest {
  distance: number;
  target: [number, number, number];
  nonce: number;
  duration?: number; // seconds for the easing (default 0.8)
}

interface Anim {
  t: number;
  dur: number;
  fromPos: THREE.Vector3;
  toPos: THREE.Vector3;
  fromTgt: THREE.Vector3;
  toTgt: THREE.Vector3;
}

export function Controls({ explore, focus, cinematic = false }: { explore: boolean; focus?: FocusRequest | null; cinematic?: boolean }) {
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const inXR = useXR((s) => !!s.session);
  const controlsRef = useRef<OrbitControls | null>(null);
  const keys = useRef<Record<string, boolean>>({});
  const anim = useRef<Anim | null>(null);

  const forward = useMemo(() => new THREE.Vector3(), []);
  const right = useMemo(() => new THREE.Vector3(), []);
  const move = useMemo(() => new THREE.Vector3(), []);
  const breath = useRef({ x: 0, y: 0 }); // last-applied breathing offset (driftless)
  const probe = useRef({ x: 0, y: 0, z: 0 }); // last-applied floating-probe translation (driftless)

  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.028; // heavy documentary inertia → slow, weighty glide
    controls.rotateSpeed = 0.7;
    controls.zoomSpeed = 0.7;
    controls.minDistance = 0.3;
    controls.maxDistance = 25;
    controlsRef.current = controls;
    return () => controls.dispose();
  }, [camera, gl]);

  // Focus mode: animate the camera to frame a structure.
  useEffect(() => {
    const c = controlsRef.current;
    if (!focus || !c || inXR) return;
    const toTgt = new THREE.Vector3(...focus.target);
    const dir = camera.position.clone().sub(c.target);
    if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1);
    dir.normalize();
    anim.current = {
      t: 0,
      dur: Math.max(0.1, focus.duration ?? 0.8),
      fromPos: camera.position.clone(),
      toPos: toTgt.clone().add(dir.multiplyScalar(focus.distance)),
      fromTgt: c.target.clone(),
      toTgt,
    };
  }, [focus, camera, inXR]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      keys.current[e.code] = true;
    };
    const up = (e: KeyboardEvent) => {
      keys.current[e.code] = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  useFrame((state, delta) => {
    const c = controlsRef.current;
    if (!c) return;
    c.enabled = !inXR;

    // Cinematic mode: gentle continuous drift for a filmic feel (paused during a
    // scripted focus move, in explore/fly mode, or in VR where the headset drives).
    c.autoRotate = cinematic && !explore && !inXR && !anim.current;
    c.autoRotateSpeed = 0.16; // very slow documentary drift

    // Inside-cell breathing: a tiny organic sway of the aim point when cinematic and
    // close in. Applied as a driftless per-frame delta so it never accumulates and
    // never fights the user's own control.
    // A gentle handheld-documentary breathing of the aim point is always on (except in
    // explore/fly, VR, or a scripted focus move), so the camera never feels locked to a
    // rig; cinematic mode breathes a little wider. Amplitude fades in as you move inside.
    const breatheOn = !inXR && !anim.current && !explore;
    const amp = cinematic ? 0.02 : 0.011;
    const t = state.clock.elapsedTime;
    const inside = THREE.MathUtils.clamp(1 - (camera.position.length() - 0.5) / 3, 0, 1);
    // Two summed octaves → an organic, non-repeating handheld sway rather than a clean
    // sine wobble (documentary operator, not a motor).
    const bx = breatheOn ? (Math.sin(t * 0.5) + 0.4 * Math.sin(t * 1.3 + 2.1)) * amp * inside : 0;
    const by = breatheOn ? (Math.sin(t * 0.37 + 1.3) + 0.4 * Math.sin(t * 1.1 + 0.7)) * amp * inside : 0;
    c.target.x += bx - breath.current.x;
    c.target.y += by - breath.current.y;
    breath.current.x = bx;
    breath.current.y = by;

    // Floating-probe drift: a tiny low-frequency translation of BOTH camera and target
    // by the same vector, so the whole viewpoint gently floats through the cytoplasm (as
    // if suspended in fluid) without changing the orbit relationship — OrbitControls
    // derives its spherical from (position − target), which this leaves untouched, so it
    // never fights the user. Driftless (previous offset subtracted); off in explore/VR.
    const pAmp = (cinematic ? 0.03 : 0.018) * inside;
    const px = breatheOn ? Math.sin(t * 0.23 + 0.5) * pAmp : 0;
    const py = breatheOn ? Math.sin(t * 0.19 + 2.2) * pAmp * 0.7 : 0;
    const pz = breatheOn ? Math.sin(t * 0.27 + 4.1) * pAmp : 0;
    camera.position.x += px - probe.current.x;
    camera.position.y += py - probe.current.y;
    camera.position.z += pz - probe.current.z;
    c.target.x += px - probe.current.x;
    c.target.y += py - probe.current.y;
    c.target.z += pz - probe.current.z;
    probe.current.x = px;
    probe.current.y = py;
    probe.current.z = pz;

    // Focus animation (overrides manual control briefly).
    if (anim.current && !inXR) {
      const a = anim.current;
      a.t = Math.min(1, a.t + delta / a.dur);
      const e = a.t < 0.5 ? 2 * a.t * a.t : 1 - Math.pow(-2 * a.t + 2, 2) / 2; // easeInOut
      camera.position.lerpVectors(a.fromPos, a.toPos, e);
      c.target.lerpVectors(a.fromTgt, a.toTgt, e);
      if (a.t >= 1) anim.current = null;
      c.update();
      return;
    }

    if (explore && !inXR) {
      const speed = 3 * delta;
      forward.subVectors(c.target, camera.position).normalize();
      right.crossVectors(forward, camera.up).normalize();
      move.set(0, 0, 0);
      const k = keys.current;
      if (k["KeyW"]) move.addScaledVector(forward, speed);
      if (k["KeyS"]) move.addScaledVector(forward, -speed);
      if (k["KeyD"]) move.addScaledVector(right, speed);
      if (k["KeyA"]) move.addScaledVector(right, -speed);
      if (k["KeyE"] || k["Space"]) move.addScaledVector(camera.up, speed);
      if (k["KeyQ"] || k["ShiftLeft"]) move.addScaledVector(camera.up, -speed);
      if (move.lengthSq() > 0) {
        camera.position.add(move);
        c.target.add(move);
      }
    }
    c.update();
  });

  return null;
}
