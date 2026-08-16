/**
 * Axis-aligned box collision against static level geometry.
 *
 * The player is modelled as an upright box whose origin sits at its feet.
 * Movement is resolved one axis at a time (X, Z, then Y) which is stable for
 * the axis-aligned rooms and corridors this game generates, and keeps the
 * whole thing a pure function of (position, delta, colliders).
 */

import type { Vec3 } from './math.js';

export interface Aabb {
  min: Vec3;
  max: Vec3;
}

/** Upright collision volume: a box of `2 * radius` footprint and `height` tall. */
export interface BodyShape {
  radius: number;
  height: number;
}

export type Axis = 'x' | 'y' | 'z';

/** Small gap kept between the body and geometry so it never re-penetrates. */
const SKIN = 1e-4;

/**
 * Longest distance any single sweep may cover. Larger deltas are split into
 * sub-steps so a fast body cannot pass straight through a thin wall between
 * two overlap tests.
 */
const MAX_SWEEP_DISTANCE = 0.15;

export const aabbFromCenterSize = (center: Vec3, size: Vec3): Aabb => ({
  min: { x: center.x - size.x / 2, y: center.y - size.y / 2, z: center.z - size.z / 2 },
  max: { x: center.x + size.x / 2, y: center.y + size.y / 2, z: center.z + size.z / 2 },
});

/** Body AABB for a feet-origin position. */
export const bodyAabb = (feet: Vec3, shape: BodyShape): Aabb => ({
  min: { x: feet.x - shape.radius, y: feet.y, z: feet.z - shape.radius },
  max: { x: feet.x + shape.radius, y: feet.y + shape.height, z: feet.z + shape.radius },
});

export const overlaps = (a: Aabb, b: Aabb): boolean =>
  a.min.x < b.max.x &&
  a.max.x > b.min.x &&
  a.min.y < b.max.y &&
  a.max.y > b.min.y &&
  a.min.z < b.max.z &&
  a.max.z > b.min.z;

export interface MoveResult {
  /** Resolved feet position after the whole delta was applied. */
  position: Vec3;
  /** Per-axis: true when geometry stopped the move on that axis this step. */
  blockedX: boolean;
  blockedY: boolean;
  blockedZ: boolean;
  /** True when a downward move was stopped by geometry this step. */
  grounded: boolean;
  /** True when an upward move was stopped by geometry this step. */
  hitCeiling: boolean;
}

/**
 * Applies `delta` to `feet`, resolving penetration against `colliders`.
 * Neither argument is mutated.
 */
export function moveWithCollisions(
  feet: Vec3,
  delta: Vec3,
  shape: BodyShape,
  colliders: readonly Aabb[],
): MoveResult {
  const position: Vec3 = { x: feet.x, y: feet.y, z: feet.z };
  let grounded = false;
  let hitCeiling = false;

  const sweep = (axis: Axis, amount: number): boolean => {
    if (amount === 0) return false;
    position[axis] += amount;
    let blocked = false;

    for (const collider of colliders) {
      const box = bodyAabb(position, shape);
      if (!overlaps(box, collider)) continue;
      blocked = true;
      if (amount > 0) {
        position[axis] -= box.max[axis] - collider.min[axis] + SKIN;
      } else {
        position[axis] += collider.max[axis] - box.min[axis] + SKIN;
      }
    }

    return blocked;
  };

  const longest = Math.max(Math.abs(delta.x), Math.abs(delta.y), Math.abs(delta.z));
  const subSteps = Math.max(1, Math.ceil(longest / MAX_SWEEP_DISTANCE));
  const stepX = delta.x / subSteps;
  const stepY = delta.y / subSteps;
  const stepZ = delta.z / subSteps;

  let blockedX = false;
  let blockedY = false;
  let blockedZ = false;

  for (let i = 0; i < subSteps; i += 1) {
    blockedX = sweep('x', stepX) || blockedX;
    blockedZ = sweep('z', stepZ) || blockedZ;
    blockedY = sweep('y', stepY) || blockedY;
  }

  if (blockedY) {
    if (delta.y <= 0) grounded = true;
    else hitCeiling = true;
  }

  return { position, blockedX, blockedY, blockedZ, grounded, hitCeiling };
}

/** True when solid geometry sits within `probe` units under the body. */
export function isSupported(feet: Vec3, shape: BodyShape, colliders: readonly Aabb[], probe = 0.05): boolean {
  const box = bodyAabb({ x: feet.x, y: feet.y - probe, z: feet.z }, shape);
  return colliders.some((collider) => overlaps(box, collider));
}
