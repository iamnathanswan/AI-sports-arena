/**
 * Plain-object vector math. Deliberately not three.js Vector3 so simulation
 * code stays importable in a headless test run.
 */

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export const vec3 = (x = 0, y = 0, z = 0): Vec3 => ({ x, y, z });

export const copyVec3 = (v: Vec3): Vec3 => ({ x: v.x, y: v.y, z: v.z });

export const setVec3 = (target: Vec3, source: Vec3): Vec3 => {
  target.x = source.x;
  target.y = source.y;
  target.z = source.z;
  return target;
};

export const addScaled = (target: Vec3, delta: Vec3, scale: number): Vec3 => {
  target.x += delta.x * scale;
  target.y += delta.y * scale;
  target.z += delta.z * scale;
  return target;
};

export const lengthXZ = (v: Vec3): number => Math.hypot(v.x, v.z);

export const clamp = (value: number, min: number, max: number): number =>
  value < min ? min : value > max ? max : value;

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export const lerpVec3 = (a: Vec3, b: Vec3, t: number): Vec3 => ({
  x: lerp(a.x, b.x, t),
  y: lerp(a.y, b.y, t),
  z: lerp(a.z, b.z, t),
});

/** Shortest-path angle interpolation, so yaw wrapping never spins the camera. */
export const lerpAngle = (a: number, b: number, t: number): number => {
  const twoPi = Math.PI * 2;
  let delta = (b - a) % twoPi;
  if (delta > Math.PI) delta -= twoPi;
  if (delta < -Math.PI) delta += twoPi;
  return a + delta * t;
};

/** Moves `current` toward `target` by at most `maxDelta`. */
export const moveToward = (current: number, target: number, maxDelta: number): number => {
  const diff = target - current;
  if (Math.abs(diff) <= maxDelta) return target;
  return current + Math.sign(diff) * maxDelta;
};
