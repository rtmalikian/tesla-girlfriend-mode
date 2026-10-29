"""Fake car + pretend together-trips over virtual time. No API calls, no
real cars, no credentials, no network.

The demo proves the core invariants:
  - cool day at her place → climate on + passenger seat heater on;
  - warm day, parked → windows vented + climate off;
  - warm day at freeway speed → windows fully closed (override wins);
  - only passenger-side commands are ever issued.

It also seeds a few weeks of pretend trip history so the learning engine
can show example suggestions (all pretend — DEMO DATA).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .config import Settings, VehicleConfig
from .learning import EventLog, build_suggestions, extract_patterns
from .planner import plan_girlfriend_mode

# Community-reported Fleet API rates (playbook §6): ~$1 per 1,000 commands,
# ~$1 per 500 data calls, ~$1 per 50 wake-ups. Girlfriend Mode never wakes
# a sleeping car to plan — commands only, at activation time.
COMMAND_COST = 1 / 1000
DATA_CALL_COST = 1 / 500

DEMO_NOW = datetime(2026, 10, 30, 17, 30)  # a Friday, 5:30 PM


@dataclass
class FakeVehicle:
    vin: str
    name: str
    climate_on: bool = False
    passenger_temp_c: float | None = None
    seat_heater_level: int = 0
    windows: str = "closed"          # closed | vented
    vent_aim: str | None = None      # proposed API — simulated state only
    fan_speed: str | None = None     # proposed API — simulated state only


class FakeTeslaClient:
    """Stand-in for TeslaClient with every method the service runs.
    Proposed-API items are modelled here (and ONLY here / in the demo)."""

    def __init__(self, vehicles: list[FakeVehicle]):
        self.vehicles = {v.vin: v for v in vehicles}
        self.command_log: list[tuple[str, str]] = []

    def auto_conditioning_start(self, vin: str) -> dict:
        self.vehicles[vin].climate_on = True
        self.command_log.append(("climate_start", vin))
        return {"result": True}

    def auto_conditioning_stop(self, vin: str) -> dict:
        self.vehicles[vin].climate_on = False
        self.command_log.append(("climate_stop", vin))
        return {"result": True}

    def set_passenger_temp(self, vin: str, temp_c: float) -> dict:
        self.vehicles[vin].passenger_temp_c = temp_c
        self.command_log.append(("set_passenger_temp", vin))
        return {"result": True}

    def seat_heater_passenger(self, vin: str, level: int) -> dict:
        self.vehicles[vin].seat_heater_level = level
        self.command_log.append(("seat_heater", vin))
        return {"result": True}

    def window_control(self, vin: str, action: str) -> dict:
        self.vehicles[vin].windows = "vented" if action == "vent" else "closed"
        self.command_log.append((f"window_{action}", vin))
        return {"result": True}

    # Proposed API — simulated.
    def set_airflow_direction(self, vin: str, vent: str, direction: str) -> dict:
        self.vehicles[vin].vent_aim = direction
        self.command_log.append(("vent_aim(simulated)", vin))
        return {"result": True}

    def set_fan_speed(self, vin: str, speed: str) -> dict:
        self.vehicles[vin].fan_speed = speed
        self.command_log.append(("set_fan_speed(simulated)", vin))
        return {"result": True}


class FakeSpotifyClient:
    """Stand-in for SpotifyClient — pretend account, pretend device."""

    def __init__(self):
        self.now_playing: str | None = None
        self.shuffle: bool = False

    def play_mix(self, playlist_uri: str = "",
                 search_phrase: str = "love songs mix") -> str:
        self.shuffle = True
        self.now_playing = playlist_uri or f"search: {search_phrase}"
        return self.now_playing


def demo_vehicles() -> list[FakeVehicle]:
    return [FakeVehicle(vin="VINY", name="Model Y")]


def demo_settings() -> Settings:
    s = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                 ai_mode="never")
    s.place_name = "her place"
    s.spotify_access_token = "demo-token"  # pretend account, not real
    return s


# (label, conditions) — one pretend evening, three weathers/speeds + mild.
DEMO_SCENARIOS = [
    ("Cool Friday evening at her place, walking back to the parked car",
     {"outside_temp_f": 52.0, "speed_mph": 0, "parked": True,
      "returning_to_car": True}),
    ("Warm Saturday afternoon, parked",
     {"outside_temp_f": 84.0, "speed_mph": 0, "parked": True,
      "returning_to_car": False}),
    ("Warm day, already on the freeway at 68 mph",
     {"outside_temp_f": 84.0, "speed_mph": 68, "parked": False,
      "returning_to_car": False}),
    ("Mild in-between evening, driving at 30 mph",
     {"outside_temp_f": 71.0, "speed_mph": 30, "parked": False,
      "returning_to_car": False}),
]


def seed_demo_history(log: EventLog) -> None:
    """A few weeks of pretend together-trips: Friday-evening trips to her
    place, repeated beach trips, and a seat-heater override habit."""
    # Fridays ~6 PM to her place, four weeks running.
    for week, day in enumerate((2, 9, 16, 23)):
        log.record_activation(
            trigger="nav", destination="her place", mode="cool",
            outside_temp_f=55.0,
            when=datetime(2026, 10, day, 18, 5))
    # Saturday beach trips, three weeks running.
    for day in (3, 10, 17):
        log.record_activation(
            trigger="manual", destination="the beach", mode="warm",
            outside_temp_f=83.0,
            when=datetime(2026, 10, day, 11, 0))
    # She keeps bumping the seat heater from 2 up to 3 on cool trips.
    for day in (2, 9, 16):
        log.record_override(
            setting="seat_heater", from_value=2, to_value=3, mode="cool",
            outside_temp_f=54.0,
            when=datetime(2026, 10, day, 18, 20))
    # …and the love-songs mix keeps getting skipped on beach trips.
    for day in (3, 10, 17):
        log.record_override(
            setting="music", from_value="love songs mix", to_value="skipped",
            mode="warm", outside_temp_f=83.0,
            when=datetime(2026, 10, day, 11, 10))


def run_demo(settings=None, now: datetime = DEMO_NOW) -> dict:
    """Run every scenario through the real planner against a fake car,
    then run the learning engine over the seeded pretend history."""
    settings = settings or demo_settings()
    fake = FakeTeslaClient(demo_vehicles())
    spotify = FakeSpotifyClient()
    vin = demo_vehicles()[0].vin
    scenarios = []
    for label, cond in DEMO_SCENARIOS:
        # Fresh car state per scenario so each proves its own invariant.
        car = fake.vehicles[vin]
        car.climate_on, car.seat_heater_level, car.windows = False, 0, "closed"
        car.vent_aim, car.fan_speed = None, None
        spotify.now_playing = None
        plan = plan_girlfriend_mode(
            settings, cond["outside_temp_f"], speed_mph=cond["speed_mph"],
            parked=cond["parked"], returning_to_car=cond["returning_to_car"])
        for c in plan["commands"]:
            if c["command"] == "climate_start":
                fake.auto_conditioning_start(vin)
            elif c["command"] == "climate_stop":
                fake.auto_conditioning_stop(vin)
            elif c["command"] == "set_passenger_temp":
                fake.set_passenger_temp(vin, c["params"]["passenger_temp_c"])
            elif c["command"] == "seat_heater":
                fake.seat_heater_passenger(vin, c["params"]["level"])
            elif c["command"] == "window_vent":
                fake.window_control(vin, "vent")
            elif c["command"] == "window_close":
                fake.window_control(vin, "close")
            elif c["command"] == "vent_aim":
                fake.set_airflow_direction(vin, "passenger", "up")
            elif c["command"] == "set_fan_speed":
                fake.set_fan_speed(vin, c["params"]["fan_speed"])
            elif c["command"] == "play_love_mix":
                spotify.play_mix(c["params"].get("playlist_uri", ""),
                                 c["params"].get("search_phrase",
                                                 "love songs mix"))
        names = [c["command"] for c in plan["commands"]]
        scenarios.append({
            "label": label, "plan": plan, "commands": names,
            "now_playing": spotify.now_playing,
            "car": {"climate_on": car.climate_on,
                    "seat_heater_level": car.seat_heater_level,
                    "windows": car.windows,
                    "passenger_temp_c": car.passenger_temp_c,
                    "vent_aim": car.vent_aim, "fan_speed": car.fan_speed},
        })

    cool, warm_parked, warm_freeway = scenarios[0], scenarios[1], scenarios[2]
    invariants = {
        "cool_seat_and_climate": bool(
            cool["car"]["climate_on"] and cool["car"]["seat_heater_level"] > 0),
        "warm_parked_vented_climate_off": bool(
            warm_parked["car"]["windows"] == "vented"
            and not warm_parked["car"]["climate_on"]),
        "freeway_windows_closed": bool(
            warm_freeway["car"]["windows"] == "closed"
            and "window_vent" not in warm_freeway["commands"]),
        "passenger_only": all(
            c in ("climate_start", "climate_stop", "set_passenger_temp",
                  "seat_heater", "window_vent", "window_close", "vent_aim",
                  "set_fan_speed", "play_love_mix")
            for sc in scenarios for c in sc["commands"]),
        "music_plays": all(sc["now_playing"] for sc in scenarios),
    }

    # Learning demo: seeded pretend history → patterns → suggestions.
    import tempfile
    from pathlib import Path
    log = EventLog(Path(tempfile.mkdtemp()) / "demo-events.jsonl")
    seed_demo_history(log)
    patterns = extract_patterns(log.load())
    suggestions = build_suggestions(settings, patterns, now=now,
                                    outside_temp_f=54.0)
    real_commands = sum(1 for sc in scenarios for c in sc["plan"]["commands"]
                        if not c["proposed"]
                        and c.get("provider") != "spotify")
    daily_cost = real_commands * COMMAND_COST + 1 * DATA_CALL_COST
    return {
        "now": now.isoformat(),
        "scenarios": scenarios,
        "invariants": invariants,
        "all_invariants_ok": all(invariants.values()),
        "patterns": patterns,
        "suggestions": suggestions,
        "commands_per_day": real_commands,
        "estimated_daily_cost_usd": round(daily_cost, 4),
        "estimated_monthly_cost_usd": round(daily_cost * 30, 2),
    }


def render_demo(report: dict) -> str:
    lines = [f"Virtual now: {report['now']} (pretend — DEMO DATA)", ""]
    for sc in report["scenarios"]:
        plan = sc["plan"]
        lines.append(f"Scenario: {sc['label']}")
        lines.append(f"  plan: {plan['summary']}")
        lines.append(f"  car afterwards: climate "
                     f"{'on' if sc['car']['climate_on'] else 'off'}, "
                     f"seat heater level {sc['car']['seat_heater_level']}, "
                     f"windows {sc['car']['windows']}, "
                     f"vent aim {sc['car']['vent_aim'] or '—'} (proposed), "
                     f"fan {sc['car']['fan_speed'] or '—'} (proposed)")
        if sc["now_playing"]:
            lines.append(f"  Now playing: her love-songs mix 🎵 "
                         f"({sc['now_playing']}, shuffle on, via Spotify)")
        lines.append("")
    lines.append("What it has learned (from pretend trip history):")
    for s in report["suggestions"]:
        lines.append(f"  • {s['text']}")
    lines.append("")
    lines.append(f"API calls: {report['commands_per_day']} real commands "
                 f"(proposed-API items are simulated, $0)")
    lines.append(f"Estimated API cost: ${report['estimated_daily_cost_usd']:.4f}/day, "
                 f"~${report['estimated_monthly_cost_usd']:.2f}/month")
    for k, v in report["invariants"].items():
        lines.append(f"Invariant {k}: {'OK' if v else 'FAIL'}")
    lines.append(f"Core invariants: "
                 f"{'ALL OK' if report['all_invariants_ok'] else 'FAILED'}")
    return "\n".join(lines)
