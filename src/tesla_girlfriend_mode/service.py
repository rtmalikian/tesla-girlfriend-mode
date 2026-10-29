"""Transport-independent Girlfriend Mode service: takes OpenAI-shaped
request dicts, returns OpenAI-shaped response dicts. The HTTP server
(server.py) is a thin wrapper; tests drive this class directly.

Flow for a user message:
  1. "turn on girlfriend mode" (or similar) → the deterministic planner
     builds the plan for the current conditions and the real commands
     execute (proposed-API items are labelled simulated, never sent).
     The activation is recorded in the local learning log.
  2. "any suggestions?" → the on-device learning engine answers from
     recorded patterns (works with the LLM off).
  3. Anything else → the LLM backend (if configured) answers with the
     profile + plan + current suggestions as context; an allowlisted
     JSON command block is validated and executed. With no backend, the
     capability blurb answers instead of an error.

Privacy: the event log and profile live on this machine only. Vehicle
and trip data go ONLY to the user-configured LLM backend, nowhere else.
"""
from __future__ import annotations

import itertools
import re
import time
from datetime import datetime
from pathlib import Path

from .config import spotify_configured
from .embeddings import embed_text
from .learning import EventLog, build_suggestions, extract_patterns
from .llm import LlmBackend, PROPOSED_COMMANDS, extract_command
from .planner import at_her_place, plan_girlfriend_mode
from .spotify_client import SpotifyClient, SpotifyError

CAPABILITY_BLURB = (
    "Say \"turn on girlfriend mode\" and I'll set the passenger side up "
    "the way she likes it for today's weather — cozy seat heater on cool "
    "days, windows cracked on warm days, her vent aimed up in between "
    "(vent aim and fan speed are proposed Tesla API features, so those "
    "are simulated for now). Ask \"any suggestions?\" and I'll share what "
    "I've learned from your trips together — everything is learned and "
    "stored on this computer only."
)

_ACTIVATE_HINTS = ("girlfriend mode", "partner mode", "activate", "turn on")
_SUGGESTION_HINTS = ("suggestion", "learned", "what have you learned",
                     "any tips", "improve")
_TEMP_RE = re.compile(r"(?:outside|temp(?:erature)?)[^\d]{0,14}(\d{2,3})",
                      re.IGNORECASE)
_SPEED_RE = re.compile(r"(\d{1,3})\s*mph", re.IGNORECASE)


def parse_conditions(text: str, settings) -> dict:
    """Best-effort read of conditions from a chat message; deterministic."""
    m = _TEMP_RE.search(text)
    temp = float(m.group(1)) if m else None
    m = _SPEED_RE.search(text)
    speed = float(m.group(1)) if m else 0.0
    low = text.lower()
    if speed == 0 and ("freeway" in low or "highway" in low):
        speed = settings.freeway_speed_mph + 10
    parked = "parked" in low or speed == 0
    returning = "returning" in low or "back to the car" in low or "gets back" in low
    return {"outside_temp_f": temp, "speed_mph": speed, "parked": parked,
            "returning_to_car": returning}


