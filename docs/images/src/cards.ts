// Thermostat card and tile cards in one image: the left column of the README's screenshot table.
// Markdown cannot align table cells to the top, so the image gets the size of the device page
// screenshot next to it, with transparency below the cards. Run this again after replacing a screenshot.
import { Resvg } from "@resvg/resvg-js";
import { IMAGES } from "./lib.ts";

type Shot = { data: string; width: number; height: number };

async function png(file: string): Promise<Shot> {
  const bytes = Buffer.from(await Bun.file(file).arrayBuffer());
  return { data: bytes.toString("base64"), width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

const thermostat = await png(`${import.meta.dir}/raw/thermostat-card.png`);
const tiles = await png(`${import.meta.dir}/raw/tiles.png`);
const device = await png(`${IMAGES}/device-settings.png`);

const BACKGROUND = "#FAFAFA"; // Home Assistant's page background in the light theme
const GAP = 24;
const width = device.width;
const margin = (width - thermostat.width) / 2;
if (margin < 0 || tiles.width !== thermostat.width) throw new Error("the raw screenshots must share one width and fit the device page screenshot");

const content = margin + thermostat.height + GAP + tiles.height + margin;
const height = Math.max(content, device.height);
const image = (shot: Shot, y: number) =>
  `<image href="data:image/png;base64,${shot.data}" x="${margin}" y="${y}" width="${shot.width}" height="${shot.height}"/>`;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="${width}" height="${content}" rx="24" fill="${BACKGROUND}"/>
  ${image(thermostat, margin)}${image(tiles, margin + thermostat.height + GAP)}
</svg>`;
await Bun.write(`${IMAGES}/cards.png`, new Resvg(svg, { fitTo: { mode: "original" } }).render().asPng());
console.log("cards.png");
