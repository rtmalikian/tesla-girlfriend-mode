# Tesla Girlfriend Mode — The Passenger Seat, Set Up Her Way (Model 3, Model Y, Model S, Model X, Cybertruck)

**Free, open-source Tesla Fleet API app that learns how your girlfriend likes the car — and sets up the passenger side that way, automatically, chosen by the weather outside.**

▶ **[Try the live demo](https://rtmalikian.github.io/tesla-girlfriend-mode/)** — slide the temperature and speed, press Activate, and watch her plan (plus what it has "learned") appear. Pretend data only, no install, no car needed.

Cars remember *driver* profiles. Nobody profiles the passenger. Girlfriend Mode is a partner-comfort profile for the passenger seat: when it activates, the car sets itself up the way *she* likes it — and it **learns from your trips together** and suggests improvements, without ever changing anything on its own.

**No AI needed:** the weather rules, the learning engine, and the suggestions all work with zero AI involved. The optional AI layer only powers free-form chat — the rules engine always computes, suggestions are always advisory.

## What it does (default profile: she runs cold)

- **Cool outside (below 65°F):** climate on, her passenger temperature warm (73°F), and her **passenger seat heater on (level 2)** — including pre-warming the seat when you're heading back to the parked car at her place, so it's cozy the moment she sits down.
- **Warm outside (78°F or above):** **windows cracked a little, climate off** — fresh air, the way she likes it.
- **In-between:** climate on at her temperature, her **passenger vent aimed up toward her head**, her **vent fan on Low**.
- **Her love-songs mix:** every activation starts her Spotify playlist (shuffle on) — through *your* Spotify account on your active device. (Honesty note below.)
- **Freeway safety override:** above 55 mph the windows are **fully closed in every mode**. The warm-day window crack only ever happens parked or at low speed.
- **Only the passenger side is ever touched.** Your side is yours.

## It learns (on your computer only)

Girlfriend Mode records activations and the manual changes made afterwards — locally, in a file on your machine, never uploaded — and turns patterns into plain-English **suggestions**:

- *"You usually head to her place Fridays around 6 PM — want it pre-activated and the seat pre-warmed?"*
- *"On the last 3 cool trips her seat heater was changed from 2 to 3. Make 3 her default?"*
- *"The love-songs mix was skipped on the last 3 trips. Pick a different mix?"*
- Frequent shared destinations and weather-pattern mismatches surface the same way.

Suggestions **never** auto-apply and **never** command the car. Ask in chat ("any suggestions?") or run `tgmode suggestions`. Learning can be switched off in setup (`TGM_LEARNING_MODE=off`).

## Honesty box — what's real today, and what isn't

- **Real Fleet API commands used:** climate on/off, passenger temperature (`set_temps`), passenger seat heater (`remote_seat_heater_request`), windows vent/close (`window_control`).
- **Vent aim and fan speed are PROPOSED API.** Tesla's Fleet API exposes no airflow-direction command and no fan-speed command today. Girlfriend Mode models both in its planner, simulator, and demo — clearly labelled "proposed API — simulated" in every preview — and ships [API_PROPOSAL.md](API_PROPOSAL.md) proposing `set_airflow_direction` and `set_fan_speed`. The real car never receives them, and nothing in this README claims otherwise.
- **Music does NOT use the car's Spotify app.** Tesla's Fleet API cannot pick a playlist inside the car's own Spotify app (its media commands are play/pause/next/volume only). Playback goes through the Spotify Web API on **your** account, on your active Spotify device — in practice your phone, which is already connected to the car. If Spotify isn't connected, the preview says so in plain words and the rest of the plan still runs.

## How it activates

1. **Automatically** — navigation destination is her place (set up by name + street address, geocoded for you — nobody types latitude/longitude), or arrival at / departure from her place. The cool-weather seat pre-warm fires when you return to the parked car there.
2. **Manually** — `tgmode activate`, or via the chat endpoint: *"turn on girlfriend mode"*.
3. **Preview first, always** — `tgmode preview` shows exactly what would happen, in plain English, before anything real (dry-run honored everywhere).

## How it works

```
 6:05 PM  You navigate to her place (or Friday ~6 PM rolls around — it learned)
          → 52°F outside = cool mode
 6:05 PM  Climate on, her side 73°F, her vent fan Low (proposed, simulated)
 6:05 PM  Her love-songs mix starts on Spotify (your phone → the car)
 8:40 PM  Walking back to the parked car at her place
          → seat heater level 2 already on — the seat is cozy when she sits
```

**Expected API cost:** ~$0.10–0.35/month at typical use — a handful of commands per activation, no polling, no wake-ups to plan.

## Quickstart (for owners, not developers)

```bash
git clone https://github.com/rtmalikian/tesla-girlfriend-mode.git
cd tesla-girlfriend-mode
python3 -m venv .venv && .venv/bin/pip install -e .
tgmode setup        # plain-language questions — writes .env for you
tgmode simulate     # demo with a pretend car, pretend trips, pretend learning
tgmode preview --outside-temp 52 --returning   # dry run: exactly what would happen
tgmode auth         # sign in to Tesla once (opens a link)
tgmode serve        # start the AI chat server
```

Setup asks: her name (or just "girlfriend"), a starting style — **Runs cold (cozy) / Runs hot / Fresh-air fan / Custom** — her place by name + street address, the freeway speed, whether to play the love-songs mix (and which Spotify playlist — paste a link or leave the default "love songs mix" search), and whether to learn from trips together. Defaults everywhere; Enter accepts.

## Tesla developer setup

Create a free app at [developer.tesla.com](https://developer.tesla.com) (Client ID + Secret), with scopes `vehicle_device_data`, `vehicle_location`, and `vehicle_cmds`, then pair your car's virtual key per Tesla's Fleet API pairing docs. `tgmode auth` prints the authorization link.

## AI endpoints

The app exposes an OpenAI-compatible server, so any AI client (Open WebUI, Continue, your own scripts) can talk to it:

```bash
curl http://127.0.0.1:8644/v1/models

curl http://127.0.0.1:8644/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "tesla-girlfriend-mode",
  "messages": [{"role": "user", "content": "turn on girlfriend mode, outside temp 52"}]}'

curl http://127.0.0.1:8644/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "tesla-girlfriend-mode",
  "messages": [{"role": "user", "content": "any suggestions?"}]}'
```

- `GET /v1/models`, `POST /v1/chat/completions`, `POST /v1/embeddings` (local feature-hashing embeddings, dim 384 — also used for place-name similarity in the learning engine).
- Pluggable backend: `TGM_AI_BASE_URL` (default local Ollama `http://localhost:11434/v1`), `TGM_AI_API_KEY`, `TGM_AI_MODEL`, `TGM_AI_MODE` (`auto|always|never`). The deterministic rules + learning engine fully work with the backend off.
- LLM-emitted commands are allowlist-validated — only: `climate_start`, `climate_stop`, `set_passenger_temp`, `seat_heater`, `window_vent`, `window_close`, `vent_aim` (proposed), `set_fan_speed` (proposed), `play_love_mix`. An LLM can never unlock a door, start a charge, or touch the driver's side through this app.
- **Privacy:** vehicle and trip data are sent **only** to the backend *you* configure. With `TGM_AI_MODE=never`, nothing leaves your machine except Tesla API calls. The learning log lives in `~/.tgm/events.jsonl` on your computer, is git-ignored, and is never uploaded anywhere.

## .env reference

| Variable | Meaning |
|---|---|
| `TESLA_CLIENT_ID` / `TESLA_CLIENT_SECRET` | Your Tesla developer app credentials |
| `TGM_VEHICLES` | Cars as `nickname=VIN` pairs (VIN optional until pairing) |
| `TGM_PARTNER_NAME` | What to call her in messages (default `girlfriend`) |
| `TGM_PRESET` | `runs_cold` / `runs_hot` / `fresh_air` / `custom` |
| `TGM_PLACE_NAME` / `TGM_PLACE_ADDRESS` / `TGM_PLACE_LAT` / `TGM_PLACE_LON` | Her place — name + address; setup geocodes the coordinates |
| `TGM_COOL_BELOW_F` / `TGM_WARM_FROM_F` | Weather thresholds (default 65 / 78) |
| `TGM_COOL_PASSENGER_TEMP_F` / `TGM_MID_PASSENGER_TEMP_F` | Her passenger temperatures (73 / 72) |
| `TGM_SEAT_HEATER_LEVEL` | 0 (never) – 3 |
| `TGM_FAN_SPEED` | `low` / `medium` / `high` / `auto` — **proposed API**, simulated today |
| `TGM_WARM_WINDOWS_CRACK` | Crack windows on warm days (1/0) |
| `TGM_FREEWAY_SPEED_MPH` | Above this, windows always fully closed (55) |
| `TGM_MUSIC_ENABLED` | Play her love-songs mix on activation (1/0) |
| `TGM_SPOTIFY_PLAYLIST_URI` | Her playlist link/URI (blank = search) |
| `TGM_SPOTIFY_SEARCH_PHRASE` | Default search when no playlist is set (`love songs mix`) |
| `TGM_SPOTIFY_ACCESS_TOKEN` | Your Spotify token (your account; .env only) |
| `TGM_LEARNING_MODE` | `auto` / `off` — on-device trip learning |
| `TGM_AI_BASE_URL` / `TGM_AI_API_KEY` / `TGM_AI_MODEL` / `TGM_AI_MODE` | Pluggable LLM backend |
| `TGM_SERVER_PORT` / `TGM_SERVER_API_KEY` | Chat server (8644) + optional bearer key |
| `TGM_DRY_RUN` | 1 = plan and report, never command |

## FAQ

**Does it change my side of the car?** Never. Every command is passenger-scoped by design, and the allowlist has no driver-side commands at all.

**Is the seat pre-warm real?** Yes — seat heater and climate are real Fleet API commands. Vent aim and fan speed are the proposed-API parts (labelled everywhere), and the music plays via your Spotify account on your phone, not the car's Spotify app.

**What does it cost to run?** The app is free and MIT-licensed. Tesla Fleet API usage is roughly $0.10–0.35/month at typical activation counts — commands only, no polling, no wake-ups.

**Where does the learning data live?** In `~/.tgm/events.jsonl` on your own computer. It's never committed to git and never uploaded. Turn learning off any time in setup.

**Can I use it for a boyfriend / husband / partner?** Of course — the name, thresholds, temperatures, seat heater, fan, windows, and playlist are all just her-or-his profile settings. "Girlfriend Mode" is just the name on the tin.

**Does it work without any AI?** Yes. Rules plan, learning counts, suggestions phrase — all deterministic and offline. AI chat is optional garnish.

## License

MIT © Raphael Malikian. Part of the Tesla AI Series — open-source Tesla Fleet API apps with embedded OpenAI-compatible endpoints.
