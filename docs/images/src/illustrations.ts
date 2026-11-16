// The drawn illustrations of the README: hero, problem, how it works, before and after.
import { AXIS, BLUE, INK, LINE, MUTED, ORANGE, PINK, REPO, path, render } from "./lib.ts";
import { onItsOwn, withSteadyRoom } from "./sim.ts";

const icon = Buffer.from(await Bun.file(`${REPO}/custom_components/steadyroom/brand/icon@2x.png`).arrayBuffer()).toString("base64");

// Hero: an abstract version of the before/after chart. Temperature runs upwards;
// with SteadyRoom the room comes up from the cold and lies flat on the target.
{
  const W = 1280, H = 400, M = 72;            // outer margin left and right
  const x0 = 700, x1 = W - M;                  // the chart block on the right
  const TOP = 96, BOTTOM = 352;                // top of the icon, baseline of the caps line
  const tgt = 252, cold = 346;                 // y of the target and of the cold start
  const X = (f: number) => x0 + f * (x1 - x0);
  const curve = (f: (u: number) => number) => path(Array.from({ length: 241 }, (_, i) => { const u = i / 240; return [X(u), f(u)] as [number, number]; }));
  // with SteadyRoom: quickly to the target, then calm on it
  const steady = curve((u) => tgt + (cold - tgt) * Math.exp(-u / 0.09) + 1.2 * Math.sin(u * 14) * (1 - Math.exp(-u / 0.09)));
  // on its own: slow, stays below, fidgets ever faster
  const own = curve((u) => tgt + 22 + (cold - tgt - 22) * Math.exp(-u / 0.22) + 3 * Math.sin(u * u * 90) * Math.min(1, u * 3));
  const body = `
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0B1220"/><stop offset="1" stop-color="#1E1B4B"/></linearGradient>
    <radialGradient id="glow" cx=".78" cy=".5" r=".5"><stop offset="0" stop-color="${PINK}" stop-opacity=".22"/><stop offset="1" stop-color="${PINK}" stop-opacity="0"/></radialGradient>
    <linearGradient id="warm" gradientUnits="userSpaceOnUse" x1="0" y1="${cold}" x2="0" y2="${tgt}"><stop offset="0" stop-color="${BLUE}"/><stop offset="1" stop-color="${PINK}"/></linearGradient>
  </defs>
  <rect width="${W}" height="${H}" rx="28" fill="url(#bg)"/>
  <rect width="${W}" height="${H}" rx="28" fill="url(#glow)"/>
  <image href="data:image/png;base64,${icon}" x="${M}" y="${TOP}" width="112" height="112"/>
  <text x="206" y="190" font-size="76" font-weight="700" fill="#FFFFFF" letter-spacing="-1.5">SteadyRoom</text>
  <text x="${M}" y="268" font-size="30" fill="#E2E8F0">Steady comfort from air conditioners</text>
  <text x="${M}" y="308" font-size="30" fill="#E2E8F0">that measure in the wrong place.</text>
  <text x="${M}" y="${BOTTOM}" font-size="19" fill="#94A3B8" letter-spacing="2">HOME ASSISTANT INTEGRATION · HEAT · COOL · AUTO</text>

  <circle cx="${x0 + 6}" cy="184" r="6" fill="${PINK}"/>
  <text x="${x0 + 22}" y="190" font-size="19" fill="#FFFFFF">with SteadyRoom</text>
  <circle cx="${x0 + 206}" cy="184" r="6" fill="${ORANGE}"/>
  <text x="${x0 + 222}" y="190" font-size="19" fill="#CBD5E1">on its own</text>

  <line x1="${x0}" y1="${BOTTOM}" x2="${x1}" y2="${BOTTOM}" stroke="#475569" stroke-width="2" stroke-linecap="round"/>
  <line x1="${x0}" y1="${tgt}" x2="${x1}" y2="${tgt}" stroke="#64748B" stroke-dasharray="6 8" stroke-width="2"/>
  <text x="${x1}" y="${tgt - 12}" font-size="15" fill="#94A3B8" text-anchor="end">target</text>
  <path d="${own}" fill="none" stroke="${ORANGE}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round" opacity=".9"/>
  <path d="${steady}" fill="none" stroke="url(#warm)" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>`;
  await render("hero", W, H, body);
}