class GirlfriendModeService:
    def __init__(self, settings, client_factory=None, llm_factory=None,
                 now_fn=None, event_log: EventLog | None = None,
                 spotify_factory=None):
        self.settings = settings
        self.client_factory = client_factory or (lambda: None)
        self.llm_factory = llm_factory
        self.spotify_factory = spotify_factory
        self.now_fn = now_fn or datetime.now
        if event_log is not None:
            self.log = event_log
        else:
            self.log = EventLog(Path(settings.data_dir) / "events.jsonl")
        self._ids = itertools.count(1)

    # -- plumbing ------------------------------------------------------
    def _client(self):
        return self.client_factory()

    def _spotify(self):
        if self.spotify_factory is not None:
            return self.spotify_factory()
        if not spotify_configured(self.settings):
            return None
        return SpotifyClient(self.settings.spotify_access_token)

    def _run_music(self, command: dict, execute: bool) -> str:
        """Music is independent of the car: it can fail (or be skipped)
        without ever blocking the comfort settings."""
        if not execute or self.settings.dry_run:
            return "dry run — not sent"
        spotify = self._spotify()
        if spotify is None:
            return ("skipped — Spotify isn't connected yet. Run "
                    "`tgmode setup` to connect it; the rest of the plan "
                    "still ran.")
        try:
            spotify.play_mix(command["params"].get("playlist_uri", ""),
                             command["params"].get("search_phrase",
                                                   "love songs mix"))
        except SpotifyError as exc:
            return f"skipped — {exc}"
        except Exception as exc:  # music must never break activation
            return f"skipped — Spotify didn't start ({str(exc)[:100]})"
        return "done — now playing on your active Spotify device"

    def record_music_skip(self, mix_label: str = "love songs mix") -> dict:
        """A skipped mix is learning data, same as any other override."""
        return self.log.record_override(
            setting="music", from_value=mix_label, to_value="skipped",
            when=self.now_fn())

    def _llm(self):
        if self.llm_factory is not None:
            return self.llm_factory()
        if self.settings.ai_mode == "never":
            return None
        if not self.settings.ai_base_url:
            return None
        return LlmBackend(self.settings.ai_base_url, self.settings.ai_api_key,
                          self.settings.ai_model, self.settings.ai_timeout_seconds)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time())}-{next(self._ids)}"

    # -- learning --------------------------------------------------------
    def patterns(self) -> dict:
        return extract_patterns(self.log.load())

    def suggestions(self, outside_temp_f: float | None = None,
                    upcoming_destination: str | None = None) -> list[dict]:
        return build_suggestions(self.settings, self.patterns(),
                                 now=self.now_fn(),
                                 outside_temp_f=outside_temp_f,
                                 upcoming_destination=upcoming_destination)

    def suggestions_text(self, **kwargs) -> str:
        items = self.suggestions(**kwargs)
        if self.settings.learning_mode == "off":
            return ("Learning is off, so I don't keep trip patterns. Turn it "
                    "on in setup if you'd like suggestions later.")
        if not items:
            return ("No suggestions yet — I need a few trips together first "
                    "before patterns show up. Everything I learn stays on "
                    "this computer.")
        lines = ["Here's what I've noticed from your trips together:"]
        lines += [f"  • {s['text']}" for s in items]
        lines.append("(Suggestions only — I never change her profile or "
                     "the car without you.)")
        return "\n".join(lines)

    def record_override(self, setting: str, from_value, to_value,
                        mode: str | None = None,
                        outside_temp_f: float | None = None) -> dict:
        return self.log.record_override(
            setting=setting, from_value=from_value, to_value=to_value,
            mode=mode, outside_temp_f=outside_temp_f, when=self.now_fn())

    # -- activation ------------------------------------------------------
    def activate(self, conditions: dict | None = None, trigger: str = "manual",
                 destination: str | None = None, execute: bool = True) -> dict:
        """Plan + (optionally) run Girlfriend Mode. Returns the plan plus
        what actually happened per command. Records the activation in the
        learning log when it really executes."""
        conditions = conditions or {}
        plan = plan_girlfriend_mode(
            self.settings,
            conditions.get("outside_temp_f"),
            speed_mph=conditions.get("speed_mph", 0),
            parked=conditions.get("parked", True),
            returning_to_car=conditions.get("returning_to_car", False))
        results = []
        vehicle = self.settings.vehicles[0] if self.settings.vehicles else None
        for c in plan["commands"]:
            if c["command"] == "play_love_mix":
                results.append({**c, "status": self._run_music(c, execute)})
            elif c["proposed"]:
                results.append({**c, "status": "simulated (proposed API)"})
            elif not execute or self.settings.dry_run:
                results.append({**c, "status": "dry run — not sent"})
            elif vehicle is None or not vehicle.vin:
                results.append({**c, "status": "no car connected yet"})
            else:
                results.append({**c, "status": self._run(c, vehicle)})
        if execute and not self.settings.dry_run:
            dest = destination or (
                self.settings.place_name
                if conditions.get("at_her_place") else None)
            self.log.record_activation(
                trigger=trigger, destination=dest, mode=plan["mode"],
                outside_temp_f=plan["outside_temp_f"], when=self.now_fn())
        return {"plan": plan, "results": results}

    def check_location_trigger(self, lat: float, lon: float,
                               nav_destination_is_hers: bool = False) -> bool:
        """Automatic trigger: navigating to her place, or being there."""
        return nav_destination_is_hers or at_her_place(self.settings, lat, lon)

    def _run(self, command: dict, vehicle) -> str:
        client = self._client()
        if client is None:
            return "no car connected yet"
        name, params = command["command"], command.get("params", {})
        try:
            if name == "climate_start":
                client.auto_conditioning_start(vehicle.vin)
            elif name == "climate_stop":
                client.auto_conditioning_stop(vehicle.vin)
            elif name == "set_passenger_temp":
                client.set_passenger_temp(vehicle.vin, params["passenger_temp_c"])
            elif name == "seat_heater":
                client.seat_heater_passenger(vehicle.vin, params.get("level", 0))
            elif name == "window_vent":
                client.window_control(vehicle.vin, "vent")
            elif name == "window_close":
                client.window_control(vehicle.vin, "close")
            else:
                return "not a real-car command"
        except Exception as exc:
            return (f"couldn't do it: {str(exc)[:120]} — check the car is "
                    "awake and your Tesla login is still valid")
        return "done"

    def activation_text(self, outcome: dict) -> str:
        lines = [outcome["plan"]["summary"], "", "What happened, in order:"]
        for r in outcome["results"]:
            lines.append(f"  • {r['description']} — {r['status']}")
        return "\n".join(lines)

    # -- OpenAI surface --------------------------------------------------
    def models_list(self) -> dict:
        return {"object": "list", "data": [{
            "id": self.settings.model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "tesla-girlfriend-mode",
        }]}

    def chat_completions(self, body: dict) -> dict:
        messages = body.get("messages") or []
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = str(m.get("content") or "")
                break
        low = user_text.lower()
        if any(h in low for h in _SUGGESTION_HINTS):
            cond = parse_conditions(user_text, self.settings)
            text = self.suggestions_text(
                outside_temp_f=cond["outside_temp_f"])
        elif any(h in low for h in _ACTIVATE_HINTS):
            cond = parse_conditions(user_text, self.settings)
            trigger = "chat"
            outcome = self.activate(cond, trigger=trigger)
            text = self.activation_text(outcome)
        else:
            text = self._llm_answer(user_text)
        return {
            "id": self._next_id("chatcmpl"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.settings.model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                      "total_tokens": 0},
        }

    def embeddings(self, body: dict) -> dict:
        raw = body.get("input", "")
        texts = raw if isinstance(raw, list) else [raw]
        data = []
        for i, t in enumerate(texts):
            data.append({
                "object": "embedding",
                "index": i,
                "embedding": embed_text(str(t), self.settings.embedding_dim),
            })
        return {
            "object": "list",
            "data": data,
            "model": self.settings.model_id,
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }

    # -- LLM path ---------------------------------------------------------
    def _context(self) -> str:
        s = self.settings
        lines = [
            f"Partner profile: {s.partner_name}; preset {s.preset}; "
            f"cool below {s.cool_below_f}°F (passenger {s.cool_passenger_temp_f}°F, "
            f"seat heater level {s.seat_heater_level}); warm from "
            f"{s.warm_from_f}°F (windows crack: {s.warm_windows_crack}); "
            f"in-between passenger {s.mid_passenger_temp_f}°F, vent aimed up, "
            f"vent fan {s.fan_speed} (fan + vent aim are proposed API).",
        ]
        for sug in self.suggestions():
            lines.append(f"Learned suggestion: {sug['text']}")
        return "\n".join(lines)

    def _llm_answer(self, user_text: str) -> str:
        llm = self._llm()
        if llm is None:
            return CAPABILITY_BLURB
        try:
            reply = llm.chat(self._context(), user_text)
        except Exception:
            return CAPABILITY_BLURB + " (The AI backend didn't respond just now.)"
        cmd = extract_command(reply)
        if cmd is None:
            return reply
        vehicle = None
        needle = cmd["vehicle"].lower()
        for v in self.settings.vehicles:
            if needle in v.name.lower() or v.name.lower() in needle:
                vehicle = v
                break
        if vehicle is None:
            names = ", ".join(v.name for v in self.settings.vehicles) or "(none yet)"
            return (f"I couldn't match \"{cmd['vehicle']}\" to one of your "
                    f"cars. Your cars: {names}.")
        return self._execute_llm_command(cmd, vehicle)

    def _execute_llm_command(self, cmd: dict, vehicle) -> str:
        name = cmd["command"]
        if name == "play_love_mix":
            status = self._run_music(
                {"command": name, "params": cmd.get("params", {})},
                execute=True)
            return f"Music: {status}."
        if name in PROPOSED_COMMANDS:
            return (f"{name} is a proposed Tesla API feature that doesn't "
                    "exist yet — simulated only, nothing was sent to the car.")
        if self.settings.dry_run:
            return f"Dry run: would run {name} on {vehicle.name} — nothing changed."
        if not vehicle.vin:
            return (f"No car connected yet for {vehicle.name} — run "
                    "`tgmode setup`, then `tgmode auth`, and try again.")
        outcome = self._run({"command": name, "params": cmd.get("params", {})},
                            vehicle)
        if outcome == "done":
            return f"Done: {name} on {vehicle.name}."
        return f"Couldn't run {name} on {vehicle.name}: {outcome}."
