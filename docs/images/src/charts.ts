// Decision map and offset chart of the README, drawn from the integration's own defaults.
// Temperature runs up the vertical axis (cold below, warm above), the offset along the horizontal one.
// Start and stop settings use the darker shade of their direction; pink marks the near-target preset.
import { AXIS, BLUE, GRID, INK, LINE, MUTED, ORANGE, PINK, render } from "./lib.ts";
import { DEFAULTS as P, grown, offset } from "./defaults.ts";

const HEAT_SET = "#C2410C", COOL_SET = "#1D4ED8";
const ORANGE_LIGHT = "#FDBA74", ORANGE_DEEP = "#9A3412", PINK_BG = "#FCE7F3";
const fmt = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${-v}` : "0");

// Staircase along the y axis: x = f(y) for y from a to b.
function stairsY(f: (y: number) => number, a: number, b: number, X: (x: number) => number, Y: (y: number) => number) {
  let prev = f(a);
  const pts = [`M${X(prev).toFixed(1)} ${Y(a).toFixed(1)}`];
  for (let i = 1; i <= 3000; i++) {
    const y = a + ((b - a) * i) / 3000;
    const x = f(y);
    if (x !== prev) { pts.push(`L${X(prev).toFixed(1)} ${Y(y).toFixed(1)}`, `L${X(x).toFixed(1)} ${Y(y).toFixed(1)}`); prev = x; }
  }
  pts.push(`L${X(prev).toFixed(1)} ${Y(b).toFixed(1)}`);
  return pts.join(" ");
}
const smoothY = (f: (y: number) => number, a: number, b: number, X: (x: number) => number, Y: (y: number) => number) =>
  Array.from({ length: 401 }, (_, i) => { const y = a + ((b - a) * i) / 400; return `${i ? "L" : "M"}${X(f(y)).toFixed(1)} ${Y(y).toFixed(1)}`; }).join(" ");
const text = (x: number, y: number, s: string, color: string, o: { anchor?: string; size?: number; weight?: number } = {}) =>
  `<text x="${x}" y="${y}" font-size="${o.size ?? 20}" font-weight="${o.weight ?? 600}" fill="${color}" stroke="#FFFFFF" stroke-width="7" paint-order="stroke" text-anchor="${o.anchor ?? "start"}">${s}</text>`;
const sym = (x: number, y: number, kind: string, color: string) =>
  kind === "line" ? `<line x1="${x}" y1="${y - 6}" x2="${x + 34}" y2="${y - 6}" stroke="${color}" stroke-width="5"/>`
  : kind === "dash" ? `<line x1="${x}" y1="${y - 6}" x2="${x + 34}" y2="${y - 6}" stroke="${color}" stroke-width="5" stroke-dasharray="11 6"/>`
  : kind === "setting" ? `<line x1="${x}" y1="${y - 6}" x2="${x + 34}" y2="${y - 6}" stroke="${color}" stroke-width="2.5" stroke-dasharray="6 5"/>`
  : kind === "off" ? `<circle cx="${x + 17}" cy="${y - 6}" r="8" fill="#FFF" stroke="${color}" stroke-width="3"/>`
  : `<rect x="${x}" y="${y - 16}" width="34" height="20" rx="3" fill="${PINK_BG}" stroke="${PINK}" stroke-width="1.5"/>`;
const legend = (x0: number, y: number, items: [string, string, string, number][]) => {
  let x = x0;
  return items.map(([kind, color, label, w]) => { const s = `${sym(x, y, kind, color)}<text x="${x + 44}" y="${y}" font-size="18" fill="${INK}">${label}</text>`; x += w; return s; }).join("");
};

// Decision map: three columns that share the temperature axis.
{
  const W = 1280, X0 = 150, GAP = 56, K = (W - X0 - 40 - 2 * GAP) / 12;
  const YMIN = -1.5, YMAX = 1.5, TOP = 230, PH = 600;
  const Y = (y: number) => TOP + ((YMAX - y) / (YMAX - YMIN)) * PH;
  type Col = { left: number; xmin: number; xmax: number };
  // Order as on air conditioners: Cool, Auto, Heat.
  const coolCol: Col = { left: X0, xmin: -3, xmax: 0 };
  const autoCol: Col = { left: X0 + 3 * K + GAP, xmin: -3, xmax: 3 };
  const heatCol: Col = { left: X0 + 9 * K + 2 * GAP, xmin: 0, xmax: 3 };
  const Xc = (c: Col) => (x: number) => c.left + (x - c.xmin) * K;
  const right = (c: Col) => c.left + (c.xmax - c.xmin) * K;

  const frame = (c: Col, title: string, sub: string) => {
    const X = Xc(c);
    const ticks = Array.from({ length: c.xmax - c.xmin + 1 }, (_, i) => c.xmin + i);
    return `<text x="${c.left}" y="${TOP - 52}" font-size="28" font-weight="700" fill="${INK}">${title}</text>
      <text x="${c.left}" y="${TOP - 24}" font-size="16" fill="${MUTED}">${sub}</text>
      ${[-1.5, -1, -0.5, 0, 0.5, 1, 1.5].map((y) => `<line x1="${c.left}" y1="${Y(y)}" x2="${right(c)}" y2="${Y(y)}" stroke="${y === 0 ? AXIS : GRID}" stroke-width="${y === 0 ? 2 : 1.5}"/>`).join("")}
      ${ticks.map((x) => `<line x1="${X(x)}" y1="${Y(YMAX)}" x2="${X(x)}" y2="${Y(YMIN)}" stroke="${x === 0 ? AXIS : GRID}" stroke-width="${x === 0 ? 2 : 1.5}"/><text x="${X(x)}" y="${Y(YMIN) + 28}" font-size="18" fill="${MUTED}" text-anchor="middle">${fmt(x)}</text>`).join("")}`;
  };
  // A switching point: a line across the column and a short label on its free side.
  const mark = (c: Col, y: number, label: string, color: string, side: "left" | "right", pos: "above" | "below") => {
    const tx = side === "left" ? c.left + 6 : right(c) - 6;
    const ty = pos === "above" ? Y(y) - 9 : Y(y) + 24;
    return `<line x1="${c.left}" y1="${Y(y)}" x2="${right(c)}" y2="${Y(y)}" stroke="${color}" stroke-width="2.5" stroke-dasharray="6 5"/>${text(tx, ty, label, color, { anchor: side === "left" ? "start" : "end", size: 18 })}`;
  };
  const heat = (c: Col, stop: number) => { const X = Xc(c);
    return `<path d="${stairsY((y) => offset(-y), YMIN, stop, X, Y)}" fill="none" stroke="${ORANGE}" stroke-width="5" stroke-linejoin="round"/><circle cx="${X(offset(-stop))}" cy="${Y(stop)}" r="9" fill="#FFF" stroke="${ORANGE}" stroke-width="4"/>`; };
  const cool = (c: Col, stop: number) => { const X = Xc(c);
    return `<path d="${stairsY((y) => -offset(y), YMAX, stop, X, Y)}" fill="none" stroke="${BLUE}" stroke-width="5" stroke-linejoin="round"/><circle cx="${X(-offset(-stop))}" cy="${Y(stop)}" r="9" fill="#FFF" stroke="${BLUE}" stroke-width="4"/>`; };

  const yAxis = [-1.5, -1, -0.5, 0, 0.5, 1, 1.5].map((y) => text(X0 - 14, Y(y) + 7, y === 0 ? "target" : fmt(y), y === 0 ? INK : MUTED, { anchor: "end", size: 18, weight: y === 0 ? 600 : 400 })).join("");
  const H = Y(YMIN) + 178;
  const body = `
  <rect width="${W}" height="${H}" rx="24" fill="#FFFFFF" stroke="${LINE}" stroke-width="2"/>
  <text x="56" y="62" font-size="32" font-weight="700" fill="${INK}">What SteadyRoom sends, by mode</text>
  ${legend(56, 108, [["line", BLUE, "unit cools", 170], ["line", ORANGE, "unit heats", 170], ["off", INK, "switches off", 190], ["setting", COOL_SET, "", 44], ["setting", HEAT_SET, "start and stop settings, coloured by direction", 400]])}
  ${frame(coolCol, "Cool", "Cool · start / stop")}${frame(autoCol, "Auto", "Auto · start / stop distance")}${frame(heatCol, "Heat", "Heat · start / stop")}
  ${mark(heatCol, P.heatStop, `stop ≥ +${P.heatStop} K`, HEAT_SET, "right", "above")}
  ${mark(heatCol, -P.heatStart, `start ≤ −${P.heatStart} K`, HEAT_SET, "right", "below")}
  ${mark(autoCol, P.autoStop, `stop ≥ +${P.autoStop} K`, HEAT_SET, "right", "above")}
  ${mark(autoCol, -P.autoStart, `start ≤ −${P.autoStart} K`, HEAT_SET, "right", "below")}
  ${mark(autoCol, P.autoStart, `start ≥ +${P.autoStart} K`, COOL_SET, "left", "above")}
  ${mark(autoCol, -P.autoStop, `stop ≤ −${P.autoStop} K`, COOL_SET, "left", "below")}
  ${mark(coolCol, P.coolStart, `start ≥ +${P.coolStart} K`, COOL_SET, "left", "above")}
  ${mark(coolCol, -P.coolStop, `stop ≤ −${P.coolStop} K`, COOL_SET, "left", "below")}
  ${heat(heatCol, P.heatStop)}${heat(autoCol, P.autoStop)}${cool(autoCol, -P.autoStop)}${cool(coolCol, -P.coolStop)}
  ${yAxis}
  <text transform="translate(40 ${Y(0)}) rotate(-90)" font-size="17" fill="${MUTED}" text-anchor="middle">room minus target (K)</text>
  <text x="${(X0 + W - 40) / 2}" y="${Y(YMIN) + 66}" font-size="18" fill="${MUTED}" text-anchor="middle">offset sent (K): + above the unit's own reading, − below it</text>
  <text x="56" y="${H - 58}" font-size="18" fill="${MUTED}">Each dashed line is a switching point on the left axis: the unit starts or stops once the room is at it.</text>
  <text x="56" y="${H - 32}" font-size="18" fill="${MUTED}">Cooling comes down from above, heating up from below. In Auto the direction changes only through off.</text>`;
  await render("decision-map", W, H, body);
}

// Offset chart: the curve with its settings on the left, the growth factor on the right.
{
  const W = 1280, YMIN = -2.5, YMAX = 0.4, PH = 640, TOP = 220;
  const Y = (y: number) => TOP + ((YMAX - y) / (YMAX - YMIN)) * PH;
  const L = { x0: 150, w: 540, max: 5 }, R = { x0: 790, w: 450, max: 7 };
  const XL = (x: number) => L.x0 + (x / L.max) * L.w, XR = (x: number) => R.x0 + (x / R.max) * R.w;
  const ticksY = [-2.5, -2, -1.5, -1, -0.5, 0];
  const grid = (x0: number, w: number, X: (x: number) => number, ticksX: number[], yLabels: boolean) =>
    ticksY.map((y) => `<line x1="${x0}" y1="${Y(y)}" x2="${x0 + w}" y2="${Y(y)}" stroke="${y === 0 ? AXIS : GRID}" stroke-width="${y === 0 ? 2 : 1.5}"/>${yLabels ? text(x0 - 14, Y(y) + 7, y === 0 ? "target" : fmt(y), y === 0 ? INK : MUTED, { anchor: "end", size: 18, weight: y === 0 ? 600 : 400 }) : ""}`).join("")
    + ticksX.map((x) => `<line x1="${X(x)}" y1="${Y(YMAX)}" x2="${X(x)}" y2="${Y(YMIN)}" stroke="${x === 0 ? AXIS : GRID}" stroke-width="${x === 0 ? 2 : 1.5}"/><text x="${X(x)}" y="${Y(YMIN) + 28}" font-size="18" fill="${MUTED}" text-anchor="middle">${x}</text>`).join("");
  const stop = P.heatStop;
  const hline = (x0: number, w: number, y: number, color: string) => `<line x1="${x0}" y1="${Y(y)}" x2="${x0 + w}" y2="${Y(y)}" stroke="${color}" stroke-width="2.5" stroke-dasharray="6 5"/>`;

  const left = `
    <text x="${L.x0}" y="${TOP - 52}" font-size="28" font-weight="700" fill="${INK}">The offset while heating</text>
    <text x="${L.x0}" y="${TOP - 24}" font-size="16" fill="${MUTED}">Offset · minimum, Offset · knee, Preset · distance</text>
    <rect x="${L.x0}" y="${Y(YMAX)}" width="${L.w}" height="${Y(-P.presetDistance) - Y(YMAX)}" fill="${PINK_BG}"/>
    ${grid(L.x0, L.w, XL, [0, 1, 2, 3, 4, 5], true)}
    ${hline(L.x0, L.w, -P.presetDistance, PINK)}
    ${hline(L.x0, L.w, -P.knee, HEAT_SET)}
    <line x1="${XL(P.minOffset)}" y1="${Y(YMAX)}" x2="${XL(P.minOffset)}" y2="${Y(YMIN)}" stroke="${HEAT_SET}" stroke-width="2.5" stroke-dasharray="6 5"/>
    <path d="${smoothY((y) => Math.max(0, grown(-y)), YMIN, 0, XL, Y)}" fill="none" stroke="${AXIS}" stroke-width="2.5"/>
    <path d="${stairsY((y) => offset(-y, 0), -0.03, stop, XL, Y)}" fill="none" stroke="${ORANGE}" stroke-width="7" stroke-dasharray="9 7"/>
    <path d="${stairsY((y) => offset(-y), YMIN, stop, XL, Y)}" fill="none" stroke="${ORANGE}" stroke-width="5" stroke-linejoin="round"/>
    <circle cx="${XL(offset(-stop))}" cy="${Y(stop)}" r="9" fill="#FFF" stroke="${ORANGE}" stroke-width="4"/>
    <circle cx="${XL(0)}" cy="${Y(stop)}" r="7" fill="#FFF" stroke="${ORANGE}" stroke-width="3"/>
    ${text(L.x0 + L.w - 8, Y(-P.presetDistance) - 12, `preset from ≥ −${P.presetDistance} K: e.g. quiet until the run ends`, PINK, { anchor: "end", size: 18 })}
    ${text(L.x0 + L.w - 8, Y(-P.knee) + 26, `knee at −${P.knee} K: grows faster below`, HEAT_SET, { anchor: "end", size: 18 })}
    ${text(XL(P.minOffset) + 10, Y(-2.3), `minimum ${P.minOffset} K`, HEAT_SET, { size: 18 })}
    ${text(XL(1.55), Y(-1.05), "offset sent", ORANGE)}
    ${text(XL(2.75), Y(-1.15), "before rounding", MUTED, { size: 17, weight: 400 })}
    ${text(XL(2.75), Y(-1.15) + 21, "to the step", MUTED, { size: 17, weight: 400 })}
    ${text(XL(0) + 14, Y(stop) - 14, "stops", ORANGE, { size: 17, weight: 400 })}`;

  const factors: [number, string, number][] = [[0, ORANGE_LIGHT, 4], [0.5, ORANGE, 5], [1, ORANGE_DEEP, 4]];
  const right = `
    <text x="${R.x0}" y="${TOP - 52}" font-size="28" font-weight="700" fill="${INK}">Growth factor</text>
    <text x="${R.x0}" y="${TOP - 24}" font-size="16" fill="${MUTED}">Offset · growth factor</text>
    ${grid(R.x0, R.w, XR, [0, 1, 2, 3, 4, 5, 6, 7], false)}
    ${hline(R.x0, R.w, -P.knee, HEAT_SET)}
    ${text(R.x0 + R.w - 8, Y(-P.knee) + 26, `knee at −${P.knee} K`, HEAT_SET, { anchor: "end", size: 18 })}
    ${factors.map(([f, c, w]) => `<path d="${stairsY((y) => offset(-y, P.minOffset, f), YMIN, 0, XR, Y)}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linejoin="round"/>`).join("")}
    ${factors.map(([f, c], i) => `${sym(XR(3.4), Y(-0.95) + i * 32, "line", c)}<text x="${XR(3.4) + 44}" y="${Y(-0.95) + i * 32}" font-size="18" fill="${INK}">factor ${f}${f === P.factor ? " (default)" : ""}</text>`).join("")}`;

  const H = Y(YMIN) + 110;
  const body = `
  <rect width="${W}" height="${H}" rx="24" fill="#FFFFFF" stroke="${LINE}" stroke-width="2"/>
  <text x="56" y="62" font-size="32" font-weight="700" fill="${INK}">How far above its own reading the unit is set</text>
  ${legend(56, 108, [["line", ORANGE, "default", 150], ["dash", ORANGE, "with Offset · minimum 0", 300], ["setting", HEAT_SET, "offset settings", 220], ["band", PINK, "near-target preset", 260]])}
  ${left}${right}
  <text transform="translate(40 ${Y((YMAX + YMIN) / 2)}) rotate(-90)" font-size="17" fill="${MUTED}" text-anchor="middle">room minus target (K)</text>
  <text x="${W / 2}" y="${H - 34}" font-size="18" fill="${MUTED}" text-anchor="middle">offset sent (K) above the unit's own reading · heating from below; cooling is the mirror image from above</text>`;
  await render("offset-curve", W, H, body);
}

// The steps of the README table; a changed default or formula fails here instead of drawing a wrong chart.
const checks: [number, number][] = [[-0.15, 0.5], [0.5, 0.5], [0.51, 1.0], [0.91, 1.0], [0.92, 1.5], [1.23, 1.5], [1.24, 2.0], [1.73, 2.5], [1.74, 3.0], [2.5, 4.5]];
for (const [d, e] of checks) if (offset(d) !== e) throw new Error(`offset(${d}) = ${offset(d)}, expected ${e}`);
