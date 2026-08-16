/**
 * three.js setup: renderer, scene, camera and resize handling. Knows nothing
 * about gameplay — it is handed a scene graph and asked to draw it.
 */

import * as THREE from 'three';

export interface RendererBundle {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  canvas: HTMLCanvasElement;
  render(): void;
  dispose(): void;
}

export function createRenderer(container: HTMLElement, backgroundColor: number, fogDensity: number): RendererBundle {
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  container.appendChild(canvas);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(backgroundColor);
  scene.fog = new THREE.FogExp2(backgroundColor, fogDensity);

  const camera = new THREE.PerspectiveCamera(
    78,
    container.clientWidth / container.clientHeight,
    0.05,
    250,
  );

  const onResize = () => {
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  window.addEventListener('resize', onResize);

  return {
    renderer,
    scene,
    camera,
    canvas,
    render: () => renderer.render(scene, camera),
    dispose: () => {
      window.removeEventListener('resize', onResize);
      renderer.dispose();
      canvas.remove();
    },
  };
}
