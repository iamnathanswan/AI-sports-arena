# Dungeon Crawler

A first-person, real-time dungeon crawler: procedurally generated depth, randomized
loot, a town hub and a pet companion — played from inside the dungeon rather than
above it. TypeScript + three.js, entirely client-side.

**Status: Milestone 0** — you can walk around one hand-authored room.

## Running it

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # headless logic tests
npm run build      # typecheck + production bundle
```

Controls: click to capture the mouse, **WASD** to move, **Shift** to sprint,
**Space** to jump, **Esc** to release the pointer.

Append `?seed=anything` to the URL to change the world seed. The seed is shown
in the debug HUD alongside FPS, position and tick count.

## Architecture

The one rule everything else follows: **simulation never imports three.js.**

```
src/
  content/          Data, not code. Interfaces first, then the data files.
    types.ts        Every content interface lives here before anything consumes it
    player.ts       Player physics tuning as data
    levels/         Hand-authored levels (generated ones arrive in M1)
    index.ts        Content registry
  sim/              Headless simulation — no three.js, no DOM, no Math.random()
    rng.ts          Seeded PRNG; one stream per level from worldSeed + depth
    math.ts         Plain-object vector math
    collision.ts    AABB sweep with sub-stepping, pure functions
    player.ts       First-person movement: look, accelerate, gravity, jump
    level.ts        Level data -> collision boxes
    world.ts        Component-bag entity store + fixed step
    loop.ts         Fixed-timestep accumulator (60 Hz) with render alpha
    input.ts        InputFrame: the sim's view of player intent
  input/            Browser keyboard/pointer-lock -> InputFrame
  render/           three.js: renderer, level meshes from data, camera + torch
  ui/               Debug HUD
tests/              Vitest, headless
```

### Why these constraints

- **Sim/render split.** Combat math, loot rolls and generation stay testable
  without a browser. `tests/architecture.test.ts` fails the build if three.js,
  the DOM, or `Math.random` leak into `src/sim` or `src/content`.
- **Fixed 60 Hz timestep.** Physics behaves identically at 30 fps and 240 fps;
  rendering interpolates between the last two simulation states.
- **Seeded RNG everywhere.** One PRNG per level derived from
  `hashSeed(worldSeed, 'level', depth)`, so the same seed always rebuilds the
  same dungeon and the same drops. `rng.fork(label)` gives an independent
  substream without disturbing the parent.
- **Data-driven content.** Adding a room, material or light means editing
  `src/content/` — never `src/render/` or `src/sim/`.

## Milestone 0 scope

Deliberately not built yet: dungeon generation, combat, loot, monsters, town,
save/load. Nothing is stubbed for them.

Coordinate conventions worth knowing before more systems land:

- Y is up; one unit is one metre.
- A player position is at their **feet**; the camera sits at `eyeHeight` above it.
- Yaw 0 faces **-Z**; yaw increases counter-clockwise.
- Level brushes are axis-aligned boxes given as centre + full size.
