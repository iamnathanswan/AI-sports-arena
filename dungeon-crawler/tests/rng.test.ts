import { describe, expect, it } from 'vitest';
import { createRng, hashSeed } from '../src/sim/rng.js';

describe('seeded rng', () => {
  it('reproduces the identical stream for the same seed', () => {
    const a = createRng(1234);
    const b = createRng(1234);
    const first = Array.from({ length: 500 }, () => a.next());
    const second = Array.from({ length: 500 }, () => b.next());
    expect(first).toEqual(second);
  });

  it('produces different streams for different seeds', () => {
    const a = Array.from({ length: 50 }, createRng(1).next);
    const b = Array.from({ length: 50 }, createRng(2).next);
    expect(a).not.toEqual(b);
  });

  it('stays inside [0, 1) over 10,000 rolls and is roughly uniform', () => {
    const rng = createRng('uniformity');
    const buckets = new Array(10).fill(0);
    for (let i = 0; i < 10_000; i += 1) {
      const value = rng.next();
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
      buckets[Math.floor(value * 10)] += 1;
    }
    // Each decile should hold ~1000 samples; allow generous slack.
    for (const count of buckets) {
      expect(count).toBeGreaterThan(850);
      expect(count).toBeLessThan(1150);
    }
  });

  it('int() covers its inclusive bounds and never escapes them', () => {
    const rng = createRng('ints');
    const seen = new Set<number>();
    for (let i = 0; i < 10_000; i += 1) {
      const value = rng.int(3, 7);
      expect(Number.isInteger(value)).toBe(true);
      expect(value).toBeGreaterThanOrEqual(3);
      expect(value).toBeLessThanOrEqual(7);
      seen.add(value);
    }
    expect(seen.size).toBe(5);
  });

  it('chance() converges on the requested probability', () => {
    const rng = createRng('chance');
    let hits = 0;
    for (let i = 0; i < 10_000; i += 1) {
      if (rng.chance(0.25)) hits += 1;
    }
    expect(hits / 10_000).toBeGreaterThan(0.23);
    expect(hits / 10_000).toBeLessThan(0.27);
  });

  it('shuffle leaves the source untouched and keeps every element', () => {
    const source = [1, 2, 3, 4, 5, 6, 7, 8];
    const rng = createRng('shuffle');
    const shuffled = rng.shuffle(source);
    expect(source).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(shuffled.slice().sort((a, b) => a - b)).toEqual(source);
  });

  it('hashSeed is stable and separator-safe', () => {
    expect(hashSeed('world', 7)).toBe(hashSeed('world', 7));
    expect(hashSeed('ab', 'c')).not.toBe(hashSeed('a', 'bc'));
  });

  it('fork produces an independent, reproducible substream', () => {
    const parent = createRng(99);
    const stateBefore = parent.state();
    const forkA = parent.fork('loot');
    expect(parent.state()).toBe(stateBefore);

    const forkB = createRng(99).fork('loot');
    expect(Array.from({ length: 20 }, forkA.next)).toEqual(
      Array.from({ length: 20 }, forkB.next),
    );
  });
});
