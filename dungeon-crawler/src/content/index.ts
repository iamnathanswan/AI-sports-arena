import type { LevelDef, LightDef } from './types.js';
import { TEST_CHAMBER } from './levels/testChamber.js';

export { PLAYER_CONFIG } from './player.js';
export type * from './types.js';

/** Every hand-authored level, keyed by id. Generated levels arrive in M1. */
export const LEVELS: Record<string, LevelDef> = {
  [TEST_CHAMBER.id]: TEST_CHAMBER,
};

export function getLevel(id: string): LevelDef {
  const level = LEVELS[id];
  if (!level) throw new Error(`Unknown level: ${id}`);
  return level;
}

/** The torch the player carries; travels with them rather than with a level. */
export const PLAYER_TORCH: LightDef = {
  id: 'player_torch',
  kind: 'point',
  color: 0xffb066,
  intensity: 320,
  distance: 18,
  decay: 2,
};
