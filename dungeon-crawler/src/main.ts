/**
 * Entry point: wires the headless simulation to the three.js renderer.
 * The frame loop steps the sim at a fixed 60 Hz and renders interpolated.
 */

import { getLevel, PLAYER_CONFIG, PLAYER_TORCH } from './content/index.js';
import { BrowserInput } from './input/browserInput.js';
import { FixedTimestep } from './sim/loop.js';
import { hashSeed } from './sim/rng.js';
import { World } from './sim/world.js';
import { buildLevelView } from './render/levelView.js';
import { PlayerView, snapshotPlayer, type PlayerSnapshot } from './render/playerView.js';
import { createRenderer } from './render/renderer.js';
import { DebugHud, FpsMeter } from './ui/debugHud.js';

/** Seed comes from ?seed=..., otherwise a fixed default so runs are repeatable. */
function resolveWorldSeed(): number {
  const raw = new URLSearchParams(window.location.search).get('seed');
  if (raw === null) return hashSeed('default-world');
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric >>> 0 : hashSeed(raw);
}

function start(): void {
  const container = document.getElementById('app');
  if (!container) throw new Error('#app container missing');

  const level = getLevel('test_chamber');
  const worldSeed = resolveWorldSeed();
  const world = new World({ level, playerConfig: PLAYER_CONFIG, worldSeed, depth: 0 });

  const { scene, camera, canvas, render } = createRenderer(
    container,
    level.backgroundColor,
    level.fogDensity,
  );
  scene.add(buildLevelView(level).group);
  // The camera joins the graph so its child torch light is rendered.
  scene.add(camera);

  const playerView = new PlayerView(camera, PLAYER_CONFIG, PLAYER_TORCH);
  const input = new BrowserInput(canvas);
  input.attach();

  const hud = new DebugHud(container);
  const fpsMeter = new FpsMeter();

  let previous: PlayerSnapshot = snapshotPlayer(world.playerState);
  let current: PlayerSnapshot = previous;

  const loop = new FixedTimestep((dt) => {
    previous = current;
    world.step(input.consume(), dt);
    current = snapshotPlayer(world.playerState);
  });

  let lastTime = performance.now();

  const frame = (now: number) => {
    const elapsedSeconds = (now - lastTime) / 1000;
    lastTime = now;

    const { alpha } = loop.advance(elapsedSeconds);
    playerView.update(previous, current, alpha, now / 1000);
    render();

    hud.update({
      fps: fpsMeter.sample(elapsedSeconds),
      x: current.x,
      y: current.y,
      z: current.z,
      yaw: current.yaw,
      grounded: world.playerState.grounded,
      seed: worldSeed,
      tick: world.tick,
      pointerLocked: input.pointerLocked,
    });

    requestAnimationFrame(frame);
  };

  requestAnimationFrame(frame);
}

start();
