from datetime import datetime

from tesla_girlfriend_mode.config import Settings
from tesla_girlfriend_mode.learning import (
    EventLog, build_suggestions, extract_patterns, similar_place)
from tesla_girlfriend_mode.simulator import seed_demo_history


def _seeded_log(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    seed_demo_history(log)
    return log


def test_recurring_together_time_detected(tmp_path):
    patterns = extract_patterns(_seeded_log(tmp_path).load())
    fridays = [r for r in patterns["recurring_times"] if r["weekday"] == 4]
    assert fridays and fridays[0]["destination"] == "her place"
    assert fridays[0]["typical_hour"] == 18
    assert fridays[0]["trips"] == 4


def test_frequent_destination_detected(tmp_path):
    patterns = extract_patterns(_seeded_log(tmp_path).load())
    dests = {f["destination"] for f in patterns["frequent_destinations"]}
    assert "the beach" in dests and "her place" in dests


def test_override_suggestion_needs_repeats(tmp_path):
    log = EventLog(tmp_path / "e.jsonl")
    # Two identical overrides: below threshold — no repeated-override pattern.
    for day in (2, 9):
        log.record_override(setting="seat_heater", from_value=2, to_value=3,
                            when=datetime(2026, 10, day, 18, 0))
    patterns = extract_patterns(log.load())
    assert patterns["repeated_overrides"] == []
    # Third one: pattern fires.
    log.record_override(setting="seat_heater", from_value=2, to_value=3,
                        when=datetime(2026, 10, 16, 18, 0))
    patterns = extract_patterns(log.load())
    assert patterns["repeated_overrides"][0]["trips"] == 3


def test_suggestions_from_seeded_history_on_friday(tmp_path):
    settings = Settings()
    patterns = extract_patterns(_seeded_log(tmp_path).load())
    friday = datetime(2026, 10, 30, 17, 30)  # a Friday
    suggestions = build_suggestions(settings, patterns, now=friday,
                                    outside_temp_f=54.0)
    kinds = {s["kind"] for s in suggestions}
    assert "recurring_time" in kinds
    assert "override_learning" in kinds
    seat = next(s for s in suggestions if "seat heater" in s["text"])
    assert "Suggestion only" in seat["text"]


def test_music_skip_suggestion(tmp_path):
    settings = Settings()
    patterns = extract_patterns(_seeded_log(tmp_path).load())
    suggestions = build_suggestions(settings, patterns,
                                    now=datetime(2026, 10, 31, 12, 0))
    assert any("love-songs mix was skipped" in s["text"] for s in suggestions)


def test_learning_off_means_no_suggestions(tmp_path):
    settings = Settings()
    settings.learning_mode = "off"
    patterns = extract_patterns(_seeded_log(tmp_path).load())
    assert build_suggestions(settings, patterns,
                             now=datetime(2026, 10, 30, 17, 30)) == []


def test_no_history_no_suggestions():
    patterns = extract_patterns([])
    assert build_suggestions(Settings(), patterns,
                             now=datetime(2026, 10, 30, 17, 30)) == []


def test_similar_place_matching():
    assert similar_place("her place", ["her place", "the beach"]) == "her place"
    assert similar_place("the beach!", ["the beach"]) is not None
    assert similar_place("airport terminal 4", ["the beach"]) is None


def test_log_roundtrip_and_torn_line(tmp_path):
    log = EventLog(tmp_path / "e.jsonl")
    log.record_activation(trigger="manual", destination="her place",
                          mode="cool", outside_temp_f=50.0,
                          when=datetime(2026, 10, 30, 18, 0))
    (tmp_path / "e.jsonl").open("a").write("{torn json\n")
    events = log.load()
    assert len(events) == 1 and events[0]["mode"] == "cool"
