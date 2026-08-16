/**
 * The simulation's view of player intent. The browser input layer produces
 * these; tests produce them by hand. Nothing here touches the DOM.
 */

export interface InputFrame {
  /** -1 (left) .. 1 (right) strafe intent. */
  moveX: number;
  /** -1 (backward) .. 1 (forward) intent. */
  moveZ: number;
  /** Raw pointer delta accumulated since the previous tick, in pixels. */
  lookDx: number;
  lookDy: number;
  jump: boolean;
  sprint: boolean;
}

export const emptyInput = (): InputFrame => ({
  moveX: 0,
  moveZ: 0,
  lookDx: 0,
  lookDy: 0,
  jump: false,
  sprint: false,
});
