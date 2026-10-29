"""End-to-end: the demo timeline asserts the core invariants —
cool → seat heater + climate on; warm parked → windows vented + climate
off; freeway → windows closed; music plays; suggestions are generated."""
from tesla_girlfriend_mode.simulator import run_demo


def test_core_invariants():
    report = run_demo()
    assert report["all_invariants_ok"] is True
    for key, ok in report["invariants"].items():
        assert ok, key
    assert len(report["scenarios"]) == 4


def test_scenario_states():
    report = run_demo()
    cool, warm_parked, warm_freeway, mild = report["scenarios"]
    assert cool["car"]["climate_on"] and cool["car"]["seat_heater_level"] == 2
    assert warm_parked["car"]["windows"] == "vented"
    assert not warm_parked["car"]["climate_on"]
    assert warm_freeway["car"]["windows"] == "closed"
    assert mild["car"]["vent_aim"] == "up"       # proposed, simulated
    assert mild["car"]["fan_speed"] == "low"     # proposed, simulated


def test_music_in_every_scenario():
    report = run_demo()
    assert all(sc["now_playing"] for sc in report["scenarios"])


def test_learning_demo_suggestions():
    report = run_demo()
    texts = " ".join(s["text"] for s in report["suggestions"])
    assert "Fridays" in texts
    assert "seat heater" in texts


def test_cost_line_present():
    report = run_demo()
    assert report["commands_per_day"] > 0
    assert report["estimated_monthly_cost_usd"] < 1.0
