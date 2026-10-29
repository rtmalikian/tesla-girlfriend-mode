"""Girlfriend Mode decision logic — pure, deterministic, no network.

Given the partner profile plus the current conditions (outside temperature,
speed, parked or driving), decide exactly what the passenger side of the car
should do. Only passenger-side settings are ever planned — the driver's
side is never touched.

Modes (chosen by outside temperature):
  cool       below the cool threshold: climate ON at her warm passenger
             temperature, passenger seat heater on (if she uses one).
  warm       at/above the warm threshold: climate OFF, windows cracked a
             little — but only parked or at low speed.
  in-between anything between: climate ON at her passenger temperature,
             her vent aimed up toward her head (PROPOSED API), her vent
             fan at her preferred speed (PROPOSED API).

Safety rule that beats every mode: above the freeway speed threshold the
windows are fully closed, always.

PROPOSED-API commands (labelled `proposed: True` everywhere they appear):
`vent_aim` and `set_fan_speed` — Tesla's Fleet API exposes neither an
airflow-direction command nor a fan-speed command today. They are modelled
here and in the simulator so the product is ready when the API lands
(see API_PROPOSAL.md); the real car never receives them.
"""
from __future__ import annotations

import math

# Real Fleet API commands this planner may emit (passenger-scoped only).
REAL_COMMANDS = {"climate_start", "climate_stop", "set_passenger_temp",
                 "seat_heater", "window_vent", "window_close"}
# Proposed commands — simulated only, never sent to a real car.
PROPOSED_COMMANDS = {"vent_aim", "set_fan_speed"}
# Music goes through the owner's Spotify account (active device), not the
# car's API at all — Tesla's Fleet API can't pick a playlist in the car.
SPOTIFY_COMMANDS = {"play_love_mix"}
ALL_COMMANDS = REAL_COMMANDS | PROPOSED_COMMANDS | SPOTIFY_COMMANDS


def _cmd(name: str, description: str, params: dict | None = None) -> dict:
    return {
        "command": name,
        "params": params or {},
        "proposed": name in PROPOSED_COMMANDS,
        "provider": "spotify" if name in SPOTIFY_COMMANDS else "tesla",
        "description": description,
    }


def _f_to_c(f: float) -> float:
    return round((f - 32) * 5 / 9, 1)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (for her-place geofence checks)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def at_her_place(settings, lat: float | None, lon: float | None) -> bool:
    """True when a location read falls inside her place's geofence."""
    if lat is None or lon is None or not (settings.place_lat or settings.place_lon):
        return False
    return distance_m(lat, lon, settings.place_lat, settings.place_lon) \
        <= settings.place_radius_m


def plan_girlfriend_mode(settings, outside_temp_f: float | None,
                         speed_mph: float = 0, parked: bool = True,
                         returning_to_car: bool = False) -> dict:
    """Build the Girlfriend Mode plan for the current conditions.

    outside_temp_f=None means the weather is unknown — the in-between plan
    is used and the summary says so, rather than guessing cozy or fresh-air.
    """
    name = settings.partner_name
    highway = speed_mph > settings.freeway_speed_mph

    if outside_temp_f is None:
        mode = "in_between"
    elif outside_temp_f < settings.cool_below_f:
        mode = "cool"
    elif outside_temp_f >= settings.warm_from_f:
        mode = "warm"
    else:
        mode = "in_between"

    commands: list[dict] = []
    notes: list[str] = []

    if mode == "cool":
        temp_f = settings.cool_passenger_temp_f
        commands.append(_cmd(
            "climate_start",
            f"Turn the climate on for {name}"))
        commands.append(_cmd(
            "set_passenger_temp",
            f"Set her passenger temperature to {temp_f}°F",
            {"passenger_temp_f": temp_f, "passenger_temp_c": _f_to_c(temp_f)}))
        commands.append(_cmd(
            "set_fan_speed",
            f"Set her vent fan to {settings.fan_speed} "
            "(proposed API — simulated)",
            {"fan_speed": settings.fan_speed}))
        if settings.seat_heater_level > 0:
            when = " so the seat is already cozy when she gets back in" \
                if returning_to_car else ""
            commands.append(_cmd(
                "seat_heater",
                f"Turn her passenger seat heater on at level "
                f"{settings.seat_heater_level}{when}",
                {"level": settings.seat_heater_level}))
    elif mode == "warm":
        commands.append(_cmd(
            "climate_stop",
            f"Turn the climate off — {name} prefers fresh air when it's warm"))
        if settings.warm_windows_crack and not highway:
            where = "parked" if parked else "at low speed"
            commands.append(_cmd(
                "window_vent",
                f"Crack the windows a little ({where})",
                {}))
        elif settings.warm_windows_crack and highway:
            notes.append("Windows stay closed: freeway speed beats the "
                         "warm-day window crack, every time.")
    else:  # in_between
        temp_f = settings.mid_passenger_temp_f
        commands.append(_cmd(
            "climate_start",
            f"Turn the climate on for {name}"))
        commands.append(_cmd(
            "set_passenger_temp",
            f"Set her passenger temperature to {temp_f}°F",
            {"passenger_temp_f": temp_f, "passenger_temp_c": _f_to_c(temp_f)}))
        commands.append(_cmd(
            "vent_aim",
            "Aim her passenger-side vent up toward her head "
            "(proposed API — simulated)",
            {"vent": "passenger", "direction": "up"}))
        commands.append(_cmd(
            "set_fan_speed",
            f"Set her vent fan to {settings.fan_speed} "
            "(proposed API — simulated)",
            {"fan_speed": settings.fan_speed}))

    # Music: her love-songs mix joins EVERY mode when it's enabled in her
    # profile. It runs through Spotify, so a music problem can never block
    # the comfort steps above (the service layer treats it independently).
    if settings.music_enabled:
        commands.append(_cmd(
            "play_love_mix",
            "Music: her love-songs mix will start on Spotify "
            "(on your active device — usually your phone, playing "
            "through the car)",
            {"playlist_uri": settings.spotify_playlist_uri,
             "search_phrase": settings.spotify_search_phrase,
             "shuffle": True}))

    # Freeway override: in EVERY mode, highway speed means windows closed.
    if highway:
        commands.append(_cmd(
            "window_close",
            f"Close the windows fully — you're above "
            f"{settings.freeway_speed_mph} mph",
            {}))

    if outside_temp_f is None:
        notes.append("Outside temperature unknown, so the in-between plan "
                     "was used.")
    proposed = [c["command"] for c in commands if c["proposed"]]
    if proposed:
        notes.append(
            "Vent aim and fan speed are proposed-API items: Tesla doesn't "
            "offer them yet, so they're simulated, not sent to the car.")

    temp_txt = f"{outside_temp_f:.0f}°F outside" if outside_temp_f is not None \
        else "outside temperature unknown"
    mode_txt = {"cool": "cool-day cozy mode", "warm": "warm-day fresh-air mode",
                "in_between": "in-between mode"}[mode]
    summary = f"Girlfriend Mode ({name}): {mode_txt} — {temp_txt}. " + \
        " ".join(c["description"] + "." for c in commands)
    if notes:
        summary += " " + " ".join(notes)

    return {
        "mode": mode,
        "partner_name": name,
        "outside_temp_f": outside_temp_f,
        "speed_mph": speed_mph,
        "parked": parked,
        "highway": highway,
        "commands": commands,
        "notes": notes,
        "summary": summary,
    }
