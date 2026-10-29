from tesla_girlfriend_mode.config import Settings
from tesla_girlfriend_mode.planner import (
    ALL_COMMANDS, PROPOSED_COMMANDS, at_her_place, plan_girlfriend_mode)


def _plan(temp, speed=0, parked=True, returning=False, settings=None):
    return plan_girlfriend_mode(settings or Settings(),
                                temp, speed_mph=speed, parked=parked,
                                returning_to_car=returning)


def _names(plan):
    return [c["command"] for c in plan["commands"]]


def test_cool_day_cozy_plan():
    plan = _plan(52.0, returning=True)
    assert plan["mode"] == "cool"
    assert "climate_start" in _names(plan)
    assert "seat_heater" in _names(plan)
    seat = next(c for c in plan["commands"] if c["command"] == "seat_heater")
    assert seat["params"]["level"] == 2
    temp = next(c for c in plan["commands"]
                if c["command"] == "set_passenger_temp")
    assert temp["params"]["passenger_temp_f"] == 73


def test_cool_boundary_exactly_at_threshold_is_in_between():
    plan = _plan(65.0)  # cool is strictly *below* 65
    assert plan["mode"] == "in_between"


def test_just_below_threshold_is_cool():
    assert _plan(64.9)["mode"] == "cool"


def test_warm_boundary_exactly_at_threshold_is_warm():
    plan = _plan(78.0)
    assert plan["mode"] == "warm"


def test_warm_parked_vents_windows_climate_off():
    plan = _plan(84.0, parked=True)
    assert "climate_stop" in _names(plan)
    assert "window_vent" in _names(plan)
    assert "climate_start" not in _names(plan)


def test_warm_low_speed_driving_still_vents():
    plan = _plan(84.0, speed=30, parked=False)
    assert "window_vent" in _names(plan)


def test_freeway_override_warm_no_vent_windows_closed():
    plan = _plan(84.0, speed=68, parked=False)
    assert plan["highway"] is True
    assert "window_vent" not in _names(plan)
    assert "window_close" in _names(plan)


def test_freeway_override_applies_in_every_mode():
    for temp in (40.0, 71.0, 90.0):
        plan = _plan(temp, speed=70, parked=False)
        assert "window_close" in _names(plan)
        assert "window_vent" not in _names(plan)


def test_exactly_at_freeway_threshold_is_not_highway():
    plan = _plan(84.0, speed=55, parked=False)  # override is strictly above
    assert plan["highway"] is False
    assert "window_vent" in _names(plan)


def test_in_between_vent_aim_up_and_proposed():
    plan = _plan(71.0)
    assert plan["mode"] == "in_between"
    aim = next(c for c in plan["commands"] if c["command"] == "vent_aim")
    assert aim["params"]["direction"] == "up"
    assert aim["proposed"] is True


def test_fan_speed_in_climate_on_modes_only():
    for temp in (52.0, 71.0):  # cool + in-between: climate running
        fan = next(c for c in _plan(temp)["commands"]
                   if c["command"] == "set_fan_speed")
        assert fan["params"]["fan_speed"] == "low"
        assert fan["proposed"] is True
    warm = _plan(84.0)  # climate off → no fan command at all
    assert "set_fan_speed" not in _names(warm)


def test_proposed_flags_match_proposed_set():
    for temp in (52.0, 71.0, 84.0):
        for c in _plan(temp, speed=70)["commands"]:
            assert c["proposed"] == (c["command"] in PROPOSED_COMMANDS)


def test_only_allowlisted_passenger_commands_ever():
    for temp in (30.0, 65.0, 71.0, 78.0, 100.0):
        for speed in (0, 30, 80):
            plan = _plan(temp, speed=speed, parked=speed == 0)
            assert set(_names(plan)) <= ALL_COMMANDS
            for c in plan["commands"]:
                assert "driver" not in str(c["params"]).lower()


def test_seat_heater_zero_means_never():
    s = Settings()
    s.seat_heater_level = 0
    assert "seat_heater" not in _names(_plan(40.0, settings=s))


def test_windows_crack_disabled():
    s = Settings()
    s.warm_windows_crack = False
    plan = _plan(84.0, settings=s)
    assert "window_vent" not in _names(plan)
    assert "climate_stop" in _names(plan)


def test_unknown_temperature_uses_in_between_and_says_so():
    plan = _plan(None)
    assert plan["mode"] == "in_between"
    assert any("unknown" in n.lower() for n in plan["notes"])


def test_at_her_place_geofence():
    s = Settings()
    s.place_lat, s.place_lon, s.place_radius_m = 34.0, -118.0, 300
    assert at_her_place(s, 34.0, -118.0) is True
    assert at_her_place(s, 34.1, -118.0) is False
    assert at_her_place(s, None, None) is False
