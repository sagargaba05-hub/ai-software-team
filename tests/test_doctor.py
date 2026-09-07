import json

from ai_team.config import Settings
from ai_team.doctor import Check, _route_probe, format_doctor


def test_human_and_json_doctor_use_same_typed_statuses():
    checks = [Check("required", "PASS", "ok", True, "time"), Check("optional", "NOT_CONFIGURED", "off", False, "time")]
    human = format_doctor(checks)
    structured = json.loads(format_doctor(checks, True))
    assert "PASS  required" in human and "OVERALL: PASS" in human
    assert [item["status"] for item in structured] == ["PASS", "NOT_CONFIGURED"]


def test_route_probe_rejects_wrong_route_and_empty(monkeypatch):
    settings = Settings(codex_enabled=False)
    monkeypatch.setattr("ai_team.doctor._request_json", lambda *a, **k: {"model": "gpt-oss:20b", "choices": [{"message": {"content": "ok"}}]})
    assert _route_probe(settings, "developer", "qwen3-coder:30b").status == "FAIL"
    monkeypatch.setattr("ai_team.doctor._request_json", lambda *a, **k: {"model": "qwen3-coder:30b", "choices": [{"message": {"content": ""}}]})
    assert _route_probe(settings, "developer", "qwen3-coder:30b").status == "FAIL"
