/**
 * Turns level content data into the collision representation the simulation
 * uses. Rendering builds its own meshes from the same data independently.
 */

import type { LevelDef } from '../content/types.js';
import { aabbFromCenterSize, type Aabb } from './collision.js';

export function buildColliders(level: LevelDef): Aabb[] {
  return level.brushes
    .filter((brush) => brush.solid !== false)
    .map((brush) => aabbFromCenterSize(brush.center, brush.size));
}
