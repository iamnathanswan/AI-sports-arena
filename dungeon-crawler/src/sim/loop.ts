/**
 * Fixed-timestep accumulator. The simulation always advances in identical
 * 1/60 s steps regardless of display refresh rate; rendering interpolates
 * between the last two states using the leftover alpha.
 */

export const SIM_HZ = 60;
export const SIM_DT = 1 / SIM_HZ;

/** Never simulate more than this many steps for one frame (spiral-of-death guard). */
const MAX_STEPS_PER_FRAME = 5;

export interface LoopStats {
  /** Steps run during the most recent advance() call. */
  steps: number;
  /** Fraction of a step left over, for render interpolation (0..1). */
  alpha: number;
  /** True when time had to be discarded to keep up. */
  clamped: boolean;
}

export class FixedTimestep {
  private accumulator = 0;

  constructor(
    private readonly step: (dt: number, stepIndex: number) => void,
    private readonly dt: number = SIM_DT,
  ) {}

  /** Feeds real elapsed seconds in; runs zero or more fixed steps. */
  advance(elapsedSeconds: number): LoopStats {
    // Guard against tab-switch spikes handing us multi-second frames.
    this.accumulator += Math.min(elapsedSeconds, this.dt * MAX_STEPS_PER_FRAME * 2);

    let steps = 0;
    while (this.accumulator >= this.dt && steps < MAX_STEPS_PER_FRAME) {
      this.step(this.dt, steps);
      this.accumulator -= this.dt;
      steps += 1;
    }

    const clamped = this.accumulator >= this.dt;
    if (clamped) this.accumulator = 0;

    return { steps, alpha: this.accumulator / this.dt, clamped };
  }

  reset(): void {
    this.accumulator = 0;
  }
}
