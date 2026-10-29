import json
from datetime import datetime

from tesla_girlfriend_mode.config import Settings, VehicleConfig
from tesla_girlfriend_mode.learning import EventLog
from tesla_girlfriend_mode.llm import extract_command
from tesla_girlfriend_mode.service import GirlfriendModeService
from tesla_girlfriend_mode.simulator import (
    FakeSpotifyClient, FakeTeslaClient, demo_vehicles, seed_demo_history)

FRIDAY = datetime(2026, 10, 30, 17, 30)


def _service(tmp_path, fake=None, spotify=None, **settings_kw):
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                        ai_mode="never", **settings_kw)
    log = EventLog(tmp_path / "events.jsonl")
    return GirlfriendModeService(
        settings,
        client_factory=(lambda: fake) if fake is not None else None,
        llm_factory=lambda: None,
        now_fn=lambda: FRIDAY,
        event_log=log,
        spotify_factory=(lambda: spotify) if spotify is not None else None), log


def _chat(service, text):
    resp = service.chat_completions(
        {"messages": [{"role": "user", "content": text}]})
    return resp["choices"][0]["message"]["content"]


def test_models_shape(tmp_path):
    service, _ = _service(tmp_path)
    models = service.models_list()
    assert models["object"] == "list"
    assert models["data"][0]["id"] == "tesla-girlfriend-mode"


def test_chat_shape_and_activation_cool(tmp_path):
    service, log = _service(tmp_path, fake=FakeTeslaClient(demo_vehicles()),
                            spotify=FakeSpotifyClient())
    resp = service.chat_completions({"messages": [
        {"role": "user", "content": "turn on girlfriend mode, outside temp 52"}]})
    assert resp["object"] == "chat.completion"
    text = resp["choices"][0]["message"]["content"]
    assert "seat heater" in text.lower()
    # activation was recorded for learning
    assert any(e["type"] == "activation" for e in log.load())


def test_chat_activation_executes_on_fake_car(tmp_path):
    fake = FakeTeslaClient(demo_vehicles())
    service, _ = _service(tmp_path, fake=fake, spotify=FakeSpotifyClient())
    _chat(service, "turn on girlfriend mode, outside temp 52")
    car = fake.vehicles["VINY"]
    assert car.climate_on is True and car.seat_heater_level == 2
    names = [n for n, _ in fake.command_log]
    assert "climate_start" in names and "seat_heater" in names
    # proposed commands never reach the car client
    assert "vent_aim(simulated)" not in names
    assert "set_fan_speed(simulated)" not in names


def test_chat_music_plays_and_failure_never_blocks(tmp_path):
    spotify = FakeSpotifyClient()
    fake = FakeTeslaClient(demo_vehicles())
    service, _ = _service(tmp_path, fake=fake, spotify=spotify)
    text = _chat(service, "turn on girlfriend mode, outside temp 84")
    assert spotify.now_playing  # mix started even in warm mode
    assert fake.vehicles["VINY"].windows == "vented"  # comfort still ran

    class BrokenSpotify:
        def play_mix(self, uri="", phrase="love songs mix"):
            from tesla_girlfriend_mode.spotify_client import SpotifyError
            raise SpotifyError("No active Spotify device found")

    fake2 = FakeTeslaClient(demo_vehicles())
    service2, _ = _service(tmp_path, fake=fake2, spotify=BrokenSpotify())
    text2 = _chat(service2, "turn on girlfriend mode, outside temp 84")
    assert "skipped" in text2
    assert fake2.vehicles["VINY"].windows == "vented"  # still ran


def test_chat_music_unconfigured_human_note(tmp_path):
    fake = FakeTeslaClient(demo_vehicles())
    service, _ = _service(tmp_path, fake=fake)  # no spotify, no token
    text = _chat(service, "turn on girlfriend mode, outside temp 52")
    assert "Spotify isn't connected yet" in text
    assert fake.vehicles["VINY"].climate_on is True


def test_chat_suggestions(tmp_path):
    service, log = _service(tmp_path)
    seed_demo_history(log)
    text = _chat(service, "any suggestions?")
    assert "Fridays" in text and "seat heater" in text


def test_embeddings_shape(tmp_path):
    service, _ = _service(tmp_path)
    emb = service.embeddings({"input": ["her place", "the beach"]})
    assert emb["object"] == "list" and len(emb["data"]) == 2
    assert len(emb["data"][0]["embedding"]) == 384


class _FakeLlm:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, context, user_message):
        return self.reply


def test_llm_command_allowlist_enforced(tmp_path):
    fake = FakeTeslaClient(demo_vehicles())
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")])
    log = EventLog(tmp_path / "e.jsonl")
    block = ('```json\n{"command": "unlock_doors", "vehicle": "Model Y"}'
             '\n```')
    service = GirlfriendModeService(
        settings, client_factory=lambda: fake,
        llm_factory=lambda: _FakeLlm(block), event_log=log)
    _chat(service, "do something for me please friend")
    assert fake.command_log == []  # dropped, never executed


def test_llm_allowlisted_command_executes(tmp_path):
    fake = FakeTeslaClient(demo_vehicles())
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")])
    block = ('```json\n{"command": "climate_start", "vehicle": "Model Y"}'
             '\n```')
    service = GirlfriendModeService(
        settings, client_factory=lambda: fake,
        llm_factory=lambda: _FakeLlm(block),
        event_log=EventLog(tmp_path / "e.jsonl"))
    text = _chat(service, "start the climate please friend")
    assert "Done" in text
    assert ("climate_start", "VINY") in fake.command_log


def test_extract_command_music():
    ok = extract_command('```json\n{"command": "play_love_mix", '
                         '"vehicle": "Model Y"}\n```')
    assert ok and ok["command"] == "play_love_mix"
    bad = extract_command('```json\n{"command": "play_rock_anthems", '
                          '"vehicle": "Model Y"}\n```')
    assert bad is None
    bad2 = extract_command('```json\n{"command": "set_fan_speed", '
                           '"vehicle": ""}\n```')
    assert bad2 is None


def test_dry_run_sends_nothing(tmp_path):
    fake = FakeTeslaClient(demo_vehicles())
    service, log = _service(tmp_path, fake=fake, spotify=FakeSpotifyClient())
    service.settings.dry_run = True
    outcome = service.activate({"outside_temp_f": 52.0})
    assert fake.command_log == []
    assert all(r["status"].startswith(("dry run", "simulated"))
               for r in outcome["results"])
    assert log.load() == []  # dry runs are not learned from


def test_music_skip_recorded_for_learning(tmp_path):
    service, log = _service(tmp_path)
    for _ in range(3):
        service.record_music_skip()
    assert any("love-songs mix was skipped" in s["text"]
               for s in service.suggestions())
