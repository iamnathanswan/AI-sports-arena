/**
 * Debug overlay: FPS, player position, seed and pointer-lock hint.
 * Plain DOM — no framework, and no reads back into the simulation.
 */

export interface HudData {
  fps: number;
  x: number;
  y: number;
  z: number;
  yaw: number;
  grounded: boolean;
  seed: number;
  tick: number;
  pointerLocked: boolean;
}

const STYLE = `
.hud {
  position: absolute; top: 12px; left: 12px;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #cfe3ff; background: rgba(6, 8, 14, 0.62);
  border: 1px solid rgba(120, 160, 220, 0.25); border-radius: 6px;
  padding: 8px 10px; pointer-events: none; white-space: pre; min-width: 190px;
}
.hud b { color: #ffce8a; font-weight: 600; }
.hint {
  position: absolute; inset: 0; display: grid; place-items: center;
  font: 500 15px/1.6 system-ui, sans-serif; color: #dce7ff;
  background: rgba(4, 6, 12, 0.55); text-align: center; pointer-events: none;
}
.hint span { background: rgba(10, 14, 24, 0.85); padding: 14px 20px; border-radius: 8px;
  border: 1px solid rgba(120, 160, 220, 0.25); }
`;

export class DebugHud {
  private readonly panel: HTMLDivElement;
  private readonly hint: HTMLDivElement;

  constructor(container: HTMLElement) {
    const style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);

    this.panel = document.createElement('div');
    this.panel.className = 'hud';
    container.appendChild(this.panel);

    this.hint = document.createElement('div');
    this.hint.className = 'hint';
    this.hint.innerHTML =
      '<span>Click to look around<br>WASD move &middot; Shift sprint &middot; Space jump &middot; Esc release</span>';
    container.appendChild(this.hint);
  }

  update(data: HudData): void {
    const yawDegrees = ((data.yaw * 180) / Math.PI).toFixed(0).padStart(3, ' ');
    this.panel.innerHTML =
      `<b>fps</b>   ${data.fps.toFixed(0).padStart(3, ' ')}\n` +
      `<b>pos</b>   ${fmt(data.x)} ${fmt(data.y)} ${fmt(data.z)}\n` +
      `<b>yaw</b>   ${yawDegrees}&deg;  ${data.grounded ? 'grounded' : 'airborne'}\n` +
      `<b>seed</b>  ${data.seed}\n` +
      `<b>tick</b>  ${data.tick}`;
    this.hint.style.display = data.pointerLocked ? 'none' : 'grid';
  }
}

const fmt = (value: number): string => value.toFixed(2).padStart(7, ' ');

/** Rolling FPS estimate, smoothed so the number is readable. */
export class FpsMeter {
  private smoothed = 60;

  sample(deltaSeconds: number): number {
    if (deltaSeconds > 0) {
      const instant = 1 / deltaSeconds;
      this.smoothed += (instant - this.smoothed) * 0.08;
    }
    return this.smoothed;
  }
}
