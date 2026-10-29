"""Guided first-run setup: plain-language questions, writes .env itself.

Built for Tesla owners, not developers — defaults everywhere, numbered
choices, places by name + street address (geocoded for you; nobody types
latitude/longitude), and cars picked by nickname (a VIN is optional and
can be added later at pairing time). Testable: input, output and the
geocoder are injectable.
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import PRESETS
from .geocode import geocode_address

FAN_CHOICES = {"1": "low", "2": "medium", "3": "high", "4": "auto"}


def _ask(input_fn, out, prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    out(f"{prompt}{suffix}")
    answer = input_fn("> ").strip()
    return answer or default


def _ask_required(input_fn, out, prompt: str, help_text: str) -> str:
    while True:
        out(help_text)
        answer = input_fn(f"{prompt} ").strip()
        if answer:
            return answer
        out("That one's required — without it the app can't talk to your car.")


def run_setup(input_fn=input, out=print, env_path: str = ".env",
              geocoder=geocode_address) -> Path:
    out("")
    out("Welcome to Tesla Girlfriend Mode setup — I'll ask a few questions")
    out("and write the settings file for you. Press Enter to accept a [default].")
    out("")

    path = Path(env_path)
    if path.exists():
        again = _ask(input_fn, out,
                     "A settings file (.env) already exists. Replace it? (y/n)", "n")
        if again.lower() not in ("y", "yes"):
            out("Keeping your existing settings. Nothing changed.")
            return path

    out("STEP 1 of 6 — Connect to Tesla")
    out("Create a free developer app at developer.tesla.com (sign in, then")
    out("'Create App'). Tesla will show you a Client ID and Client Secret.")
    client_id = _ask_required(input_fn, out, "Paste your Client ID:",
                              "First, the Client ID:")
    client_secret = _ask_required(input_fn, out, "Paste your Client Secret:",
                                  "Now the Client Secret (it stays on this computer):")

    out("")
    out("STEP 2 of 6 — Your cars")
    out("For each car, just a nickname (like Model Y). A VIN is optional —")
    out("find it in your Tesla app under Controls → Software, or leave it")
    out("blank and add it when you pair the car.")
    vehicles: list[tuple[str, str]] = []
    while True:
        n = len(vehicles) + 1
        name = _ask(input_fn, out,
                    f"Car {n} nickname (e.g. Model Y) — or press Enter if done:",
                    "" if vehicles else "")
        if not name:
            if vehicles:
                break
            out("Add at least one car to continue.")
            continue
        vin = _ask(input_fn, out, f"VIN for {name} (blank is fine):")
        vehicles.append((name, vin))

    out("")
    out("STEP 3 of 6 — Her profile")
    partner_name = _ask(input_fn, out,
                        "What should I call her in messages? (e.g. girlfriend, "
                        "or her name)", "girlfriend")
    out("How does she like the car? Pick a starting style — you can tweak")
    out("every number afterwards by running setup again:")
    out("  1) Runs cold (cozy) — warm seat, warm air, gentle fan")
    out("  2) Runs hot — cooler air, almost never a seat heater")
    out("  3) Fresh-air fan — windows cracked whenever it's mild")
    out("  4) Custom — set every preference myself")
    preset_choice = _ask(input_fn, out, "Pick 1, 2, 3 or 4:", "1")
    preset_key = {"1": "runs_cold", "2": "runs_hot", "3": "fresh_air"}.get(
        preset_choice, "custom")
    if preset_key == "custom":
        profile = {}
        profile["cool_below_f"] = _ask(
            input_fn, out, "Below what outside temperature (°F) is it a "
            "'cool, cozy' day?", "65")
        profile["warm_from_f"] = _ask(
            input_fn, out, "From what outside temperature (°F) is it a "
            "'warm, fresh-air' day?", "78")
        profile["cool_passenger_temp_f"] = _ask(
            input_fn, out, "Her passenger temperature on cool days (°F):", "73")
        profile["mid_passenger_temp_f"] = _ask(
            input_fn, out, "Her passenger temperature on in-between days (°F):",
            "72")
        profile["seat_heater_level"] = _ask(
            input_fn, out, "Her seat heater level on cool days "
            "(0 = never, 1-3):", "2")
        out("Her vent fan strength when the climate is running:")
        out("  1) Low   2) Medium   3) High   4) Auto")
        fan_choice = _ask(input_fn, out, "Pick 1, 2, 3 or 4:", "1")
        profile["fan_speed"] = FAN_CHOICES.get(fan_choice, "low")
        crack = _ask(input_fn, out,
                     "Crack the windows a little on warm days? (y/n)", "y")
        profile["warm_windows_crack"] = crack.lower() not in ("n", "no")
    else:
        p = PRESETS[preset_key]
        profile = {
            "cool_below_f": str(p["cool_below_f"]),
            "warm_from_f": str(p["warm_from_f"]),
            "cool_passenger_temp_f": str(p["cool_passenger_temp_f"]),
            "mid_passenger_temp_f": str(p["mid_passenger_temp_f"]),
            "seat_heater_level": str(p["seat_heater_level"]),
            "fan_speed": p["fan_speed"],
            "warm_windows_crack": bool(p["warm_windows_crack"]),
        }
    freeway = _ask(input_fn, out,
                   "Above what speed (mph) should the windows always stay "
                   "fully closed? (freeway safety)", "55")
    out("And the soundtrack: when Girlfriend Mode turns on, it can start")
    out("a Spotify love-songs mix on your phone (which plays through the")
    out("car) — the car's own Spotify app can't be picked by any app, so")
    out("it goes through your Spotify account instead.")
    music_choice = _ask(input_fn, out,
                        "Play a Spotify love-songs mix when Girlfriend "
                        "Mode turns on? (y/n)", "y")
    music_enabled = music_choice.lower() not in ("n", "no")
    spotify_playlist, spotify_token = "", ""
    if music_enabled:
        spotify_playlist = _ask(
            input_fn, out,
            "Paste a Spotify playlist link/URI for her mix — or press "
            "Enter to just search 'love songs mix':", "")
        spotify_token = _ask(
            input_fn, out,
            "Your Spotify access token (optional — stored only here; "
            "blank = connect later):", "")

    out("")
    out("STEP 4 of 6 — Her place")
    out("Girlfriend Mode can switch itself on when you navigate to her")
    out("place, arrive there, or head back to the parked car there.")
    place_name = _ask(input_fn, out,
                      "What do you call her place?", "her place")
    place_address = _ask(input_fn, out,
                         "Her street address (street, city, state) — used "
                         "once to find it on the map, stored only here:")
    place_lat, place_lon = "", ""
    if place_address:
        found = geocoder(place_address)
        if found:
            place_lat, place_lon = f"{found[0]:.6f}", f"{found[1]:.6f}"
            out(f"Found it on the map — that's where '{place_name}' is.")
        else:
            out("I couldn't find that address on the map — no problem, "
                "Girlfriend Mode will still work whenever you switch it on "
                "manually or by chat; run setup again to retry the address.")

    out("")
    out("STEP 5 of 6 — Learning & the AI brain (both optional)")
    out("Learn from trips together to suggest improvements? It notices")
    out("things like 'you usually head to her place Fridays around 6 PM'")
    out("and suggests profile tweaks when a setting keeps getting changed.")
    out("It all stays on this computer — nothing is uploaded anywhere.")
    out("  1) Yes — learn and suggest (default)")
    out("  2) No — don't record trips")
    learn_choice = _ask(input_fn, out, "Pick 1 or 2:", "1")
    learning_mode = "off" if learn_choice == "2" else "auto"
    out("And the AI brain for chat:")
    out("  1) Built-in answers only — no AI, nothing leaves this computer")
    out("  2) Ollama on this computer — free local AI (default)")
    out("  3) Another AI service (OpenAI, Groq, LM Studio…) — you'll paste its details")
    choice = _ask(input_fn, out, "Pick 1, 2 or 3:", "2")
    ai_mode, ai_url, ai_key, ai_model = "auto", "http://localhost:11434/v1", "", "llama3.1"
    if choice == "1":
        ai_mode = "never"
    elif choice == "3":
        ai_url = _ask_required(input_fn, out, "Service address (base URL):",
                               "Paste the service's API address:")
        ai_key = _ask(input_fn, out, "API key for that service (stored only here):")
        ai_model = _ask(input_fn, out, "Model name:", "gpt-4o-mini")

    out("")
    out("STEP 6 of 6 — The chat server")
    port = _ask(input_fn, out, "Port for the chat address:", "8644")
    server_key = _ask(input_fn, out,
                      "Optional password for the chat address (blank = none):")

    crack_val = profile["warm_windows_crack"]
    crack_env = "1" if crack_val is True or str(crack_val).lower() in ("1", "true", "y", "yes") else "0"
    lines = [
        "# Written by `tgmode setup` — edit by re-running setup any time.",
        f"TESLA_CLIENT_ID={client_id}",
        f"TESLA_CLIENT_SECRET={client_secret}",
        "TESLA_REGION=na",
        "TESLA_REDIRECT_URI=http://localhost:8080/callback",
        "TGM_VEHICLES=" + ",".join(f"{name}={vin}" for name, vin in vehicles),
        "TGM_SERVER_HOST=127.0.0.1",
        f"TGM_SERVER_PORT={port}",
        f"TGM_SERVER_API_KEY={server_key}",
        "TGM_MODEL_ID=tesla-girlfriend-mode",
        f"TGM_AI_BASE_URL={ai_url}",
        f"TGM_AI_API_KEY={ai_key}",
        f"TGM_AI_MODEL={ai_model}",
        f"TGM_AI_MODE={ai_mode}",
        "TGM_AI_TIMEOUT_SECONDS=20",
        "TGM_EMBEDDING_DIM=384",
        "TGM_TOKEN_FILE=~/.tgm/tokens.json",
        "TGM_DATA_DIR=~/.tgm",
        "TGM_DRY_RUN=0",
        f"TGM_LEARNING_MODE={learning_mode}",
        f"TGM_MUSIC_ENABLED={'1' if music_enabled else '0'}",
        f"TGM_SPOTIFY_PLAYLIST_URI={spotify_playlist}",
        "TGM_SPOTIFY_SEARCH_PHRASE=love songs mix",
        f"TGM_SPOTIFY_ACCESS_TOKEN={spotify_token}",
        f"TGM_PARTNER_NAME={partner_name}",
        f"TGM_PRESET={preset_key}",
        f"TGM_PLACE_NAME={place_name}",
        f"TGM_PLACE_ADDRESS={place_address}",
        f"TGM_PLACE_LAT={place_lat}",
        f"TGM_PLACE_LON={place_lon}",
        "TGM_PLACE_RADIUS_M=300",
        f"TGM_COOL_BELOW_F={profile['cool_below_f']}",
        f"TGM_WARM_FROM_F={profile['warm_from_f']}",
        f"TGM_COOL_PASSENGER_TEMP_F={profile['cool_passenger_temp_f']}",
        f"TGM_MID_PASSENGER_TEMP_F={profile['mid_passenger_temp_f']}",
        f"TGM_SEAT_HEATER_LEVEL={profile['seat_heater_level']}",
        f"TGM_FAN_SPEED={profile['fan_speed']}",
        f"TGM_WARM_WINDOWS_CRACK={crack_env}",
        f"TGM_FREEWAY_SPEED_MPH={freeway}",
    ]
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)

    out("")
    out("All set — settings saved to .env (only readable by you).")
    out("Next steps:")
    out("  1) tgmode auth        — sign in to Tesla once (opens a link)")
    out("  2) tgmode simulate    — see a demo with a pretend car and trips")
    out("  3) tgmode preview     — plain-English dry run of Girlfriend Mode")
    out("  4) tgmode serve       — start the AI chat server")
    return path
