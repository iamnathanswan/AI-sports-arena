/**
 * Seeded pseudo-random number generation.
 *
 * Rule for the whole project: simulation code never calls Math.random().
 * Every random decision comes from an Rng created from an explicit seed so
 * the same seed always reproduces the same world, loot and encounters.
 */

export interface Rng {
  /** Uniform float in [0, 1). */
  next(): number;
  /** Uniform float in [min, max). */
  range(min: number, max: number): number;
  /** Uniform integer in [min, max] inclusive. */
  int(min: number, max: number): number;
  /** True with the given probability (0..1). */
  chance(probability: number): boolean;
  /** Uniformly picks one element; throws on an empty list. */
  pick<T>(items: readonly T[]): T;
  /** Fisher-Yates copy of the input, left untouched. */
  shuffle<T>(items: readonly T[]): T[];
  /** Independent stream derived from this one, without consuming state. */
  fork(label: string): Rng;
  /** Current internal state, for save games and debugging. */
  state(): number;
}

/** FNV-1a over the string form of each part, so seeds can be human readable. */
export function hashSeed(...parts: Array<string | number>): number {
  let hash = 0x811c9dc5;
  for (const part of parts) {
    const text = String(part);
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193);
    }
    // Separator so ('ab', 'c') and ('a', 'bc') do not collide.
    hash ^= 0x2f;
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** mulberry32 — small, fast, and good enough for gameplay randomness. */
export function createRng(seed: number | string): Rng {
  let state = (typeof seed === 'number' ? seed : hashSeed(seed)) >>> 0;

  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  const rng: Rng = {
    next,
    range: (min, max) => min + next() * (max - min),
    int: (min, max) => min + Math.floor(next() * (max - min + 1)),
    chance: (probability) => next() < probability,
    pick: (items) => {
      if (items.length === 0) throw new Error('rng.pick called with an empty list');
      return items[Math.floor(next() * items.length)]!;
    },
    shuffle: (items) => {
      const copy = items.slice();
      for (let i = copy.length - 1; i > 0; i -= 1) {
        const j = Math.floor(next() * (i + 1));
        [copy[i], copy[j]] = [copy[j]!, copy[i]!];
      }
      return copy;
    },
    fork: (label) => createRng(hashSeed(state, label)),
    state: () => state,
  };

  return rng;
}
