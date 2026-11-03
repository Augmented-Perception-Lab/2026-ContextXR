"""CLI smoke tests and live-mode LLM caching with a fake client (no network, no API key)."""

import json
from pathlib import Path

from contextxr import load_minexrpp
from contextxr.cli import main
from contextxr.methods.llm import LLMSuggester
from contextxr.methods.llm_cache import LLMCache, LLMResponse

TOY = Path(__file__).parent / "data" / "toy"


def test_cli_validate_and_methods(capsys):
    assert main(["validate", str(TOY)]) == 0
    assert "OK" in capsys.readouterr().out
    assert main(["methods"]) == 0
    assert "few_shot_llm[user+env]" in capsys.readouterr().out


def test_cli_run_writes_results(tmp_path, capsys):
    out = tmp_path / "pop.jsonl"
    assert main(["run", "--task", "initial", "--method", "popularity", "--out", str(out)]) == 0
    lines = out.read_text().splitlines()
    assert json.loads(lines[0])["type"] == "run" and json.loads(lines[-1])["type"] == "summary"
    assert "popularity" in capsys.readouterr().out


def test_cli_factors(capsys):
    assert main(["run", "--task", "factors"]) == 0
    assert "user 47, task 14, environment 12, mixed 8, none 20" in capsys.readouterr().out


def test_cli_cache_miss_is_an_error(capsys):
    assert main(["run", "--task", "initial", "--method", "zero_shot_llm", "--data", str(TOY), "--no-cv"]) == 3
    assert "No cached LLM response" in capsys.readouterr().err


def test_cli_export_web_is_a_stub():
    assert main(["export-web"]) == 2


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        recs = [{"facet_id": "spotify.view_now_playing", "tier": "primary", "confidence": 0.9, "reason": "music"}]
        return LLMResponse(text="```json\n" + json.dumps({"summary": "s", "recommendations": recs}) + "\n```")


def test_live_mode_records_then_replays(tmp_path):
    ds = load_minexrpp()
    scenario = ds.scenarios["P04_LivingRoom_Relaxing"]
    client = FakeClient()
    live = LLMSuggester(ds, "user", cache=LLMCache(tmp_path, mode="live", client=client))
    assert live.suggest(scenario.context, ds.catalog, None, 10) == ["spotify.view_now_playing"]
    assert live.suggest(scenario.context, ds.catalog, None, 10) == ["spotify.view_now_playing"]
    assert client.calls == 1  # second call served from the cache
    replay = LLMSuggester(ds, "user", cache=LLMCache(tmp_path))  # fresh cache object, replay mode
    assert replay.suggest(scenario.context, ds.catalog, None, 10) == ["spotify.view_now_playing"]
    files = list(tmp_path.rglob("*.jsonl"))
    assert len(files) == 1 and len(list((tmp_path / "catalogs").iterdir())) == 1
