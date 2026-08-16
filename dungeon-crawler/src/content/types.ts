/**
 * Content interfaces.
 *
 * Project rule: every new kind of content gets its interface here first, then
 * a data file under `src/content/`, then the system that consumes it. Systems
 * code must never need editing to add a new room, material or level.
 */

export interface Vec3Data {
  x: number;
  y: number;
  z: number;
}

/** Flat-colour placeholder material. No textures until the art pass (M6). */
export interface MaterialDef {
  id: string;
  /** Hex colour, e.g. 0x6b6257. */
  color: number;
  /** 0 = matte, 1 = mirror. */
  roughness?: number;
  metalness?: number;
  /** Self-illumination colour for things that should glow. */
  emissive?: number;
  emissiveIntensity?: number;
}

/**
 * A solid box of level geometry. `center` is the middle of the box in world
 * space; `size` is its full extent on each axis.
 */
export interface BrushDef {
  id: string;
  center: Vec3Data;
  size: Vec3Data;
  material: string;
  /** Solid brushes block movement. Decorative ones are rendered only. */
  solid?: boolean;
}

export type LightKind = 'ambient' | 'point';

export interface LightDef {
  id: string;
  kind: LightKind;
  color: number;
  intensity: number;
  /** Point lights only. */
  position?: Vec3Data;
  distance?: number;
  decay?: number;
}

/** The player's physical and control tuning, kept as data rather than constants. */
export interface PlayerConfigDef {
  radius: number;
  height: number;
  eyeHeight: number;
  walkSpeed: number;
  sprintMultiplier: number;
  groundAcceleration: number;
  airAcceleration: number;
  groundFriction: number;
  jumpSpeed: number;
  gravity: number;
  /** Terminal downward speed, so long falls stay predictable. */
  maxFallSpeed: number;
  /** Radians of yaw per pixel of mouse movement. */
  lookSensitivity: number;
  /** Maximum absolute pitch in radians. */
  maxPitch: number;
  /** Bob amplitude and frequency for the head/torch, purely cosmetic. */
  headBobAmplitude: number;
  headBobFrequency: number;
}

/** A hand-authored or generated playable space. */
export interface LevelDef {
  id: string;
  name: string;
  /** Sky/fog colour behind everything. */
  backgroundColor: number;
  fogDensity: number;
  materials: MaterialDef[];
  brushes: BrushDef[];
  lights: LightDef[];
  playerSpawn: Vec3Data;
  /** Yaw the player faces on spawn, in radians. */
  playerSpawnYaw: number;
}
