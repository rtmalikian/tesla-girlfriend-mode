"""On-device pattern learning + suggestions — deterministic statistics,
no LLM required, nothing leaves this computer.

What it records (local JSONL in the app's data dir — gitignored, never
committed, never uploaded):
  - activations: trigger type, destination/place name, weekday, time,
    the mode chosen, and the weather at the time;
  - overrides: settings the driver changed by hand after an activation
    (seat heater, fan, windows, passenger temp) — the strongest signal
    that a saved preference is wrong.

What it suggests (advisory only — suggestions NEVER change the profile
and NEVER command the car; the owner accepts or ignores them):
  1. Recurring together-times: "you usually head to her place Fridays
     around 6 PM" → a heads-up to pre-activate / pre-warm.
  2. Frequent shared destinations: places often visited with Girlfriend
     Mode on → suggest activating when a trip there starts.
  3. Override learning: the same setting overridden the same way on
     OVERRIDE_THRESHOLD+ trips → suggest updating her profile default.
  4. Weather-pattern fit: today's weather matches trips where a
     different mode kept being chosen/adjusted → surface it.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .embeddings import embed_text

OVERRIDE_THRESHOLD = 3     # same override, this many trips, before suggesting
MIN_TRIPS_FOR_PATTERN = 3  # recurring-time / destination patterns need support
SIMILARITY_THRESHOLD = 0.55  # embedding cosine for "same place, new spelling"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday"]


class EventLog:
    """Append-only JSONL store. Injectable path so tests never touch the
    owner's real log."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def record(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(event) + "\n")

    def record_activation(self, *, trigger: str, destination: str | None,
                          mode: str, outside_temp_f: float | None,
                          when: datetime | None = None) -> dict:
        when = when or datetime.now()
        event = {
            "type": "activation",
            "trigger": trigger,                # nav | arrival | manual | chat
            "destination": destination or "",
            "weekday": when.weekday(),          # Monday = 0
            "hour": when.hour,
            "mode": mode,
            "outside_temp_f": outside_temp_f,
            "at": when.isoformat(),
        }
        self.record(event)
        return event

    def record_override(self, *, setting: str, from_value, to_value,
                        mode: str | None = None,
                        outside_temp_f: float | None = None,
                        when: datetime | None = None) -> dict:
        when = when or datetime.now()
        event = {
            "type": "override",
            "setting": setting,                 # seat_heater|fan|windows|passenger_temp
            "from": from_value,
            "to": to_value,
            "mode": mode,
            "outside_temp_f": outside_temp_f,
            "weekday": when.weekday(),
            "hour": when.hour,
            "at": when.isoformat(),
        }
        self.record(event)
        return event

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn last line must never break suggestions
        return events


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are unit-normalised


def similar_place(name: str, known_places: list[str], dim: int = 384) -> str | None:
    """Match a new destination string to a learned shared destination using
    the local feature-hashing embeddings (same engine as /v1/embeddings)."""
    if not name or not known_places:
        return None
    target = embed_text(name.lower(), dim)
    best, best_score = None, 0.0
    for place in known_places:
        if place.lower() == name.lower():
            return place
        score = _cosine(target, embed_text(place.lower(), dim))
        if score > best_score:
            best, best_score = place, score
    return best if best_score >= SIMILARITY_THRESHOLD else None


def _hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12} {suffix}"


def extract_patterns(events: list[dict]) -> dict:
    """Pure statistics over the event log — fully testable, no I/O."""
    activations = [e for e in events if e.get("type") == "activation"]
    overrides = [e for e in events if e.get("type") == "override"]

    # 1. Recurring (weekday, destination) clusters with a typical hour.
    by_slot: dict[tuple[int, str], list[int]] = defaultdict(list)
    for e in activations:
        dest = (e.get("destination") or "").strip()
        if dest:
            by_slot[(e["weekday"], dest.lower())].append(e["hour"])
    recurring = []
    for (weekday, dest), hours in by_slot.items():
        if len(hours) >= MIN_TRIPS_FOR_PATTERN:
            typical = Counter(hours).most_common(1)[0][0]
            recurring.append({
                "weekday": weekday, "destination": dest,
                "typical_hour": typical, "trips": len(hours),
            })
    recurring.sort(key=lambda r: -r["trips"])

    # 2. Frequent shared destinations (any weekday).
    dest_counts = Counter((e.get("destination") or "").strip().lower()
                          for e in activations if (e.get("destination") or "").strip())
    frequent = [{"destination": d, "trips": n}
                for d, n in dest_counts.most_common()
                if n >= MIN_TRIPS_FOR_PATTERN]

    # 3. Repeated identical overrides.
    override_counts = Counter(
        (e["setting"], str(e.get("from")), str(e.get("to"))) for e in overrides)
    repeated_overrides = [
        {"setting": s, "from": f, "to": t, "trips": n}
        for (s, f, t), n in override_counts.most_common()
        if n >= OVERRIDE_THRESHOLD]

    # 4. Mode actually used per weather band (what really happened vs plan).
    bands: dict[str, Counter] = defaultdict(Counter)
    for e in activations:
        temp = e.get("outside_temp_f")
        if temp is None:
            continue
        band = "cool" if temp < 60 else "warm" if temp >= 80 else "in_between"
        bands[band][e.get("mode")] += 1
    weather_modes = {band: dict(counts) for band, counts in bands.items()}

    return {
        "activations": len(activations),
        "overrides": len(overrides),
        "recurring_times": recurring,
        "frequent_destinations": frequent,
        "repeated_overrides": repeated_overrides,
        "weather_modes": weather_modes,
    }


