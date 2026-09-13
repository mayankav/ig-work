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


def test_calls_are_counted_so_telegram_can_say_what_is_left(monkeypatch):
    from datetime import datetime, timezone
    from suresilly import telegram
    keys = {"GEMINI_API_KEY": "g1", "GEMINI_API_KEY_2": "g2", "GROQ_API_KEY": "q"}
    monkeypatch.setattr(llm, "key", lambda name: keys.get(name, ""))  # not the real .env.local
    assert llm.left_today() == {} and telegram.tank() == ""

    daily = '{"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}]}}'
    llm._count("gemini-3.8-flash", "g1", Reply(200, "{}"))
    llm._count("gemini-3.8-flash", "g1", Reply(200, "{}"))
    llm._count("gemini-3.8-flash", "g2", Reply(429, daily))
    groq = Reply(200, "{}")
    groq.headers = {"x-ratelimit-remaining-requests": "998", "x-ratelimit-limit-requests": "1000"}
    llm._count("openai/gpt-oss-120b", "q", groq)

    left = llm.left_today()
    # 3 models x 2 keys = 6 allowances of 20. Key 1 used 2 on one model; key 2 is empty on that model.
    assert (left["gemini_total"], left["gemini_left"]) == (120, 120 - 2 - 20)
    assert (left["groq_left"], left["groq_total"]) == (998, 1000)
    assert left["gemini_refill"] in ("12:30", "13:30")  # midnight Pacific, summer or winter
    line = telegram.tank()
    assert "Gemini 98 of 120 calls · Groq (backup) 998 of 1,000" in line and "refills at" in line
    saved = open(llm.USAGE).read()
    assert "key 1" in saved and '"g1"' not in saved and '"g2"' not in saved  # labels only, never the keys

    tomorrow = datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert llm.left_today(tomorrow)["gemini_left"] == 120  # a new Pacific day starts full


def test_tank_warns_when_gemini_is_low_or_empty(monkeypatch):
    from suresilly import telegram
    monkeypatch.setattr(llm, "left_today", lambda: {"gemini_left": 0, "gemini_total": 180, "gemini_refill": "12:30"})
    assert "used up" in telegram.tank()
    monkeypatch.setattr(llm, "left_today", lambda: {"gemini_left": 8, "gemini_total": 180, "gemini_refill": "12:30"})
    assert "running low" in telegram.tank()
