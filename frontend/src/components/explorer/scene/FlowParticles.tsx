// A data-driven instanced particle flow. The number of *visible* particles is set
// by the caller from real simulation data (glucose in the medium, ATP in a
// compartment, …); the motion is illustrative but the count and activity are not.

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

interface Streams {
  dirs: THREE.Vector3[];
  phases: number[];
}

function useStreams(max: number): Streams {
  return useMemo(() => {
    const dirs: THREE.Vector3[] = [];
    const phases: number[] = [];
    for (let i = 0; i < max; i++) {
      const v = new THREE.Vector3(Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random() * 2 - 1);
      if (v.lengthSq() < 1e-6) v.set(1, 0, 0);
      dirs.push(v.normalize());
      phases.push(Math.random());
    }
    return { dirs, phases };
  }, [max]);
}

export interface FlowParticlesProps {
  /** Maximum instances allocated (upper bound on `active`). */
  max: number;
  /** Number of particles actually shown — bind this to simulation data. */
  active: number;
  color: string;
  size?: number;
  speed?: number;
  emissive?: number;
  /** Compute a particle's position from its stable direction and animation phase. */
  place: (dir: THREE.Vector3, phase: number, i: number, out: THREE.Vector3) => void;
}

export function FlowParticles({ max, active, color, size = 0.06, speed = 0.4, emissive = 0.7, place }: FlowParticlesProps) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const { dirs, phases } = useStreams(max);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmp = useMemo(() => new THREE.Vector3(), []);

  useFrame((state) => {
    const mesh = ref.current;
    if (!mesh) return;
    const t = state.clock.elapsedTime;
    const n = Math.max(0, Math.min(max, Math.round(active)));
    for (let i = 0; i < n; i++) {
      const phase = (t * speed + phases[i]) % 1;
      place(dirs[i], phase, i, tmp);
      dummy.position.copy(tmp);
      // Fade in/out over the path so particles appear/vanish rather than pop.
      dummy.scale.setScalar(size * (0.5 + 0.5 * Math.sin(phase * Math.PI)));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, max]} frustumCulled={false}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={emissive} toneMapped={false} />
    </instancedMesh>
  );
}
