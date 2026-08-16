import type { PlayerConfigDef } from './types.js';

/** Baseline player tuning. Units are metres and seconds. */
export const PLAYER_CONFIG: PlayerConfigDef = {
  radius: 0.35,
  height: 1.8,
  eyeHeight: 1.62,
  walkSpeed: 4.4,
  sprintMultiplier: 1.65,
  groundAcceleration: 60,
  airAcceleration: 12,
  groundFriction: 42,
  jumpSpeed: 5.2,
  gravity: 22,
  maxFallSpeed: 40,
  lookSensitivity: 0.0022,
  maxPitch: Math.PI / 2 - 0.02,
  headBobAmplitude: 0.035,
  headBobFrequency: 9.5,
};
