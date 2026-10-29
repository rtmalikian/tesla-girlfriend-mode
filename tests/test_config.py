import pytest

from tesla_girlfriend_mode.config import ConfigError, load_settings

BASE = {"TGM_VEHICLES": "Model Y=VINY"}


def _load(**overrides):
    env = dict(BASE)
    env.update(overrides)
    return load_settings(env)


def test_defaults_are_raphaels_girlfriends_profile():
    s = _load()
    assert s.partner_name == "girlfriend"
    assert s.cool_below_f == 65 and s.warm_from_f == 78
    assert s.cool_passenger_temp_f == 73
    assert s.seat_heater_level == 2
    assert s.fan_speed == "low"
    assert s.warm_windows_crack is True
    assert s.freeway_speed_mph == 55
    assert s.learning_mode == "auto"
    assert s.ai_base_url == "http://localhost:11434/v1"
    assert s.model_id == "tesla-girlfriend-mode"
    assert s.server_port == 8644


def test_env_overrides():
    s = _load(TGM_COOL_BELOW_F="60", TGM_WARM_FROM_F="80",
              TGM_FAN_SPEED="high", TGM_SEAT_HEATER_LEVEL="3",
              TGM_LEARNING_MODE="off", TGM_PARTNER_NAME="Anna",
              TGM_WARM_WINDOWS_CRACK="0")
    assert (s.cool_below_f, s.warm_from_f) == (60, 80)
    assert s.fan_speed == "high" and s.seat_heater_level == 3
    assert s.learning_mode == "off" and s.partner_name == "Anna"
    assert s.warm_windows_crack is False


def test_thresholds_must_have_a_gap():
    with pytest.raises(ConfigError):
        _load(TGM_COOL_BELOW_F="78", TGM_WARM_FROM_F="78")
    with pytest.raises(ConfigError):
        _load(TGM_COOL_BELOW_F="80", TGM_WARM_FROM_F="70")


def test_fan_speed_validated():
    with pytest.raises(ConfigError):
        _load(TGM_FAN_SPEED="turbo")


def test_seat_heater_range():
    with pytest.raises(ConfigError):
        _load(TGM_SEAT_HEATER_LEVEL="4")


def test_learning_mode_validated():
    with pytest.raises(ConfigError):
        _load(TGM_LEARNING_MODE="sometimes")


def test_ai_mode_validated():
    with pytest.raises(ConfigError):
        _load(TGM_AI_MODE="maybe")


def test_vehicles_nickname_only_ok():
    s = load_settings({"TGM_VEHICLES": "Model Y"})
    assert s.vehicles[0].name == "Model Y" and s.vehicles[0].vin == ""


def test_music_defaults_and_overrides():
    s = _load()
    assert s.music_enabled is True
    assert s.spotify_playlist_uri == ""
    assert s.spotify_search_phrase == "love songs mix"
    s2 = _load(TGM_MUSIC_ENABLED="0",
               TGM_SPOTIFY_PLAYLIST_URI="spotify:playlist:abc123")
    assert s2.music_enabled is False
    assert s2.spotify_playlist_uri == "spotify:playlist:abc123"


def test_planner_music_step_all_modes_and_disabled():
    from tesla_girlfriend_mode.config import Settings
    from tesla_girlfriend_mode.planner import plan_girlfriend_mode
    for temp in (52.0, 71.0, 84.0):
        plan = plan_girlfriend_mode(Settings(), temp)
        music = [c for c in plan["commands"]
                 if c["command"] == "play_love_mix"]
        assert len(music) == 1
        assert music[0]["proposed"] is False
        assert music[0]["provider"] == "spotify"
    off = Settings()
    off.music_enabled = False
    for temp in (52.0, 71.0, 84.0):
        plan = plan_girlfriend_mode(off, temp)
        assert "play_love_mix" not in [c["command"] for c in plan["commands"]]


def test_place_coordinates_parse():
    s = _load(TGM_PLACE_LAT="34.0522", TGM_PLACE_LON="-118.2437",
              TGM_PLACE_NAME="her place")
    assert s.place_lat == pytest.approx(34.0522)
    assert s.place_lon == pytest.approx(-118.2437)
