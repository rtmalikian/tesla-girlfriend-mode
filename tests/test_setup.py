"""The setup wizard must produce a config the app can load — no developer
knowledge required from the (scripted) user."""
from tesla_girlfriend_mode.config import load_settings
from tesla_girlfriend_mode.setup import run_setup


def _scripted(answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def _parse_env(path):
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    return env


def _fake_geocoder(address):
    return (34.0522, -118.2437)


def test_wizard_runs_cold_preset_with_geocoded_place(tmp_path):
    answers = [
        "cid-123", "secret-xyz",                    # step 1
        "Model Y", "", "",                          # step 2: one car, blank VIN
        "", "1",                                    # step 3: default name, Runs cold
        "",                                         # freeway default 55
        "y", "", "",                                # music yes, search default, no token yet
        "", "123 Palm Ave, Los Angeles, CA",        # step 4: her place + address
        "1", "2",                                   # step 5: learning on, Ollama
        "", "",                                     # step 6: default port, no password
    ]
    env_file = tmp_path / ".env"
    run_setup(input_fn=_scripted(answers), out=lambda *a: None,
              env_path=str(env_file), geocoder=_fake_geocoder)
    s = load_settings(_parse_env(env_file))
    assert s.partner_name == "girlfriend"
    assert s.preset == "runs_cold"
    assert s.cool_below_f == 65 and s.warm_from_f == 78
    assert s.cool_passenger_temp_f == 73 and s.seat_heater_level == 2
    assert s.fan_speed == "low"
    assert s.music_enabled is True
    assert s.spotify_search_phrase == "love songs mix"
    assert s.place_name == "her place"
    assert abs(s.place_lat - 34.0522) < 1e-4
    assert s.learning_mode == "auto"
    assert s.server_port == 8644


def test_wizard_custom_profile_no_music(tmp_path):
    answers = [
        "cid", "sec",
        "Solo", "", "",
        "Anna", "4",                                # custom profile
        "60", "76", "74", "71", "3",                # thresholds, temps, seat
        "3",                                        # fan: high
        "y",                                        # windows crack yes
        "60",                                       # freeway 60
        "n",                                        # music off
        "", "456 Oak St, Smalltown",                # place; geocoder finds nothing
        "2", "1",                                   # learning off, no AI
        "", "",
    ]
    env_file = tmp_path / ".env"
    run_setup(input_fn=_scripted(answers), out=lambda *a: None,
              env_path=str(env_file), geocoder=lambda a: None)
    s = load_settings(_parse_env(env_file))
    assert s.partner_name == "Anna" and s.preset == "custom"
    assert s.cool_below_f == 60 and s.warm_from_f == 76
    assert s.seat_heater_level == 3 and s.fan_speed == "high"
    assert s.freeway_speed_mph == 60
    assert s.music_enabled is False
    assert s.place_lat == 0.0  # address not found — manual mode still works
    assert s.learning_mode == "off" and s.ai_mode == "never"


def test_wizard_keeps_existing_when_declined(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TGM_VEHICLES=Keep=\n")
    run_setup(input_fn=_scripted(["n"]), out=lambda *a: None,
              env_path=str(env_file), geocoder=_fake_geocoder)
    assert "Keep" in env_file.read_text()
