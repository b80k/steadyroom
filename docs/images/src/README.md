# README graphics

The drawn graphics in `docs/images` are generated from the scripts in this folder. They need [Bun](https://bun.sh) and, for identical output, macOS (the text is set in Helvetica Neue; elsewhere the fallback font shifts labels slightly).

```bash
cd docs/images/src
bun install
bun run build
```

| Script | Writes | From |
|---|---|---|
| `illustrations.ts` | `hero.png`, `problem.png`, `how-it-works.png`, `before-after.png` | fixed drawings; the before/after curves come from the room model in `sim.ts` |
| `charts.ts` | `decision-map.png`, `offset-curve.png` | the defaults in `logic.py` and `const.py`, read by `defaults.ts` |
| `cards.ts` | `cards.png` | the screenshots in `raw/`, sized to `device-settings.png` |

## Colours

One meaning per colour in every graphic: orange is the unit and heating, blue the room sensor and cooling, pink SteadyRoom. Start and stop settings use the darker shade of their direction. Temperature always runs upwards: cold below, warm above.

## Screenshots

`device-settings.png` and the two files in `raw/` are screenshots from a Home Assistant test instance at double resolution, with the room at 20.4 °C, the target at 21.0 °C and the unit reporting 25 °C, the worked example of the README. After replacing one of them, run `bun cards.ts`: it pads `cards.png` to the height of the device page so both columns of the table start at the top.

`thermostat-card.png` and `tiles.png` in `docs/images` are not used by the current README. They stay because the READMEs of the releases up to 0.1.3 link to them.
