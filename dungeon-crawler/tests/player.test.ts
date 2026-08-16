import { describe, expect, it } from 'vitest';
import { PLAYER_CONFIG } from '../src/content/player.js';
import { TEST_CHAMBER } from '../src/content/levels/testChamber.js';
import { emptyInput, type InputFrame } from '../src/sim/input.js';
import { buildColliders } from '../src/sim/level.js';
import { SIM_DT } from '../src/sim/loop.js';
import { createPlayerState, stepPlayer, wishDirection } from '../src/sim/player.js';
import { World } from '../src/sim/world.js';

const colliders = buildColliders(TEST_CHAMBER);

/** Unbounded floor, for tests about acceleration rather than geometry. */
const openFloor = buildColliders({
  ...TEST_CHAMBER,
  brushes: [
    {
      id: 'floor',
      center: { x: 0, y: -0.5, z: 0 },
      size: { x: 400, y: 1, z: 400 },
      material: 'floor',
    },
  ],
});

const input = (overrides: Partial<InputFrame> = {}): InputFrame => ({ ...emptyInput(), ...overrides });

const spawnPlayer = () => createPlayerState(TEST_CHAMBER.playerSpawn, 0);

const run = (
  state: ReturnType<typeof spawnPlayer>,
  frame: InputFrame,
  ticks: number,
  world = colliders,
) => {
  for (let i = 0; i < ticks; i += 1) stepPlayer(state, frame, world, SIM_DT, PLAYER_CONFIG);
};

describe('look', () => {
  it('turns left on negative pointer delta and wraps yaw into [0, 2pi)', () => {
    const state = spawnPlayer();
    run(state, input({ lookDx: 400 }), 1);
    expect(state.yaw).toBeGreaterThan(0);
    expect(state.yaw).toBeLessThan(Math.PI * 2);
  });

  it('clamps pitch so the camera can never flip over', () => {
    const state = spawnPlayer();
    run(state, input({ lookDy: -5000 }), 20);
    expect(state.pitch).toBeCloseTo(PLAYER_CONFIG.maxPitch, 6);
    run(state, input({ lookDy: 10000 }), 20);
    expect(state.pitch).toBeCloseTo(-PLAYER_CONFIG.maxPitch, 6);
  });
});

describe('wishDirection', () => {
  it('is zero without input', () => {
    const state = spawnPlayer();
    expect(wishDirection(state, input())).toEqual({ x: 0, y: 0, z: 0 });
  });

  it('sends forward down -Z at yaw 0 and down -X at yaw 90 degrees', () => {
    const state = spawnPlayer();
    const forward = wishDirection(state, input({ moveZ: 1 }));
    expect(forward.z).toBeCloseTo(-1, 6);
    expect(forward.x).toBeCloseTo(0, 6);

    state.yaw = Math.PI / 2;
    const turned = wishDirection(state, input({ moveZ: 1 }));
    expect(turned.x).toBeCloseTo(-1, 6);
    expect(turned.z).toBeCloseTo(0, 6);
  });

  it('normalises diagonals so strafe-running is not faster', () => {
    const state = spawnPlayer();
    const diagonal = wishDirection(state, input({ moveX: 1, moveZ: 1 }));
    expect(Math.hypot(diagonal.x, diagonal.z)).toBeCloseTo(1, 6);
  });
});

describe('movement', () => {
  it('settles on the floor under gravity', () => {
    const state = createPlayerState({ x: 0, y: 2, z: 4 }, 0);
    run(state, input(), 120);
    expect(state.grounded).toBe(true);
    expect(state.position.y).toBeCloseTo(0, 2);
    expect(state.velocity.y).toBe(0);
  });

  it('accelerates to walk speed and no further', () => {
    const state = spawnPlayer();
    run(state, input({ moveZ: 1 }), 120, openFloor);
    const speed = Math.hypot(state.velocity.x, state.velocity.z);
    expect(speed).toBeGreaterThan(PLAYER_CONFIG.walkSpeed * 0.95);
    expect(speed).toBeLessThanOrEqual(PLAYER_CONFIG.walkSpeed + 1e-6);
  });

  it('sprints faster than it walks', () => {
    const walker = spawnPlayer();
    const sprinter = spawnPlayer();
    run(walker, input({ moveZ: 1 }), 120, openFloor);
    run(sprinter, input({ moveZ: 1, sprint: true }), 120, openFloor);
    const walkSpeed = Math.hypot(walker.velocity.x, walker.velocity.z);
    const sprintSpeed = Math.hypot(sprinter.velocity.x, sprinter.velocity.z);
    expect(sprintSpeed / walkSpeed).toBeCloseTo(PLAYER_CONFIG.sprintMultiplier, 1);
  });

  it('comes to a stop from friction when input is released', () => {
    const state = spawnPlayer();
    run(state, input({ moveZ: 1 }), 60, openFloor);
    run(state, input(), 60, openFloor);
    expect(Math.hypot(state.velocity.x, state.velocity.z)).toBe(0);
  });

  it('jumps only while grounded', () => {
    const state = spawnPlayer();
    run(state, input(), 30);
    expect(state.grounded).toBe(true);

    run(state, input({ jump: true }), 1);
    expect(state.grounded).toBe(false);
    expect(state.velocity.y).toBeGreaterThan(0);

    const apexVelocity = state.velocity.y;
    run(state, input({ jump: true }), 1);
    expect(state.velocity.y).toBeLessThan(apexVelocity);
  });

  it('cannot walk out through the chamber walls', () => {
    for (const dir of [
      { moveZ: 1 },
      { moveZ: -1 },
      { moveX: 1 },
      { moveX: -1 },
    ]) {
      const state = spawnPlayer();
      run(state, input(dir), 600);
      expect(Math.abs(state.position.x)).toBeLessThan(8.25);
      expect(Math.abs(state.position.z)).toBeLessThan(6.25);
    }
  });

  it('is deterministic: identical inputs produce identical state', () => {
    const frames = Array.from({ length: 300 }, (_, i) =>
      input({ moveZ: 1, moveX: i % 7 === 0 ? 1 : 0, lookDx: (i % 13) - 6, jump: i % 45 === 0 }),
    );

    const runAll = () => {
      const state = spawnPlayer();
      for (const frame of frames) stepPlayer(state, frame, colliders, SIM_DT, PLAYER_CONFIG);
      return state;
    };

    expect(runAll()).toEqual(runAll());
  });
});

describe('world', () => {
  it('derives the same level rng from the same worldSeed and depth', () => {
    const make = () =>
      new World({ level: TEST_CHAMBER, playerConfig: PLAYER_CONFIG, worldSeed: 4242, depth: 3 });
    expect(make().rng.next()).toBe(make().rng.next());
  });

  it('derives a different rng at a different depth', () => {
    const shallow = new World({ level: TEST_CHAMBER, playerConfig: PLAYER_CONFIG, worldSeed: 4242, depth: 1 });
    const deep = new World({ level: TEST_CHAMBER, playerConfig: PLAYER_CONFIG, worldSeed: 4242, depth: 2 });
    expect(shallow.rng.next()).not.toBe(deep.rng.next());
  });

  it('steps the player and keeps its transform in sync', () => {
    const world = new World({ level: TEST_CHAMBER, playerConfig: PLAYER_CONFIG, worldSeed: 1, depth: 0 });
    for (let i = 0; i < 60; i += 1) world.step(input({ moveZ: 1 }), SIM_DT);
    expect(world.tick).toBe(60);
    expect(world.player.transform!.position).toEqual(world.playerState.position);
    expect(world.query('player')).toHaveLength(1);
  });
});