_SETTING_PHRASES = {
    "seat_heater": ("her seat heater", "seat heater level"),
    "fan": ("her vent fan", "fan speed"),
    "windows": ("the windows", "window setting"),
    "passenger_temp": ("her passenger temperature", "passenger temperature"),
    "music": ("her love-songs mix", "music"),
}


def build_suggestions(settings, patterns: dict,
                      now: datetime | None = None,
                      outside_temp_f: float | None = None,
                      upcoming_destination: str | None = None) -> list[dict]:
    """Turn patterns into plain-English, advisory-only suggestions.
    Returns [] when there isn't enough history — never invents patterns."""
    if getattr(settings, "learning_mode", "auto") == "off":
        return []
    now = now or datetime.now()
    name = settings.partner_name
    out: list[dict] = []

    # 1. Recurring together-time coming up today.
    for r in patterns["recurring_times"]:
        if r["weekday"] == now.weekday():
            out.append({
                "kind": "recurring_time",
                "text": (f"You usually head to {r['destination']} on "
                         f"{WEEKDAY_NAMES[r['weekday']]}s around "
                         f"{_hour_label(r['typical_hour'])} ({r['trips']} trips "
                         f"so far). Want Girlfriend Mode pre-activated — and "
                         f"the seat pre-warmed — before you leave today?"),
            })
            break

    # 2. Trip starting to a frequent shared destination (embedding-matched).
    if upcoming_destination:
        match = similar_place(
            upcoming_destination,
            [f["destination"] for f in patterns["frequent_destinations"]])
        her_place = (settings.place_name or "").lower()
        if match and match != her_place:
            out.append({
                "kind": "frequent_destination",
                "text": (f"You often have Girlfriend Mode on for trips to "
                         f"{match}. Activate it for this trip too, so the "
                         f"passenger side is set up {name}'s way?"),
            })

    # 3. Repeated overrides → propose a profile-default update (never silent).
    for o in patterns["repeated_overrides"]:
        if o["setting"] == "music":
            out.append({
                "kind": "override_learning",
                "text": (f"The love-songs mix was skipped on the last "
                         f"{o['trips']} trips together. Want to pick a "
                         f"different mix for {name}'s profile? "
                         f"(Suggestion only — nothing changes unless "
                         f"you say so.)"),
            })
            continue
        label, _ = _SETTING_PHRASES.get(o["setting"], (o["setting"], o["setting"]))
        out.append({
            "kind": "override_learning",
            "text": (f"On the last {o['trips']} trips, {label} was changed "
                     f"from {o['from']} to {o['to']} after Girlfriend Mode "
                     f"activated. Make {o['to']} the saved default for "
                     f"{name}? (Suggestion only — nothing changes unless "
                     f"you say so.)"),
        })

    # 4. Weather-pattern fit: today's band historically used another mode.
    if outside_temp_f is not None:
        band = "cool" if outside_temp_f < 60 else \
            "warm" if outside_temp_f >= 80 else "in_between"
        planned = "cool" if outside_temp_f < settings.cool_below_f else \
            "warm" if outside_temp_f >= settings.warm_from_f else "in_between"
        counts = patterns["weather_modes"].get(band, {})
        total = sum(counts.values())
        for mode, n in counts.items():
            if mode != planned and total >= MIN_TRIPS_FOR_PATTERN \
                    and n / total >= 0.6:
                out.append({
                    "kind": "weather_fit",
                    "text": (f"On past days like today ({band} weather), "
                             f"Girlfriend Mode most often ended up in "
                             f"{mode.replace('_', '-')} mode ({n} of {total} "
                             f"trips) — not the {planned.replace('_', '-')} "
                             f"mode the temperature rules pick. Worth "
                             f"previewing before you set off."),
                })
                break

    return out