// The problem: a cross-section of the room.
{
  const W = 1280, H = 524;
  const body = `
  <defs>
    <linearGradient id="air" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${ORANGE}" stop-opacity=".55"/><stop offset=".35" stop-color="${ORANGE}" stop-opacity=".12"/><stop offset="1" stop-color="${BLUE}" stop-opacity=".16"/></linearGradient>
  </defs>
  <rect width="${W}" height="${H}" rx="24" fill="#FFFFFF" stroke="${LINE}" stroke-width="2"/>
  <g transform="translate(0 -96)">
  <rect x="56" y="150" width="760" height="410" rx="10" fill="url(#air)" stroke="#CBD5E1" stroke-width="3"/>
  <line x1="56" y1="560" x2="816" y2="560" stroke="#94A3B8" stroke-width="6"/>
  <rect x="76" y="176" width="230" height="58" rx="14" fill="#F8FAFC" stroke="#94A3B8" stroke-width="3"/>
  <line x1="96" y1="220" x2="286" y2="220" stroke="#CBD5E1" stroke-width="3"/>
  <path d="M110 250 q18 40 60 70 M160 250 q22 46 80 76 M210 250 q26 50 100 80" fill="none" stroke="${ORANGE}" stroke-width="5" stroke-linecap="round" stroke-dasharray="2 12" opacity=".9"/><line x1="286" y1="205" x2="350" y2="205" stroke="${ORANGE}" stroke-width="3"/>
  <circle cx="286" cy="205" r="10" fill="${ORANGE}"/>
  <rect x="350" y="177" width="148" height="56" rx="12" fill="${ORANGE}"/>
  <text x="424" y="215" font-size="28" font-weight="700" fill="#FFF" text-anchor="middle">25.0 °C</text>
  <rect x="438" y="470" width="300" height="70" rx="18" fill="#CBD5E1"/>
  <rect x="438" y="436" width="44" height="104" rx="14" fill="#CBD5E1"/>
  <rect x="694" y="436" width="44" height="104" rx="14" fill="#CBD5E1"/>
  <line x1="588" y1="360" x2="588" y2="428" stroke="${BLUE}" stroke-width="4"/>
  <circle cx="588" cy="428" r="12" fill="${BLUE}"/>
  <rect x="514" y="320" width="148" height="48" rx="12" fill="${BLUE}"/>
  <text x="588" y="353" font-size="26" font-weight="700" fill="#FFF" text-anchor="middle">20.4 °C</text>
  <g font-size="22">
    <text x="868" y="200" font-weight="700" fill="${ORANGE}">At the unit</text>
    <text x="868" y="232" fill="${INK}">It reads the air it just blew out.</text>
    <text x="868" y="262" fill="${INK}">Target reached, so it throttles</text>
    <text x="868" y="292" fill="${INK}">down and switches off.</text>
    <text x="868" y="372" font-weight="700" fill="${BLUE}">Where you sit</text>
    <text x="868" y="404" fill="${INK}">Still too cold. A few minutes</text>
    <text x="868" y="434" fill="${INK}">later the unit starts again.</text>
    <text x="868" y="514" fill="${MUTED}">The room swings, the compressor</text>
    <text x="868" y="544" fill="${MUTED}">cycles, nobody is comfortable.</text>
  </g></g>`;
  await render("problem", W, H, body);
}

