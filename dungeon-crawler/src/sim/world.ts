/**
 * The simulation world: a component-bag entity store plus the level's static
 * collision data. Deliberately not a class hierarchy — entities are plain
 * objects with optional components, and systems query by component key.
 */

import type { LevelDef, PlayerConfigDef } from '../content/types.js';
import type { Aabb } from './collision.js';
import type { InputFrame } from './input.js';
import { buildColliders } from './level.js';
import type { Vec3 } from './math.js';
import { createPlayerState, stepPlayer, type PlayerState } from './player.js';
import { createRng, hashSeed, type Rng } from './rng.js';

export interface Components {
  /** Where a thing is in the world, for anything that has a position. */
  transform?: { position: Vec3; yaw: number };
  /** Present only on the locally controlled player. */
  player?: PlayerState;
  /** Free-form tag list for cheap filtering. */
  tags?: string[];
}

export interface Entity extends Components {
  readonly id: number;
}

export interface WorldOptions {
  level: LevelDef;
  playerConfig: PlayerConfigDef;
  /** Master seed for this run; per-level RNGs derive from it plus depth. */
  worldSeed: number;
  depth?: number;
}

export class World {
  readonly level: LevelDef;
  readonly colliders: readonly Aabb[];
  readonly playerConfig: PlayerConfigDef;
  readonly worldSeed: number;
  readonly depth: number;
  /** One PRNG per level, derived from worldSeed + depth. */
  readonly rng: Rng;

  /** Simulation ticks elapsed since the world was created. */
  tick = 0;

  private readonly entities = new Map<number, Entity>();
  private nextEntityId = 1;

  readonly player: Entity;

  constructor(options: WorldOptions) {
    this.level = options.level;
    this.playerConfig = options.playerConfig;
    this.worldSeed = options.worldSeed;
    this.depth = options.depth ?? 0;
    this.colliders = buildColliders(options.level);
    this.rng = createRng(hashSeed(this.worldSeed, 'level', this.depth));

    const spawn = options.level.playerSpawn;
    const playerState = createPlayerState(spawn, options.level.playerSpawnYaw);
    this.player = this.spawn({
      player: playerState,
      transform: { position: playerState.position, yaw: playerState.yaw },
      tags: ['player'],
    });
  }

  spawn(components: Components): Entity {
    const entity: Entity = { id: this.nextEntityId++, ...components };
    this.entities.set(entity.id, entity);
    return entity;
  }

  destroy(id: number): void {
    this.entities.delete(id);
  }

  get(id: number): Entity | undefined {
    return this.entities.get(id);
  }

  /** All entities carrying every one of the given component keys. */
  query<K extends keyof Components>(...keys: K[]): Array<Entity & Required<Pick<Components, K>>> {
    const matches: Array<Entity & Required<Pick<Components, K>>> = [];
    for (const entity of this.entities.values()) {
      if (keys.every((key) => entity[key] !== undefined)) {
        matches.push(entity as Entity & Required<Pick<Components, K>>);
      }
    }
    return matches;
  }

  /** Advances the whole simulation by one fixed step. */
  step(input: InputFrame, dt: number): void {
    for (const entity of this.query('player')) {
      stepPlayer(entity.player, input, this.colliders, dt, this.playerConfig);
      if (entity.transform) {
        entity.transform.position = entity.player.position;
        entity.transform.yaw = entity.player.yaw;
      }
    }
    this.tick += 1;
  }

  get playerState(): PlayerState {
    return this.player.player!;
  }
}
