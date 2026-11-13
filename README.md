# SteadyRoom

![SteadyRoom: steady comfort from air conditioners that measure in the wrong place](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/hero.png)

[![Release](https://img.shields.io/github/v/release/b80k/steadyroom?color=E5488A)](https://github.com/b80k/steadyroom/releases)
[![Home Assistant 2026.10+](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-18BCF2?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Validate](https://github.com/b80k/steadyroom/actions/workflows/validate.yml/badge.svg)](https://github.com/b80k/steadyroom/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-3B82F6)](LICENSE)

**Your heat pump switches on, off, on, off, and the sofa never gets warm? SteadyRoom fixes that.** It stops short cycling of air conditioners whose built-in sensor sits in the wrong place, and turns them into a calm, precise room thermostat.

- 🎯 **Measures where you live**: decides from a sensor in the middle of the room, not from the unit's housing.
- 🌊 **Runs gently instead of cycling**: one steady run to the target instead of a stop-and-go every few minutes.
- 🧩 **One entity, no automation spaghetti**: works with the standard Thermostat and Tile cards, all settings on the device page.
- 🛡️ **Safe to try**: every new device starts in *Observe only* and touches nothing until you let it.

## The problem

![A wall unit reads 25.4 °C in its own warm air while the middle of the room is still at 20.4 °C](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/problem.png)

Most split units measure the temperature at their own housing, high up on the wall, right in the warm air they blow out. When heating, they believe the room has reached the target long before its centre has, throttle down, switch off, start again a few minutes later. The room swings, the compressor cycles, and nobody is comfortable.

## The fix

![Room sensor to SteadyRoom to your unit](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/how-it-works.png)

SteadyRoom puts a virtual thermostat on top of your unit. It decides heat, cool or off from a sensor in the middle of the room, and it gives the unit a setpoint relative to the unit's *own* reading. The unit therefore always sees a clear, steady demand and keeps running gently until the room itself is where you want it.

![Schematic: on its own the unit starts five times in two hours and the room stays below target; with SteadyRoom it starts once and holds the target band](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/before-after.png)

*Schematic illustration of the effect, not a measurement.*

## What you get

One climate entity per room. Put it on the standard **Thermostat card** or a **Tile card** and you have everything in one place: room temperature, target, mode (Off, Heat, Cool, Auto) and what the unit is doing. Fan speed and vane position pass through to your unit. All tuning values live as settings on the device page.

| Thermostat card | Device page |
|---|---|
| ![SteadyRoom on the standard Thermostat card: heating, target 21.0 °C, room 20.4 °C](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/thermostat-card.png) | ![SteadyRoom device page with its settings](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/device-settings.png) |

The difference in one glance: the room centre reads 20.4 °C while the wall unit believes it is already at 25 °C.

![Tile cards: SteadyRoom heating to 21.0 °C, room centre 20.4 °C, wall unit 25 °C](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/tiles.png)

It replaces what usually takes an automation and a handful of helpers: a target helper, a mode selector, an on/off switch for the schedule and four time helpers.

## Get started

Requires Home Assistant 2026.10 or newer.

1. In Home Assistant open the **Marketplace**, choose **Add from link** and enter `https://github.com/b80k/steadyroom`.
2. Install **SteadyRoom** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → SteadyRoom**.
4. Select the air conditioner, the room temperature sensor and, optionally, a fallback sensor, door/window contacts and a schedule.
5. A new device starts with **Observe only** switched on and no mode chosen: it touches nothing on your unit yet. Pick a mode on the thermostat card, compare `would_hvac_mode` and `would_setpoint` with what your unit does, then turn **Observe only** off on the device page to let SteadyRoom take over.

## How it decides

| Mode | Starts | Stops |
|---|---|---|
| Heat | room below target − 0.2 K | room at target + 0.2 K |
| Cool | room above target + 0.2 K | room at target − 0.2 K |
| Auto | heating below target − 0.5 K, cooling above target + 0.5 K | at target ± 0.2 K |

Between start and stop the unit keeps doing what it did (hysteresis). In **Auto**, a running unit never switches straight to the opposite direction: it switches off first, and the opposite direction stays locked for 15 minutes after a run ended. That prevents heat–cool ping-pong around the target.

## The setpoint sent to the unit

The setpoint is the unit's own measured temperature plus an offset (minus, when cooling). The offset depends on how far the room is from the target:

![Offset over distance to target: 0.5 K near the target, growing quadratically beyond 0.5 K, in 0.5 K steps](https://raw.githubusercontent.com/b80k/steadyroom/main/docs/images/offset.png)

- up to 0.5 K away: 0.5 K,
- beyond that it grows quadratically: g = d + 0.5 · (d − 0.5)², rounded up to the unit's step (usually 0.5 K).

| Room behind target by | Offset |
|---|---|
| ≤ 0.50 K | 0.5 K |
| ≤ 0.91 K | 1.0 K |
| ≤ 1.23 K | 1.5 K |
| ≤ 1.50 K | 2.0 K |
| ≤ 1.73 K | 2.5 K |
| 2.50 K | 4.5 K |

The offset itself has no cap; only the final setpoint is limited (16–30 °C by default). A new setpoint is only sent when it differs by at least half a step, so the unit is not flooded with commands.

## Doors, windows and schedule

- **Contacts**: if any contact stays open for 60 s, the unit switches off. While a contact is open, a stopped unit does not start. Once all contacts have been closed for 15 s, the unit resumes the direction it had before. If your contacts report *closed* as `on`, tick the inversion option. A contact that is `unavailable` or `unknown` counts as closed, so a sensor with a flat battery does not keep your unit off.
- **Schedule**: pick a Home Assistant *Schedule* helper. Outside its blocks the unit stays off. Without a schedule SteadyRoom is always active. If the schedule becomes `unavailable`, `unknown` or disappears, SteadyRoom keeps its last answer (inside, if it never had one) instead of switching the unit off.

## Robust by design

- If the room sensor is unavailable, SteadyRoom uses the fallback sensor; without either it will not start heating or cooling and says so. Switching off (mode Off, open door, end of schedule) always goes out, sensor or not. With **Sensor · maximum age** set, a sensor that has not reported for that long counts as unavailable too.
- When the unit comes back after a connection loss, SteadyRoom sends nothing for 30 s, then re-sends mode and setpoint. Cloud-connected units otherwise keep running on a command they missed. A return from unavailable never counts as the end of a run, so it does not start the Auto lock.
- A command the unit rejects is tried again after 30 s. `sent_setpoint` only shows setpoints the unit accepted.
- Nothing is sent before Home Assistant has finished starting.
- In mode **Off** SteadyRoom keeps the unit off. That includes *dry* or *fan only* started from the remote or another app: SteadyRoom switches it off again.
- Mode, target, last direction and the lock survive restarts.
- It only ever sends commands to the unit you selected. If you rename the unit, a sensor, a contact or the schedule, SteadyRoom follows the new entity id. If the unit's entity is removed, SteadyRoom stops sending and never commands another entity that later takes over the old id; select the unit again under **Configure**.

## Settings

All values are number entities on the SteadyRoom device page and take effect immediately. Each name starts with its group, so the page lists them group by group.

| Group | Setting | Default |
|---|---|---|
| Heat | start below / stop above target | 0.2 K / 0.2 K |
| Cool | start above / stop below target | 0.2 K / 0.2 K |
| Auto | start distance / stop distance | 0.5 K / 0.2 K |
| Auto | opposite direction lock | 15 min |
| Door | open delay / close delay | 60 s / 15 s |
| Offset | minimum | 0.5 K |
| Offset | knee ⚙️ | 0.5 K |
| Offset | growth factor above the knee ⚙️ | 0.5 |
| Unit | lowest / highest setpoint sent to the unit ⚙️ | 16 °C / 30 °C |
| Sensor | maximum age, 0 = no limit ⚙️ | 0 min |

⚙️ Fine tuning. These start disabled, so the device page folds them into **+5 disabled entities** and keeps the list short. While disabled they keep their default. To change one, open it there and enable it; Home Assistant reloads SteadyRoom after about 30 seconds.

To change the unit, sensors, contacts or schedule later, use **Configure** on the integration.

### Observe only

Every new device starts with the **Observe only** switch on; turn it off to let SteadyRoom take over. While it is on, SteadyRoom decides as usual but sends nothing to the unit; the attributes `would_hvac_mode` and `would_setpoint` show what it would do, so you can compare it with an existing automation for a few days. The Auto lock follows what the real unit does. Turning the switch off makes SteadyRoom take over and send mode and setpoint at once. The switch position is stored with the device's configuration and survives a crash.

Fan speed and vane position still pass through to the unit while observing: they are your own commands, not SteadyRoom's decisions.

Until you choose a mode for the first time, SteadyRoom sends nothing at all, even with **Observe only** off (`reason: not_configured`).

## Diagnostics

The climate entity carries attributes that explain every decision: `reason` (`not_configured`, `off_mode`, `in_band`, `heating`, `cooling`, `door_open`, `outside_schedule`, `locked`, `sensor_missing`, `unit_unavailable`), `distance`, `offset`, `sent_setpoint`, `last_direction`, `run_ended_at`, `locked_direction`, `lock_until`, `would_hvac_mode`, `would_setpoint`, `observe_only`.

## Not included

SteadyRoom does not compute the room temperature from several sensors, does not drive radiator valves or relays, and has no presence or presets. Use any temperature sensor you trust as input.
