// Shared pieces of the README graphics: paths, palette, and SVG to PNG at double resolution.
import { Resvg } from "@resvg/resvg-js";

export const IMAGES = `${import.meta.dir}/..`;
export const REPO = `${import.meta.dir}/../../..`;
export const FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif";

// One meaning per colour in every graphic: orange is the unit and heating,
// blue the room sensor and cooling, pink SteadyRoom.
export const ORANGE = "#F97316", PINK = "#E5488A", BLUE = "#3B82F6";
export const INK = "#1E293B", MUTED = "#64748B", LINE = "#E2E8F0", GRID = "#EEF2F6", AXIS = "#94A3B8";

export const path = (points: [number, number][]) =>
  points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");

/** Render an SVG body to docs/images/<name>.png. */
export async function render(name: string, width: number, height: number, body: string): Promise<void> {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="${FONT}">${body}</svg>`;
  const png = new Resvg(svg, { fitTo: { mode: "zoom", value: 2 }, font: { loadSystemFonts: true, defaultFontFamily: "Helvetica Neue" } }).render().asPng();
  await Bun.write(`${IMAGES}/${name}.png`, png);
  console.log(`${name}.png`);
}
