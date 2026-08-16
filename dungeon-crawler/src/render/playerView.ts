/**
 * Drives the camera from interpolated simulation state and carries the
 * player's torch. Rendering never writes back into the simulation.
 */

import * as THREE from 'three';
import type { LightDef, PlayerConfigDef } from '../content/types.js';
import { lerp, lerpAngle } from '../sim/math.js';
import type { PlayerState } from '../sim/player.js';

/** The subset of player state rendering cares about, captured per sim step. */
export interface PlayerSnapshot {
  x: number;
  y: number;
  z: number;
  yaw: number;
  pitch: number;
  bobPhase: number;
}

export const snapshotPlayer = (state: PlayerState): PlayerSnapshot => ({
  x: state.position.x,
  y: state.position.y,
  z: state.position.z,
  yaw: state.yaw,
  pitch: state.pitch,
  bobPhase: state.bobPhase,
});

export class PlayerView {
  readonly torch: THREE.PointLight;
  private readonly torchIntensity: number;

  constructor(
    private readonly camera: THREE.PerspectiveCamera,
    private readonly config: PlayerConfigDef,
    torchDef: LightDef,
  ) {
    this.torch = new THREE.PointLight(
      torchDef.color,
      torchDef.intensity,
      torchDef.distance ?? 0,
      torchDef.decay ?? 2,
    );
    this.torch.name = torchDef.id;
    this.torchIntensity = torchDef.intensity;
    // Slightly ahead of and below the eye, so walls light up before the floor.
    this.torch.position.set(0, -0.15, -0.25);
    this.camera.add(this.torch);
  }

  /** Places the camera between two sim states. `alpha` is 0..1. */
  update(previous: PlayerSnapshot, current: PlayerSnapshot, alpha: number, elapsed: number): void {
    const x = lerp(previous.x, current.x, alpha);
    const y = lerp(previous.y, current.y, alpha);
    const z = lerp(previous.z, current.z, alpha);
    const yaw = lerpAngle(previous.yaw, current.yaw, alpha);
    const pitch = lerp(previous.pitch, current.pitch, alpha);
    const bobPhase = lerp(previous.bobPhase, current.bobPhase, alpha);

    const bob = Math.sin(bobPhase * this.config.headBobFrequency) * this.config.headBobAmplitude;

    this.camera.position.set(x, y + this.config.eyeHeight + bob, z);
    this.camera.rotation.set(pitch, yaw, 0, 'YXZ');

    // Cheap torch flicker: two out-of-phase sines, no RNG involved.
    const flicker = 1 + Math.sin(elapsed * 11.3) * 0.05 + Math.sin(elapsed * 27.7) * 0.03;
    this.torch.intensity = this.torchIntensity * flicker;
  }
}
