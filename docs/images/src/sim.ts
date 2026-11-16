// One large, open room and one unit under two controls. Schematic: one step is a minute, nothing is measured.
// A is the air at the sofa, M the furniture and walls; both charts use the same room physics.
import { DEFAULTS } from "./defaults.ts";

export type Run = { room: [number, number][]; on: [number, number][] };
export const P = { h: 0.06, kAM: 0.008, kMA: 0.005, loss: 0.0003, out: 8 };
const TARGET = 21;
type S = { A: number; M: number };

function step(s: S, f: number) {
  const { A, M } = s;
  s.A = A + P.h * f - P.kAM * (A - M) - P.loss * (A - P.out);
  s.M = M + P.kMA * (A - M);
}

// The unit on its own regulates on its own reading in the warm air at its housing. It throttles early
// and switches ever faster between heating and idle. The switching pattern is given (as observed),
// the room temperature follows from it.
export function onItsOwn(n: number): Run {
  const s = { A: 19, M: 18.2 }, room: [number, number][] = [], on: [number, number][] = [];
  let i = 0;
  for (let k = 0; i <= n; k++) {
    const r = Math.max(6, Math.round(80 * 0.72 ** k)), p = Math.max(5, Math.round(15 * 0.85 ** k)), f = Math.max(0.25, 0.4 * 0.9 ** k);
    on.push([i, Math.min(n, i + r)]);
    for (let j = 0; j < r && i <= n; j++, i++) { step(s, f); room.push([i, s.A]); }
    for (let j = 0; j < p && i <= n; j++, i++) { step(s, 0); room.push([i, s.A]); }
  }
  return { room, on };
}

// With SteadyRoom the sensor at the sofa decides, with the default band around the target. Far from the
// target the offset asks for much power, near it for little, but never so little that the unit falls idle.
export function withSteadyRoom(n: number): Run {
  const s = { A: 19, M: 18.2 }, room: [number, number][] = [], on: [number, number][] = [];
  const stop = TARGET + DEFAULTS.heatStop, start = TARGET - DEFAULTS.heatStart;
  let running = true, t0 = 0;
  for (let i = 0; i <= n; i++) {
    if (running && s.A >= stop) { on.push([t0, i]); running = false; }
    else if (!running && s.A <= start) { running = true; t0 = i; }
    step(s, running ? Math.min(1, Math.max(0.4, (stop - s.A) / 1.2)) : 0); room.push([i, s.A]);
  }
  if (running) on.push([t0, n]);
  return { room, on };
}
