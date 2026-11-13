# SteadyRoom

Stops short cycling of air conditioners whose built-in sensor sits in the wrong place.

Most split units measure the temperature at their own housing, high up on the wall, right in the warm air they blow out. When heating, they believe the room has reached the target long before its centre has, throttle down, switch off, start again a few minutes later. The room swings, the compressor cycles, and nobody is comfortable.

SteadyRoom puts a virtual thermostat on top of your unit. It decides heat, cool or off from a sensor in the middle of the room, and it gives the unit a setpoint relative to the unit's *own* reading. The unit therefore always sees a clear, steady demand and keeps running gently until the room itself is where you want it.

## What you get

One climate entity per room. Put it on the standard **Thermostat card** or a **Tile card** and you have everything in one place: room temperature, target, mode (Off, Heat, Cool, Auto) and what the unit is doing. Fan speed and vane position pass through to your unit. All tuning values live as settings on the device page.

It replaces what usually takes an automation and a handful of helpers: a target helper, a mode selector, an on/off switch for the schedule and four time helpers.

## How it decides

| Mode | Starts | Stops |
|---|---|---|
| Heat | room below target − 0.2 K | room at target + 0.2 K |
| Cool | room above target + 0.2 K | room at target − 0.2 K |
| Auto | heating below target − 0.5 K, cooling above target + 0.5 K | at target ± 0.2 K |

Between start and stop the unit keeps doing what it did (hysteresis). In **Auto**, a running unit never switches straight to the opposite direction: it switches off first, and the opposite direction stays locked for 15 minutes after a run ended. That prevents heat–cool ping-pong around the target.

## The setpoint sent to the unit

The setpoint is the unit's own measured temperature plus an offset (minus, when cooling). The offset depends on how far the room is from the target:

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

- If the room sensor is unavailable, SteadyRoom uses the fallback sensor; without either it will not start heating or cooling and says so. Switching off (mode Off, open door, end of schedule) always goes out, sensor or not. With **Maximum sensor age** set, a sensor that has not reported for that long counts as unavailable too.
- When the unit comes back after a connection loss, SteadyRoom sends nothing for 30 s, then re-sends mode and setpoint. Cloud-connected units otherwise keep running on a command they missed. A return from unavailable never counts as the end of a run, so it does not start the Auto lock.
- A command the unit rejects is tried again after 30 s. `sent_setpoint` only shows setpoints the unit accepted.
- Nothing is sent before Home Assistant has finished starting.
- In mode **Off** SteadyRoom keeps the unit off. That includes *dry* or *fan only* started from the remote or another app: SteadyRoom switches it off again.
- Mode, target, last direction and the lock survive restarts.
- It only ever sends commands to the unit you selected. If you rename the unit, a sensor, a contact or the schedule, SteadyRoom follows the new entity id. If the unit's entity is removed, SteadyRoom stops sending and never commands another entity that later takes over the old id; select the unit again under **Configure**.

## Installation

Requires Home Assistant 2026.10 or newer.

1. In Home Assistant open the **Marketplace**, choose **Add from link** and enter `https://github.com/b80k/steadyroom`.
2. Install **SteadyRoom** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → SteadyRoom**.
4. Select the air conditioner, the room temperature sensor and, optionally, a fallback sensor, door/window contacts and a schedule.
5. A new device starts with **Observe only** switched on and no mode chosen: it touches nothing on your unit yet. Pick a mode on the thermostat card, compare `would_hvac_mode` and `would_setpoint` with what your unit does, then turn **Observe only** off on the device page to let SteadyRoom take over.

## Settings

All values are number entities on the SteadyRoom device page and take effect immediately.

| Setting | Default |
|---|---|
| Heat start / stop | 0.2 K / 0.2 K |
| Cool start / stop | 0.2 K / 0.2 K |
| Auto start / stop | 0.5 K / 0.2 K |
| Minimum offset | 0.5 K |
| Knee of the offset curve | 0.5 K |
| Growth factor above the knee | 0.5 |
| Lock of the opposite direction (Auto) | 15 min |
| Lowest / highest setpoint sent to the unit | 16 °C / 30 °C |
| Door open delay / close delay | 60 s / 15 s |
| Maximum sensor age (0 = no limit) | 0 min |

To change the unit, sensors, contacts or schedule later, use **Configure** on the integration.

### Observe only

Every new device starts with the **Observe only** switch on; turn it off to let SteadyRoom take over. While it is on, SteadyRoom decides as usual but sends nothing to the unit; the attributes `would_hvac_mode` and `would_setpoint` show what it would do, so you can compare it with an existing automation for a few days. The Auto lock follows what the real unit does. Turning the switch off makes SteadyRoom take over and send mode and setpoint at once. The switch position is stored with the device's configuration and survives a crash.

Fan speed and vane position still pass through to the unit while observing: they are your own commands, not SteadyRoom's decisions.

Until you choose a mode for the first time, SteadyRoom sends nothing at all, even with **Observe only** off (`reason: not_configured`).

## Diagnostics

The climate entity carries attributes that explain every decision: `reason` (`not_configured`, `off_mode`, `in_band`, `heating`, `cooling`, `door_open`, `outside_schedule`, `locked`, `sensor_missing`, `unit_unavailable`), `distance`, `offset`, `sent_setpoint`, `last_direction`, `run_ended_at`, `locked_direction`, `lock_until`, `would_hvac_mode`, `would_setpoint`, `observe_only`.

## Not included

SteadyRoom does not compute the room temperature from several sensors, does not drive radiator valves or relays, and has no presence or presets. Use any temperature sensor you trust as input.