// How it works: room sensor, SteadyRoom, unit. The numbers are one worked example of the defaults.
{
  const W = 1280, H = 304;
  const box = (x: number, title: string, lines: string[], color: string) => `
    <rect x="${x}" y="150" width="340" height="190" rx="20" fill="#F8FAFC" stroke="${color}" stroke-width="3"/>
    <rect x="${x}" y="150" width="340" height="12" rx="6" fill="${color}"/>
    <text x="${x + 28}" y="208" font-size="25" font-weight="700" fill="${INK}">${title}</text>
    ${lines.map((l, i) => `<text x="${x + 28}" y="${248 + i * 32}" font-size="20" fill="${MUTED}">${l}</text>`).join("")}`;
  const arrow = (x: number) => `<path d="M${x} 245 h44 m-14 -14 l14 14 l-14 14" fill="none" stroke="#94A3B8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
  const body = `
  <rect width="${W}" height="${H}" rx="24" fill="#FFFFFF" stroke="${LINE}" stroke-width="2"/>
  <g transform="translate(0 -96)">
  ${box(56, "Room sensor", ["In the middle of the room:", "20.4 °C, target 21.0 °C"], BLUE)}
  ${arrow(410)}
  ${box(470, "SteadyRoom", ["Decides heat, cool or off:", "0.6 K too cold, so heat"], PINK)}
  ${arrow(824)}
  ${box(884, "Your unit", ["Gets its own reading + offset:", "25.0 °C + 1.0 K = 26.0 °C"], ORANGE)}</g>`;
  await render("how-it-works", W, H, body);
}

// Before and after (schematic): the same room model under both controls.
{
  const W = 1280, H = 720, N = 360;
  const panel = (y0: number, title: string, sub: string, data: { room: [number, number][]; on: [number, number][] }, color: string) => {
    const x0 = 150, w = 1060, h = 170;
    const X = (i: number) => x0 + (i / N) * w;
    const Y = (t: number) => y0 + h - ((t - 18.5) / 3.5) * h;
    const pts = data.room.map(([i, t]) => [X(i), Y(t)] as [number, number]);
    const bars = data.on.map(([a, b]) => `<rect x="${X(a)}" y="${y0 + h + 22}" width="${Math.max(2, X(b) - X(a))}" height="18" rx="4" fill="${color}"/>`).join("");
    return `
    <text x="56" y="${y0 - 46}" font-size="25" font-weight="700" fill="${INK}">${title}</text>
    <text x="56" y="${y0 - 16}" font-size="20" fill="${MUTED}">${sub}</text>
    <rect x="${x0}" y="${Y(21.2)}" width="${w}" height="${Y(20.8) - Y(21.2)}" fill="${AXIS}" opacity=".16"/>
    <line x1="${x0}" y1="${Y(21)}" x2="${x0 + w}" y2="${Y(21)}" stroke="${MUTED}" stroke-width="2" stroke-dasharray="6 6"/>
    <text x="${x0 - 14}" y="${Y(21) + 7}" font-size="18" font-weight="600" fill="${INK}" text-anchor="end">21 °C</text>
    <text x="${x0 - 14}" y="${Y(19) + 7}" font-size="18" fill="${MUTED}" text-anchor="end">19 °C</text>
    <path d="${path(pts)}" fill="none" stroke="${color}" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>
    <text x="${x0 - 14}" y="${y0 + h + 37}" font-size="18" fill="${MUTED}" text-anchor="end">unit on</text>
    <rect x="${x0}" y="${y0 + h + 22}" width="${w}" height="18" rx="4" fill="#F1F5F9"/>${bars}`;
  };
  const a = onItsOwn(N), b = withSteadyRoom(N);
  const body = `
  <rect width="${W}" height="${H}" rx="24" fill="#FFFFFF" stroke="${LINE}" stroke-width="2"/>
  ${panel(150, "On its own", `long runs at first, then ever shorter on and off, the sofa creeps up but never gets to 21 °C`, a, ORANGE)}
  ${panel(460, "With SteadyRoom", `at the target much sooner, then a few long runs with real off-time that keeps growing`, b, PINK)}
  <text x="150" y="700" font-size="17" fill="#94A3B8">0 h</text>
  <text x="1210" y="700" font-size="17" fill="#94A3B8" text-anchor="end">6 h · same room, same unit · schematic</text>`;
  await render("before-after", W, H, body);
}
