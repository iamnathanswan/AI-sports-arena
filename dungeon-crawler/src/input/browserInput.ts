/**
 * Browser input -> InputFrame. This is the only place that knows about
 * keyboards, mice and pointer lock; the simulation just sees numbers.
 */

import type { InputFrame } from '../sim/input.js';

const KEY_BINDINGS: Record<string, keyof HeldKeys> = {
  KeyW: 'forward',
  ArrowUp: 'forward',
  KeyS: 'back',
  ArrowDown: 'back',
  KeyA: 'left',
  ArrowLeft: 'left',
  KeyD: 'right',
  ArrowRight: 'right',
  Space: 'jump',
  ShiftLeft: 'sprint',
  ShiftRight: 'sprint',
};

interface HeldKeys {
  forward: boolean;
  back: boolean;
  left: boolean;
  right: boolean;
  jump: boolean;
  sprint: boolean;
}

export class BrowserInput {
  private readonly held: HeldKeys = {
    forward: false,
    back: false,
    left: false,
    right: false,
    jump: false,
    sprint: false,
  };

  private lookDx = 0;
  private lookDy = 0;
  private locked = false;

  private readonly listeners: Array<() => void> = [];

  constructor(private readonly canvas: HTMLElement) {}

  /** True while the pointer is locked to the canvas. */
  get pointerLocked(): boolean {
    return this.locked;
  }

  attach(): void {
    const onKeyDown = (event: KeyboardEvent) => {
      const binding = KEY_BINDINGS[event.code];
      if (!binding) return;
      this.held[binding] = true;
      if (this.locked) event.preventDefault();
    };

    const onKeyUp = (event: KeyboardEvent) => {
      const binding = KEY_BINDINGS[event.code];
      if (!binding) return;
      this.held[binding] = false;
    };

    const onMouseMove = (event: MouseEvent) => {
      if (!this.locked) return;
      this.lookDx += event.movementX;
      this.lookDy += event.movementY;
    };

    const onClick = () => {
      if (!this.locked) void this.canvas.requestPointerLock();
    };

    const onLockChange = () => {
      this.locked = document.pointerLockElement === this.canvas;
      if (!this.locked) this.releaseAll();
    };

    const onBlur = () => this.releaseAll();

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', onBlur);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('pointerlockchange', onLockChange);
    this.canvas.addEventListener('click', onClick);

    this.listeners.push(
      () => window.removeEventListener('keydown', onKeyDown),
      () => window.removeEventListener('keyup', onKeyUp),
      () => window.removeEventListener('blur', onBlur),
      () => document.removeEventListener('mousemove', onMouseMove),
      () => document.removeEventListener('pointerlockchange', onLockChange),
      () => this.canvas.removeEventListener('click', onClick),
    );
  }

  detach(): void {
    for (const remove of this.listeners.splice(0)) remove();
  }

  /**
   * Snapshot for one simulation step. Held keys persist; accumulated pointer
   * movement is drained, so running several steps in one frame never applies
   * the same mouse delta twice.
   */
  consume(): InputFrame {
    const frame: InputFrame = {
      moveX: (this.held.right ? 1 : 0) - (this.held.left ? 1 : 0),
      moveZ: (this.held.forward ? 1 : 0) - (this.held.back ? 1 : 0),
      lookDx: this.lookDx,
      lookDy: this.lookDy,
      jump: this.held.jump,
      sprint: this.held.sprint,
    };
    this.lookDx = 0;
    this.lookDy = 0;
    return frame;
  }

  private releaseAll(): void {
    for (const key of Object.keys(this.held) as Array<keyof HeldKeys>) {
      this.held[key] = false;
    }
    this.lookDx = 0;
    this.lookDy = 0;
  }
}
