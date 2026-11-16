// The defaults of the integration, read from its source, and the offset formula of logic.py.
// A changed default therefore shows up in the graphics with the next run.
import { REPO } from "./lib.ts";

const source = (file: string) => Bun.file(`${REPO}/custom_components/steadyroom/${file}`).text();
const logic = await source("logic.py");
const consts = await source("const.py");

function read(text: string, pattern: RegExp, what: string): number {
  const match = text.match(pattern);
  if (!match) throw new Error(`default not found: ${what}`);
  return Number(match[1]);
}
const parameter = (name: string) =>
  read(logic, new RegExp(`^ {4}${name}: float = ([0-9.]+)`, "m"), `logic.Parameters.${name}`);

export const DEFAULTS = {
  heatStart: parameter("heat_start"),
  heatStop: parameter("heat_stop"),
  coolStart: parameter("cool_start"),
  coolStop: parameter("cool_stop"),
  autoStart: parameter("auto_start"),
  autoStop: parameter("auto_stop"),
  minOffset: parameter("min_offset"),
  knee: parameter("knee"),
  factor: parameter("factor"),
  step: read(consts, /^DEFAULT_STEP: Final = ([0-9.]+)/m, "const.DEFAULT_STEP"),
  presetDistance: read(consts, /^ {4}KEY_PRESET_DISTANCE: ([0-9.]+),/m, "const.EXTRA_DEFAULTS, preset distance"),
};

const EPSILON = 1e-6; // as in logic.py

/** The distance to the target after the quadratic growth beyond the knee. */
export const grown = (distance: number, factor = DEFAULTS.factor) =>
  distance <= DEFAULTS.knee ? distance : distance + factor * (distance - DEFAULTS.knee) ** 2;

/** What logic.offset() returns for a distance, with the default knee and step. */
export const offset = (distance: number, minimum = DEFAULTS.minOffset, factor = DEFAULTS.factor) =>
  Math.max(minimum, Math.ceil(grown(distance, factor) / DEFAULTS.step - EPSILON) * DEFAULTS.step);
