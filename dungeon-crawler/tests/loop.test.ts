import { describe, expect, it } from 'vitest';
import { FixedTimestep, SIM_DT } from '../src/sim/loop.js';

describe('FixedTimestep', () => {
  it('runs exactly one step per sim interval', () => {
    let steps = 0;
    const loop = new FixedTimestep(() => (steps += 1));
    loop.advance(SIM_DT);
    expect(steps).toBe(1);
  });

  it('accumulates fractional time instead of dropping it', () => {
    let steps = 0;
    const loop = new FixedTimestep(() => (steps += 1));
    for (let i = 0; i < 6; i += 1) loop.advance(SIM_DT / 3);
    expect(steps).toBe(2);
  });

  it('always hands the same dt to the step function', () => {
    const seen: number[] = [];
    const loop = new FixedTimestep((dt) => seen.push(dt));
    loop.advance(SIM_DT * 3.5);
    expect(new Set(seen)).toEqual(new Set([SIM_DT]));
  });

  it('reports an interpolation alpha in [0, 1)', () => {
    const loop = new FixedTimestep(() => {});
    const { alpha } = loop.advance(SIM_DT * 1.5);
    expect(alpha).toBeGreaterThanOrEqual(0);
    expect(alpha).toBeLessThan(1);
    expect(alpha).toBeCloseTo(0.5, 6);
  });

  it('clamps a huge frame instead of spiralling', () => {
    let steps = 0;
    const loop = new FixedTimestep(() => (steps += 1));
    const stats = loop.advance(30);
    expect(steps).toBeLessThanOrEqual(5);
    expect(stats.clamped).toBe(true);
    expect(stats.alpha).toBe(0);
  });
});
