import { describe, expect, it } from 'vitest';
import {
  aabbFromCenterSize,
  bodyAabb,
  isSupported,
  moveWithCollisions,
  overlaps,
  type Aabb,
  type BodyShape,
} from '../src/sim/collision.js';
import { buildColliders } from '../src/sim/level.js';
import { TEST_CHAMBER } from '../src/content/levels/testChamber.js';

const SHAPE: BodyShape = { radius: 0.35, height: 1.8 };

const floor: Aabb = aabbFromCenterSize({ x: 0, y: -0.5, z: 0 }, { x: 20, y: 1, z: 20 });
const wallEast: Aabb = aabbFromCenterSize({ x: 3, y: 2, z: 0 }, { x: 1, y: 4, z: 20 });

describe('aabb helpers', () => {
  it('detects overlap and separation', () => {
    const a = aabbFromCenterSize({ x: 0, y: 0, z: 0 }, { x: 1, y: 1, z: 1 });
    const b = aabbFromCenterSize({ x: 0.5, y: 0, z: 0 }, { x: 1, y: 1, z: 1 });
    const c = aabbFromCenterSize({ x: 5, y: 0, z: 0 }, { x: 1, y: 1, z: 1 });
    expect(overlaps(a, b)).toBe(true);
    expect(overlaps(a, c)).toBe(false);
  });

  it('builds a feet-origin body box', () => {
    const box = bodyAabb({ x: 1, y: 2, z: 3 }, SHAPE);
    expect(box.min).toEqual({ x: 0.65, y: 2, z: 2.65 });
    expect(box.max).toEqual({ x: 1.35, y: 3.8, z: 3.35 });
  });
});

describe('moveWithCollisions', () => {
  it('moves freely when nothing is in the way', () => {
    const result = moveWithCollisions({ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: -2 }, SHAPE, [floor]);
    expect(result.position.x).toBeCloseTo(1, 6);
    expect(result.position.z).toBeCloseTo(-2, 6);
    expect(result.blockedX).toBe(false);
  });

  it('stops at a wall instead of tunnelling through it', () => {
    const result = moveWithCollisions({ x: 0, y: 0, z: 0 }, { x: 10, y: 0, z: 0 }, SHAPE, [wallEast]);
    expect(result.blockedX).toBe(true);
    // Wall face is at x = 2.5; the body may not push past it minus its radius.
    expect(result.position.x).toBeLessThanOrEqual(2.5 - SHAPE.radius);
    expect(result.position.x).toBeCloseTo(2.5 - SHAPE.radius, 3);
  });

  it('slides along a wall rather than sticking to it', () => {
    const result = moveWithCollisions({ x: 2, y: 0, z: 0 }, { x: 2, y: 0, z: 3 }, SHAPE, [wallEast]);
    expect(result.blockedX).toBe(true);
    expect(result.blockedZ).toBe(false);
    expect(result.position.z).toBeCloseTo(3, 6);
  });

  it('lands on the floor and reports grounded', () => {
    const result = moveWithCollisions({ x: 0, y: 3, z: 0 }, { x: 0, y: -5, z: 0 }, SHAPE, [floor]);
    expect(result.grounded).toBe(true);
    expect(result.position.y).toBeCloseTo(0, 3);
  });

  it('reports a ceiling hit without grounding', () => {
    const ceiling = aabbFromCenterSize({ x: 0, y: 4.25, z: 0 }, { x: 20, y: 0.5, z: 20 });
    const result = moveWithCollisions({ x: 0, y: 2.5, z: 0 }, { x: 0, y: 3, z: 0 }, SHAPE, [ceiling]);
    expect(result.hitCeiling).toBe(true);
    expect(result.grounded).toBe(false);
    expect(result.position.y).toBeLessThanOrEqual(4 - SHAPE.height);
  });

  it('never leaves the body intersecting geometry, over many random-ish steps', () => {
    const colliders = buildColliders(TEST_CHAMBER);
    let position = { ...TEST_CHAMBER.playerSpawn };
    for (let i = 0; i < 2000; i += 1) {
      const angle = i * 0.37;
      const delta = { x: Math.cos(angle) * 0.4, y: Math.sin(angle * 0.7) * 0.4, z: Math.sin(angle) * 0.4 };
      position = moveWithCollisions(position, delta, SHAPE, colliders).position;
      const box = bodyAabb(position, SHAPE);
      for (const collider of colliders) {
        expect(overlaps(box, collider)).toBe(false);
      }
    }
  });

  it('does not mutate the position it was given', () => {
    const start = { x: 0, y: 0, z: 0 };
    moveWithCollisions(start, { x: 5, y: -5, z: 5 }, SHAPE, [floor, wallEast]);
    expect(start).toEqual({ x: 0, y: 0, z: 0 });
  });
});

describe('isSupported', () => {
  it('is true standing on the floor and false in mid-air', () => {
    expect(isSupported({ x: 0, y: 0, z: 0 }, SHAPE, [floor])).toBe(true);
    expect(isSupported({ x: 0, y: 2, z: 0 }, SHAPE, [floor])).toBe(false);
  });
});

describe('buildColliders', () => {
  it('includes every solid brush from the level data', () => {
    const colliders = buildColliders(TEST_CHAMBER);
    expect(colliders).toHaveLength(TEST_CHAMBER.brushes.filter((b) => b.solid !== false).length);
  });
});
