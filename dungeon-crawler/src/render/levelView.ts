/**
 * Builds the three.js representation of a level purely from its content data.
 * Adding a room, material or light means editing data — never this file.
 */

import * as THREE from 'three';
import type { LevelDef, MaterialDef } from '../content/types.js';

export interface LevelView {
  group: THREE.Group;
  dispose(): void;
}

function makeMaterial(def: MaterialDef): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({
    color: def.color,
    roughness: def.roughness ?? 0.9,
    metalness: def.metalness ?? 0.0,
  });
  if (def.emissive !== undefined) {
    material.emissive = new THREE.Color(def.emissive);
    material.emissiveIntensity = def.emissiveIntensity ?? 1;
  }
  return material;
}

export function buildLevelView(level: LevelDef): LevelView {
  const group = new THREE.Group();
  group.name = `level:${level.id}`;

  const materials = new Map<string, THREE.MeshStandardMaterial>();
  for (const def of level.materials) {
    materials.set(def.id, makeMaterial(def));
  }

  const unitBox = new THREE.BoxGeometry(1, 1, 1);

  for (const brush of level.brushes) {
    const material = materials.get(brush.material);
    if (!material) throw new Error(`Level ${level.id}: unknown material '${brush.material}'`);

    const mesh = new THREE.Mesh(unitBox, material);
    mesh.name = brush.id;
    mesh.position.set(brush.center.x, brush.center.y, brush.center.z);
    mesh.scale.set(brush.size.x, brush.size.y, brush.size.z);
    mesh.castShadow = false;
    mesh.receiveShadow = false;
    group.add(mesh);
  }

  for (const light of level.lights) {
    if (light.kind === 'ambient') {
      group.add(new THREE.AmbientLight(light.color, light.intensity));
      continue;
    }
    const point = new THREE.PointLight(light.color, light.intensity, light.distance ?? 0, light.decay ?? 2);
    if (light.position) point.position.set(light.position.x, light.position.y, light.position.z);
    point.name = light.id;
    group.add(point);
  }

  return {
    group,
    dispose: () => {
      unitBox.dispose();
      for (const material of materials.values()) material.dispose();
      group.clear();
    },
  };
}
