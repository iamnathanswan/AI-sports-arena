/**
 * First-person movement. Pure logic: given a player component, an input frame
 * and the level's colliders, produce the next state. No three.js, no DOM.
 */

import type { PlayerConfigDef } from '../content/types.js';
import type { Aabb, BodyShape } from './collision.js';
import { isSupported, moveWithCollisions } from './collision.js';
import type { InputFrame } from './input.js';
import { clamp, vec3, type Vec3 } from './math.js';

export interface PlayerState {
  position: Vec3;
  velocity: Vec3;
  yaw: number;
  pitch: number;
  grounded: boolean;
  /** Accumulated distance walked on the ground, drives head bob. */
  bobPhase: number;
}

export const createPlayerState = (spawn: Vec3, yaw: number): PlayerState => ({
  position: { x: spawn.x, y: spawn.y, z: spawn.z },
  velocity: vec3(),
  yaw,
  pitch: 0,
  grounded: false,
  bobPhase: 0,
});

export const bodyShapeFor = (config: PlayerConfigDef): BodyShape => ({
  radius: config.radius,
  height: config.height,
});

/** Applies pointer deltas to yaw/pitch, clamping pitch to avoid flipping over. */
export function applyLook(state: PlayerState, input: InputFrame, config: PlayerConfigDef): void {
  state.yaw -= input.lookDx * config.lookSensitivity;
  state.pitch = clamp(
    state.pitch - input.lookDy * config.lookSensitivity,
    -config.maxPitch,
    config.maxPitch,
  );

  const twoPi = Math.PI * 2;
  state.yaw = ((state.yaw % twoPi) + twoPi) % twoPi;
}

/** Unit-length world-space direction the player wants to move, from yaw + input. */
export function wishDirection(state: PlayerState, input: InputFrame): Vec3 {
  const magnitude = Math.hypot(input.moveX, input.moveZ);
  if (magnitude === 0) return vec3();

  const x = input.moveX / magnitude;
  const z = input.moveZ / magnitude;
  const sin = Math.sin(state.yaw);
  const cos = Math.cos(state.yaw);

  // Yaw 0 looks down -Z; +X is the player's right.
  return {
    x: x * cos - z * sin,
    y: 0,
    z: -x * sin - z * cos,
  };
}

/**
 * Advances the player by exactly one fixed simulation step. `state` is
 * mutated in place — the caller owns snapshotting for render interpolation.
 */
export function stepPlayer(
  state: PlayerState,
  input: InputFrame,
  colliders: readonly Aabb[],
  dt: number,
  config: PlayerConfigDef,
): void {
  applyLook(state, input, config);

  const wish = wishDirection(state, input);
  const targetSpeed = config.walkSpeed * (input.sprint ? config.sprintMultiplier : 1);
  const acceleration = state.grounded ? config.groundAcceleration : config.airAcceleration;

  if (wish.x !== 0 || wish.z !== 0) {
    state.velocity.x += wish.x * acceleration * dt;
    state.velocity.z += wish.z * acceleration * dt;

    const speed = Math.hypot(state.velocity.x, state.velocity.z);
    if (speed > targetSpeed) {
      const scale = targetSpeed / speed;
      state.velocity.x *= scale;
      state.velocity.z *= scale;
    }
  } else if (state.grounded) {
    const speed = Math.hypot(state.velocity.x, state.velocity.z);
    const drop = config.groundFriction * dt;
    if (speed <= drop) {
      state.velocity.x = 0;
      state.velocity.z = 0;
    } else {
      const scale = (speed - drop) / speed;
      state.velocity.x *= scale;
      state.velocity.z *= scale;
    }
  }

  if (input.jump && state.grounded) {
    state.velocity.y = config.jumpSpeed;
    state.grounded = false;
  }

  state.velocity.y = Math.max(state.velocity.y - config.gravity * dt, -config.maxFallSpeed);

  const shape = bodyShapeFor(config);
  const result = moveWithCollisions(
    state.position,
    { x: state.velocity.x * dt, y: state.velocity.y * dt, z: state.velocity.z * dt },
    shape,
    colliders,
  );

  state.position = result.position;

  // Kill velocity into a wall so we do not burst sideways when we clear it;
  // sliding still works because each axis was swept independently.
  if (result.blockedX) state.velocity.x = 0;
  if (result.blockedZ) state.velocity.z = 0;

  if (result.grounded) {
    state.velocity.y = 0;
    state.grounded = true;
  } else if (result.hitCeiling) {
    state.velocity.y = 0;
    state.grounded = false;
  } else {
    state.grounded = isSupported(state.position, shape, colliders);
  }

  const horizontalSpeed = Math.hypot(state.velocity.x, state.velocity.z);
  state.bobPhase = state.grounded ? state.bobPhase + horizontalSpeed * dt : state.bobPhase;
}
