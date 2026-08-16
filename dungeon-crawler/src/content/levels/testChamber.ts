import type { LevelDef } from '../types.js';

const box = (
  id: string,
  center: [number, number, number],
  size: [number, number, number],
  material: string,
  solid = true,
) => ({
  id,
  center: { x: center[0], y: center[1], z: center[2] },
  size: { x: size[0], y: size[1], z: size[2] },
  material,
  solid,
});

/**
 * Hand-authored proving ground for the first-person controller.
 * Interior is 16 x 12 metres and 4 metres tall, centred on the origin.
 */
export const TEST_CHAMBER: LevelDef = {
  id: 'test_chamber',
  name: 'Test Chamber',
  backgroundColor: 0x07070a,
  fogDensity: 0.035,
  materials: [
    { id: 'floor', color: 0x3a352f, roughness: 0.95, metalness: 0.0 },
    { id: 'wall', color: 0x4a443c, roughness: 0.9, metalness: 0.0 },
    { id: 'ceiling', color: 0x241f1b, roughness: 1.0, metalness: 0.0 },
    { id: 'pillar', color: 0x5b5245, roughness: 0.8, metalness: 0.05 },
    { id: 'crate', color: 0x6b4f2a, roughness: 0.85, metalness: 0.0 },
    {
      id: 'brazier',
      color: 0x2a1b12,
      roughness: 0.6,
      metalness: 0.2,
      emissive: 0xff7a2a,
      emissiveIntensity: 2.2,
    },
  ],
  brushes: [
    box('floor', [0, -0.25, 0], [17, 0.5, 13], 'floor'),
    box('ceiling', [0, 4.25, 0], [17, 0.5, 13], 'ceiling'),
    box('wall_north', [0, 2, -6.25], [17, 4.5, 0.5], 'wall'),
    box('wall_south', [0, 2, 6.25], [17, 4.5, 0.5], 'wall'),
    box('wall_west', [-8.25, 2, 0], [0.5, 4.5, 13], 'wall'),
    box('wall_east', [8.25, 2, 0], [0.5, 4.5, 13], 'wall'),

    box('pillar_nw', [-4, 2, -3], [0.9, 4, 0.9], 'pillar'),
    box('pillar_ne', [4, 2, -3], [0.9, 4, 0.9], 'pillar'),
    box('pillar_sw', [-4, 2, 3], [0.9, 4, 0.9], 'pillar'),
    box('pillar_se', [4, 2, 3], [0.9, 4, 0.9], 'pillar'),

    // Low platform to prove jumping and ground detection.
    box('plinth', [0, 0.3, -4.4], [3, 0.6, 1.4], 'crate'),
    box('crate', [6.4, 0.5, -4.6], [1, 1, 1], 'crate'),

    // Glowing brazier stub, paired with the point light below.
    box('brazier_stand', [-6.6, 0.55, 4.6], [0.7, 1.1, 0.7], 'brazier'),
  ],
  lights: [
    { id: 'ambient', kind: 'ambient', color: 0x2c3040, intensity: 1.2 },
    {
      id: 'brazier_light',
      kind: 'point',
      color: 0xff8a3d,
      intensity: 260,
      position: { x: -6.6, y: 1.4, z: 4.6 },
      distance: 14,
      decay: 2,
    },
  ],
  playerSpawn: { x: 0, y: 0, z: 4 },
  // Yaw 0 looks down -Z, i.e. into the room rather than at the wall behind.
  playerSpawnYaw: 0,
};
