# API Proposal — passenger airflow control for the Tesla Fleet API

**Status:** proposal. Neither endpoint below exists in the Fleet API today.
Girlfriend Mode models both in its simulator and labels them
"proposed API" everywhere they appear — the real car never receives them.

Two small gaps keep partner/passenger comfort profiles (and a whole class
of accessibility and family use cases) from working on Tesla today:

## 1. `set_airflow_direction` — vent aiming

There is no Fleet API command to aim a vent. Girlfriend Mode's
in-between-weather plan wants the passenger vent aimed **up toward her
head**; today that step is simulated only.

Proposed command:

```
POST /api/1/vehicles/{vehicle_tag}/command/set_airflow_direction
{
  "vent": "passenger",            // driver | passenger | rear_left | rear_right
  "direction": "up",              // up | neutral | down | face | feet
  "angle_degrees": 30             // optional, vendor-defined range
}
```

Response mirrors existing climate commands (`{"result": true, "reason": ""}`).

## 2. `set_fan_speed` — fan speed parameter

The Fleet API can start/stop climate and set temperatures, but exposes
**no fan-speed control**. A passenger who "runs cold" often wants warm
air moving *gently* (fan on Low); others want it strong. Girlfriend Mode
stores her preference (`low | medium | high | auto`) and applies it in
every plan where the climate is running — simulated today.

Proposed command (or, equivalently, an optional parameter on
`auto_conditioning_start`):

```
POST /api/1/vehicles/{vehicle_tag}/command/set_fan_speed
{
  "fan_speed": "low",             // low | medium | high | auto, or 1..10
  "zone": "passenger"             // optional: all | driver | passenger
}
```

## Why this is safe to add

- Both commands are passenger-comfort-only, no vehicle motion, no locks,
  no charging — the same risk class as `set_temps` and
  `remote_seat_heater_request`, which already exist.
- Both are idempotent set-points, trivially rate-limitable like other
  climate commands.
- Until they exist, this app ships the full product around them:
  planner, simulator, AI endpoints, and learning engine — ready the day
  the API lands.
