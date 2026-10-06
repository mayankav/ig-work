import subprocess
import threading

import pytest

from suresilly import staircase as SC


class Done:
    def __init__(self, out="", code=0, err=""):
        self.stdout, self.returncode, self.stderr = out, code, err


def runner(outputs, seen=None):
    def run(cmd, **k):
        if seen is not None:
            seen.append((cmd, k))
        out = outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out
    return run


def test_parse_reads_json_from_fences_and_noise_and_flags_the_rest():
    assert SC.parse('> build\n```json\n{"a": 1}\n```') == {"a": 1}
    assert SC.parse('Here you go: {"a": 2} thanks')["a"] == 2
    assert "_bad_json" in SC.parse("no json at all")


def test_flatten_labels_every_turn_and_ends_with_the_json_rule():
    text = SC.flatten([{"role": "system", "content": "a"}, {"role": "user", "content": "b"}, {"role": "assistant", "content": "c"}])
    assert text.startswith("INSTRUCTIONS:\na") and "REQUEST:\nb" in text and "YOUR EARLIER ANSWER:\nc" in text and text.endswith("Do not use tools, read files or run commands.")


def test_a_call_runs_the_cli_on_the_named_model_in_its_own_data_folder():
    seen = []
    call = SC.opencode("m1", 5, runner([Done('> build · m1\n{"ok": true}')], seen))
    assert call([{"role": "user", "content": "x"}]) == {"ok": True}
    cmd, k = seen[0]
    assert cmd[:4] == ["opencode", "run", "-m", "opencode/m1"] and k["env"]["XDG_DATA_HOME"].startswith("/") and k["timeout"] == 5


def test_each_thread_gets_its_own_data_folder_and_reuses_it():
    homes = {}

    def grab(name):
        homes[name] = (SC._own_home()["XDG_DATA_HOME"], SC._own_home()["XDG_DATA_HOME"])

    threads = [threading.Thread(target=grab, args=(n,)) for n in "ab"]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert homes["a"][0] == homes["a"][1] and homes["b"][0] == homes["b"][1] and homes["a"][0] != homes["b"][0]


@pytest.mark.parametrize("bad", [Done("", 0), Done("x", 1, "boom"), subprocess.TimeoutExpired("c", 1)])
def test_a_failed_call_raises_model_down(bad):
    with pytest.raises(SC.ModelDown):
        SC.opencode("m1", 1, runner([bad]))([{"role": "user", "content": "x"}])


def test_the_staircase_falls_down_rests_the_failed_step_and_counts():
    stairs = SC.Staircase(["a", "b"], 1, runner([Done("", 1, "down"), Done('{"n": 1}'), Done('{"n": 2}')]))
    assert stairs([{"role": "user", "content": "x"}]) == {"n": 1} and stairs.failed == {"a": 1, "b": 0} and stairs.answered == {"a": 0, "b": 1}
    assert stairs([{"role": "user", "content": "x"}]) == {"n": 2} and stairs.last == "b"     # a is resting: b answers at once


def test_when_every_step_fails_the_error_names_each():
    stairs = SC.Staircase(["a", "b"], 1, runner([Done("", 1, "x1"), Done("", 1, "x2"), Done("", 1, "x3")]))
    with pytest.raises(SC.ModelDown, match="every step of the staircase failed"):
        stairs([{"role": "user", "content": "x"}])


class Reply:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        return self._body


def chat(content):
    return Reply(200, {"choices": [{"message": {"content": content}}]})


def test_http_chat_returns_the_json_and_strips_a_thinking_block():
    seen = {}

    def post(url, **k):
        seen.update(url=url, **k)
        return chat('<think>let me think {not json}</think>\n```json\n{"ok": 1}\n```')

    assert SC.http_chat("m", "https://h/v1/", "KEY", post=post)([{"role": "user", "content": "x"}]) == {"ok": 1}
    assert seen["url"] == "https://h/v1/chat/completions" and seen["headers"]["Authorization"] == "Bearer KEY" and seen["json"]["model"] == "m"


@pytest.mark.parametrize("reply", [Reply(429, text="slow down"), Reply(500, text="boom"), chat(""), Reply(200, {"nope": 1})])
def test_http_chat_failures_are_model_down(reply):
    with pytest.raises(SC.ModelDown):
        SC.http_chat("m", "https://h", "k", post=lambda url, **k: reply)([{"role": "user", "content": "x"}])


def test_a_network_error_is_model_down():
    def post(url, **k):
        raise SC.requests.ConnectionError("down")
    with pytest.raises(SC.ModelDown, match="ConnectionError"):
        SC.http_chat("m", "https://h", "k", post=post)([{"role": "user", "content": "x"}])


def test_from_env_names_the_provider_and_a_missing_key_rests_the_step():
    call = SC.from_env("nvidia", "moonshotai/kimi-k3", env={"NVIDIA_API_KEY": "K"}, post=lambda url, **k: chat('{"a": 1}'))
    assert call.model == "nvidia/moonshotai/kimi-k3" and call([{"role": "user", "content": "x"}]) == {"a": 1}
    none = SC.from_env("cohere", "command-a", env={"COHERE_API_KEY": ""})
    with pytest.raises(SC.ModelDown, match="no COHERE_API_KEY"):
        none([{"role": "user", "content": "x"}])


def test_a_staircase_mixes_cli_models_and_http_steps():
    good = SC.http_chat("g", "https://h", "k", post=lambda url, **k: chat('{"n": 9}'))
    stairs = SC.Staircase([SC.http_chat("bad", "https://h", "k", post=lambda url, **k: Reply(429)), good, "cli"], 1, runner([]))
    assert stairs([{"role": "user", "content": "x"}]) == {"n": 9} and stairs.failed["bad"] == 1 and stairs.answered["g"] == 1


def test_json_mode_is_asked_for_and_dropped_when_the_provider_rejects_it():
    sent = []

    def post(url, **k):
        sent.append("response_format" in k["json"])
        return Reply(400, text="unsupported") if len(sent) == 1 else chat('{"a": 1}')

    assert SC.http_chat("m", "https://h", "k", post=post)([{"role": "user", "content": "x"}]) == {"a": 1} and sent == [True, False]
    sent.clear()
    SC.http_chat("m", "https://h", "k", post=lambda url, **k: sent.append("response_format" in k["json"]) or chat("{}"), json_mode=False)([{"role": "user", "content": "x"}])
    assert sent == [False]
