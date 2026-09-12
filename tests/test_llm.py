import json

from suresilly import llm


class Reply:
    def __init__(self, status, text):
        self.status_code, self.text, self.headers = status, text, {}

    def json(self):
        return json.loads(self.text)


def test_a_used_up_daily_allowance_moves_to_the_next_key_without_waiting(monkeypatch):
    gemini_daily = ('{"error": {"code": 429, "details": [{"violations": [{"quotaId": '
                    '"GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]}]}}')
    calls, naps = [], []

    def spent(model, key, system, user, temperature):
        calls.append(key)
        return Reply(429, gemini_daily)

    def fresh(model, key, system, user, temperature):
        calls.append(key)
        return Reply(200, '{"ok": true}')

    monkeypatch.setattr(llm, "routes", lambda: [("m", "key-1", spent, None), ("m", "key-2", fresh, json.dumps)])
    monkeypatch.setattr(llm.time, "sleep", naps.append)
    assert llm.chat_json("s", "u") == ({"ok": True}, "m")
    assert calls == ["key-1", "key-2"] and naps == []
