"""Configuration for Tesla Girlfriend Mode. All settings come from the
environment (see .env.example). Run `tgmode setup` and answer a few
plain-language questions — it writes .env for you. .env is git-ignored so
secrets (and your partner's address) never leave your machine.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

FAN_SPEEDS = ("low", "medium", "high", "auto")


class ConfigError(Exception):
    pass


@dataclass
class VehicleConfig:
    name: str
    vin: str = ""   # may be blank: nickname-only cars get a VIN at pairing time


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    region: str = "na"
    redirect_uri: str = "http://localhost:8080/callback"
    token_file: str = "~/.tgm/tokens.json"
    vehicles: list[VehicleConfig] = field(default_factory=list)
    # The OpenAI-compatible server this app exposes.
    server_host: str = "127.0.0.1"
    server_port: int = 8644
    server_api_key: str = ""
    model_id: str = "tesla-girlfriend-mode"
    # Pluggable LLM backend (any OpenAI-compatible API; default: local Ollama).
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = ""
    ai_model: str = "llama3.1"
    ai_mode: str = "auto"             # auto | always | never
    ai_timeout_seconds: float = 20.0
    embedding_dim: int = 384
    dry_run: bool = False
    learning_mode: str = "auto"       # auto | off — on-device pattern learning
    data_dir: str = "~/.tgm"
    # Music on activation: her Spotify love-songs mix, via the OWNER's
    # Spotify account on their active device (usually their phone, which
    # is connected to the car). Tesla's Fleet API cannot pick a playlist
    # inside the car's own Spotify app — see README honesty note.
    music_enabled: bool = True
    spotify_playlist_uri: str = ""    # blank → search spotify_search_phrase
    spotify_search_phrase: str = "love songs mix"
    spotify_access_token: str = ""    # owner's own token; .env only, never committed
    # ---- Partner profile (the whole point of the app) -------------------
    partner_name: str = "girlfriend"
    preset: str = "runs_cold"
    # Her place, stored by name + geocoded coordinates (never typed by hand).
    place_name: str = ""
    place_address: str = ""
    place_lat: float = 0.0
    place_lon: float = 0.0
    place_radius_m: int = 300
    # Weather thresholds (°F).
    cool_below_f: int = 65            # below this: cozy mode
    warm_from_f: int = 78             # at/above this: fresh-air mode
    # Her passenger-side preferences.
    cool_passenger_temp_f: int = 73   # passenger temp on cool days
    mid_passenger_temp_f: int = 72    # passenger temp on in-between days
    seat_heater_level: int = 2        # 0 = never, 1-3
    fan_speed: str = "low"            # low|medium|high|auto (PROPOSED API)
    warm_windows_crack: bool = True   # crack the windows on warm days
    freeway_speed_mph: int = 55       # above this, windows always fully closed


def spotify_configured(settings: "Settings") -> bool:
    """Music can only play when the owner connected their Spotify account."""
    return bool(settings.spotify_access_token)


def _parse_vehicles(raw: str) -> list[VehicleConfig]:
    """Format: name=VIN,name2=VIN2, or bare nicknames (VIN filled in later)."""
    vehicles = []
    for idx, item in enumerate(raw.split(",")):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, vin = item.split("=", 1)
            vehicles.append(VehicleConfig(name=name.strip() or f"car-{idx + 1}",
                                          vin=vin.strip()))
        else:
            # A bare value is a nickname whose VIN gets added at pairing.
            vehicles.append(VehicleConfig(name=item, vin=""))
    if not vehicles:
        raise ConfigError("TGM_VEHICLES is empty — add at least one car nickname")
    return vehicles


def _int(env: dict, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a whole number, got {raw!r}") from exc


def _float(env: dict, key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _bool(env: dict, key: str, default: bool = False) -> bool:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings(env: dict | None = None) -> Settings:
    env = os.environ if env is None else env
    s = Settings()
    s.client_id = env.get("TESLA_CLIENT_ID", "")
    s.client_secret = env.get("TESLA_CLIENT_SECRET", "")
    s.region = env.get("TESLA_REGION", "na").strip().lower()
    if s.region not in ("na", "eu", "cn"):
        raise ConfigError(f"TESLA_REGION must be na|eu|cn, got {s.region!r}")
    s.redirect_uri = env.get("TESLA_REDIRECT_URI", s.redirect_uri)
    s.token_file = env.get("TGM_TOKEN_FILE", s.token_file)
    raw_vehicles = env.get("TGM_VEHICLES", "")
    if raw_vehicles.strip():
        s.vehicles = _parse_vehicles(raw_vehicles)
    s.server_host = env.get("TGM_SERVER_HOST", s.server_host)
    s.server_port = _int(env, "TGM_SERVER_PORT", s.server_port)
    s.server_api_key = env.get("TGM_SERVER_API_KEY", "")
    s.model_id = env.get("TGM_MODEL_ID", s.model_id)
    s.ai_base_url = env.get("TGM_AI_BASE_URL", s.ai_base_url).rstrip("/")
    s.ai_api_key = env.get("TGM_AI_API_KEY", "")
    s.ai_model = env.get("TGM_AI_MODEL", s.ai_model)
    s.ai_mode = env.get("TGM_AI_MODE", s.ai_mode).strip().lower()
    if s.ai_mode not in ("auto", "always", "never"):
        raise ConfigError(f"TGM_AI_MODE must be auto|always|never, got {s.ai_mode!r}")
    s.ai_timeout_seconds = _float(env, "TGM_AI_TIMEOUT_SECONDS", s.ai_timeout_seconds)
    s.embedding_dim = _int(env, "TGM_EMBEDDING_DIM", s.embedding_dim)
    if not (8 <= s.embedding_dim <= 4096):
        raise ConfigError("TGM_EMBEDDING_DIM must be between 8 and 4096")
    s.dry_run = _bool(env, "TGM_DRY_RUN")
    s.learning_mode = env.get("TGM_LEARNING_MODE", s.learning_mode).strip().lower()
    if s.learning_mode not in ("auto", "off"):
        raise ConfigError(
            f"TGM_LEARNING_MODE must be auto|off, got {s.learning_mode!r}")
    s.data_dir = env.get("TGM_DATA_DIR", s.data_dir)
    s.music_enabled = _bool(env, "TGM_MUSIC_ENABLED", True)
    s.spotify_playlist_uri = env.get("TGM_SPOTIFY_PLAYLIST_URI", "").strip()
    s.spotify_search_phrase = env.get(
        "TGM_SPOTIFY_SEARCH_PHRASE", s.spotify_search_phrase).strip() \
        or s.spotify_search_phrase
    s.spotify_access_token = env.get("TGM_SPOTIFY_ACCESS_TOKEN", "")
    # Partner profile.
    s.partner_name = env.get("TGM_PARTNER_NAME", s.partner_name).strip() or s.partner_name
    s.preset = env.get("TGM_PRESET", s.preset).strip().lower() or s.preset
    s.place_name = env.get("TGM_PLACE_NAME", "")
    s.place_address = env.get("TGM_PLACE_ADDRESS", "")
    s.place_lat = _float(env, "TGM_PLACE_LAT", 0.0)
    s.place_lon = _float(env, "TGM_PLACE_LON", 0.0)
    s.place_radius_m = _int(env, "TGM_PLACE_RADIUS_M", s.place_radius_m)
    s.cool_below_f = _int(env, "TGM_COOL_BELOW_F", s.cool_below_f)
    s.warm_from_f = _int(env, "TGM_WARM_FROM_F", s.warm_from_f)
    if not s.cool_below_f < s.warm_from_f:
        raise ConfigError(
            f"The 'cool below' temperature ({s.cool_below_f}°F) must be lower "
            f"than the 'warm from' temperature ({s.warm_from_f}°F). "
            "Re-run `tgmode setup` and pick two temperatures with a gap "
            "between them.")
    s.cool_passenger_temp_f = _int(env, "TGM_COOL_PASSENGER_TEMP_F",
                                   s.cool_passenger_temp_f)
    s.mid_passenger_temp_f = _int(env, "TGM_MID_PASSENGER_TEMP_F",
                                  s.mid_passenger_temp_f)
    for key, val in (("TGM_COOL_PASSENGER_TEMP_F", s.cool_passenger_temp_f),
                     ("TGM_MID_PASSENGER_TEMP_F", s.mid_passenger_temp_f)):
        if not (50 <= val <= 85):
            raise ConfigError(f"{key} must be between 50 and 85, got {val}")
    s.seat_heater_level = _int(env, "TGM_SEAT_HEATER_LEVEL", s.seat_heater_level)
    if not (0 <= s.seat_heater_level <= 3):
        raise ConfigError("TGM_SEAT_HEATER_LEVEL must be 0 (never) to 3")
    s.fan_speed = env.get("TGM_FAN_SPEED", s.fan_speed).strip().lower()
    if s.fan_speed not in FAN_SPEEDS:
        raise ConfigError(
            f"TGM_FAN_SPEED must be one of {'/'.join(FAN_SPEEDS)}, "
            f"got {s.fan_speed!r}")
    s.warm_windows_crack = _bool(env, "TGM_WARM_WINDOWS_CRACK", True)
    s.freeway_speed_mph = _int(env, "TGM_FREEWAY_SPEED_MPH", s.freeway_speed_mph)
    if not (20 <= s.freeway_speed_mph <= 90):
        raise ConfigError("TGM_FREEWAY_SPEED_MPH must be between 20 and 90")
    return s


# Starting presets offered as numbered choices in the setup wizard.
PRESETS = {
    "runs_cold": {
        "label": "Runs cold (cozy)",
        "cool_below_f": 65, "warm_from_f": 78,
        "cool_passenger_temp_f": 73, "mid_passenger_temp_f": 72,
        "seat_heater_level": 2, "fan_speed": "low",
        "warm_windows_crack": True,
    },
    "runs_hot": {
        "label": "Runs hot",
        "cool_below_f": 60, "warm_from_f": 75,
        "cool_passenger_temp_f": 70, "mid_passenger_temp_f": 68,
        "seat_heater_level": 0, "fan_speed": "auto",
        "warm_windows_crack": True,
    },
    "fresh_air": {
        "label": "Fresh-air fan",
        "cool_below_f": 62, "warm_from_f": 72,
        "cool_passenger_temp_f": 72, "mid_passenger_temp_f": 70,
        "seat_heater_level": 1, "fan_speed": "medium",
        "warm_windows_crack": True,
    },
}
