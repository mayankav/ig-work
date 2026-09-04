"""Source transport and persistence tests; synthetic evidence stays in temp dirs."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bibliography as bib
import claim_support as support
import critic
import llm
import writer
from support_fixture import with_support

PROVIDERS = (("groq", lambda *args: None),)


def entry(claim="A plain claim about a shared task."):
    return with_support({"id": "test-2000", "claims": [claim], "pillars": ["trust"], "verified": {}})


def record():
    return next(iter(entry()["claim_support"].values()))


def test_record_replays():
    data = entry()
    support.validate(record(), data["claims"][0], data["line"])


def test_ocr_whitespace_does_not_become_a_false_invented_quote():
    evidence = record()
    original = evidence["source"]["passages"][0]["text"]
    evidence["source"]["passages"][0]["text"] = original.replace(" ", "  \n\t")
    support.check_reply(evidence["review"], evidence["source"])


def test_claim_refusal_keeps_the_specific_reason():
    evidence = record()
    reason = "The passage says training can undo the habit, not that it cannot change."
    evidence["review"]["vetoes"].append({"id": "claim", "reason": reason})
    with pytest.raises(support.Unsupported) as refused:
        support.check_reply(evidence["review"], evidence["source"])
    assert reason in str(refused.value)


@pytest.mark.parametrize("changed", ["Habits do change with practice.",
    "Habits may not change with practice.", "Habits do not change without practice."])
def test_whitespace_tolerance_never_changes_words(changed):
    evidence = record()
    evidence["source"]["passages"][0]["text"] = "Habits  do\nnot change with practice."
    evidence["review"]["quotes"] = [{"passage": 0, "text": changed}]
    with pytest.raises(support.Unsupported, match="does not match"):
        support.check_reply(evidence["review"], evidence["source"])


@pytest.mark.parametrize("change", ["claim", "line", "bytes", "version", "reviewer"])
def test_proof_cannot_move_to_another_claim_or_book(change):
    data, evidence = entry(), record()
    if change == "claim":
        data["claims"][0] = "A different claim."
    elif change == "line":
        data["line"] = "Another book"
    elif change == "bytes":
        evidence["source"]["passages"][0]["text"] += " Changed."
    elif change == "version":
        evidence["version"] = "old"
    else:
        evidence["checked_by"] = evidence["proposed_by"]
        evidence["sha256"] = support.digest({k: v for k, v in evidence.items() if k != "sha256"})
    with pytest.raises(support.Unsupported):
        support.validate(evidence, data["claims"][0], data["line"])


@pytest.mark.parametrize("fault", ["clear", "uncertain", "missing", "invented", "claim_veto", "bad_index"])
def test_unreliable_reviewer_cannot_supply_support(fault):
    evidence = record()
    reply = evidence["review"]
    if fault == "clear": reply["vetoes"] = []
    if fault == "uncertain": reply["uncertain"] = ["claim"]
    if fault == "missing": reply["inspected"] = ["claim"]
    if fault == "invented": reply["quotes"][0]["text"] = "This quote is not in the source."
    if fault == "claim_veto": reply["vetoes"].append({"id": "claim", "reason": "Only the term matches."})
    if fault == "bad_index": reply["quotes"][0]["passage"] = True
    with pytest.raises(support.Unsupported):
        support.check_reply(reply, evidence["source"])


def test_source_request_is_bound_to_catalogue_scan():
    calls = []
    def get(url, params):
        calls.append((url, params))
        if "metadata" in url:
            return {"d1": "ia800204.us.archive.org", "dir": "/27/items/synthetic-source"}
        return {"ia": "synthetic-source", "matches": [
            {"text": "A {{{shared}}} task is described here.", "par": [{"page": 12}]}]}
    source = support.passages_for(record()["book"], "shared task", get)
    assert calls[0][0] == "https://archive.org/metadata/synthetic-source"
    assert calls[1][1]["item_id"] == "synthetic-source"
    assert calls[1][1]["q"] == '"shared task"'
    assert calls[1][1]["pre_tag"] == "{{{"
    assert source["passages"][0]["pages"] == [12]
    assert "{{{" not in source["passages"][0]["text"]


@pytest.mark.parametrize("host,path", [("evil.example", "/27/items/synthetic-source"),
    ("ia800204.us.archive.org.evil.example", "/27/items/synthetic-source"),
    ("ia800204.us.archive.org", "/27/items/other-book")])
def test_foreign_host_or_item_path_is_not_followed(host, path):
    calls = []
    def get(url, params):
        calls.append(url)
        return {"d1": host, "dir": path}
    with pytest.raises(support.Unsupported):
        support.passages_for(record()["book"], "shared task", get)
    assert len(calls) == 1


def test_whole_overlong_passage_is_refused_not_cut():
    def get(url, params):
        if "metadata" in url:
            return {"d1": "ia800204.us.archive.org", "dir": "/27/items/synthetic-source"}
        return {"ia": "synthetic-source", "matches": [
            {"text": "x" * (support.MAX_PASSAGE_CHARS + 1), "par": [{"page": 1}]}]}
    with pytest.raises(support.Unsupported):
        support.passages_for(record()["book"], "shared task", get)


def test_live_path_passes_fetched_text_to_independent_reviewer(monkeypatch):
    evidence = record()
    monkeypatch.setattr(support, "passages_for", lambda *args: evidence["source"])
    monkeypatch.setattr(critic, "available_providers", lambda proposer: PROVIDERS)
    def ask(system, user, schema, **kwargs):
        payload = json.loads(user)
        assert payload["source"] == evidence["source"]
        assert payload["claims"]["control"] == support.CONTROL
        assert kwargs["providers"] == PROVIDERS
        return evidence["review"], "groq"
    monkeypatch.setattr(llm, "ask", ask)
    result = support.verify(evidence["book"], "shared task", evidence["claim"], "gemini", None)
    support.validate(result, evidence["claim"], entry()["line"])


def test_outage_cannot_be_saved_as_support(monkeypatch):
    evidence = record()
    monkeypatch.setattr(support, "passages_for", lambda *args: evidence["source"])
    monkeypatch.setattr(critic, "available_providers", lambda proposer: PROVIDERS)
    def unavailable(*args, **kwargs): raise llm.ModelRefused("outage")
    monkeypatch.setattr(llm, "ask", unavailable)
    with pytest.raises(support.Unsupported, match="could not be reached"):
        support.verify(evidence["book"], "shared task", evidence["claim"], "gemini", None)


def test_updates_preserve_each_claims_own_record(tmp_path, monkeypatch):
    monkeypatch.setattr(bib, "CITATIONS_PATH", tmp_path / "citations.json")
    first, second = entry(), entry("A second claim about a shared task.")
    bib.store(first)
    original = copy.deepcopy(bib.load_pool()[0]["claim_support"])
    bib.store(second)
    merged = bib.load_pool()[0]
    assert len(merged["claims"]) == len(merged["claim_support"]) == 2
    assert all(merged["claim_support"][k] == v for k, v in original.items())


@pytest.mark.parametrize("existing", [False, True])
def test_unproved_insert_or_update_leaves_file_unchanged(tmp_path, monkeypatch, existing):
    path = tmp_path / "citations.json"
    monkeypatch.setattr(bib, "CITATIONS_PATH", path)
    path.write_text(json.dumps({"citations": [entry()] if existing else []}))
    before = path.read_bytes()
    data = entry("An unsupported new claim.")
    data.pop("claim_support")
    with pytest.raises(bib.Unverified, match="no current passage"):
        bib.store(data)
    assert path.read_bytes() == before


def test_legacy_claims_are_not_selectable(monkeypatch):
    old = entry()
    old.pop("claim_support")
    monkeypatch.setattr(writer, "load_citations", lambda: {old["id"]: old})
    assert writer.citations_for("trust") == []
    monkeypatch.setattr(bib, "discover", lambda *a, **k: (None, []))
    monkeypatch.setattr(bib, "recent", lambda: [])
    def forbidden(*args, **kwargs): pytest.fail("writer called with no supported source")
    monkeypatch.setattr(llm, "ask", forbidden)
    with pytest.raises(writer.Refused, match="No source-supported claim") as refusal:
        writer.plan_deck("A moment at the door", "trust")
    assert refusal.value.retry is False


def test_filter_keeps_original_claim_indices(monkeypatch):
    data = entry()
    data["claims"].insert(0, "An old unproved claim.")
    monkeypatch.setattr(writer, "load_citations", lambda: {data["id"]: data})
    monkeypatch.setattr(bib, "discover", lambda *a, **k: (None, []))
    monkeypatch.setattr(bib, "recent", lambda: [])
    assert bib.supported_indices(data) == [1]
    def inspect_prompt(system, user, schema, **kwargs):
        assert "claim 1:" in user
        assert "claim 0:" not in user
        assert "An old unproved claim." not in user
        raise llm.ModelRefused("stop after inspecting the prompt")
    monkeypatch.setattr(llm, "ask", inspect_prompt)
    with pytest.raises(llm.ModelRefused, match="stop after"):
        writer.plan_deck("A moment at the door", "trust")


def test_force_cannot_use_unproved_selected_claim(monkeypatch):
    old = entry()
    old.pop("claim_support")
    monkeypatch.setattr(writer, "load_citations", lambda: {old["id"]: old})
    monkeypatch.setattr(writer, "plan_deck", lambda *a, **k: (
        {"citation_id": old["id"], "claim_index": 0}, {}, "gemini"))
    with pytest.raises(bib.Unverified, match="no usable source support"):
        writer.write_deck("A moment at the door", "trust", title="Test", pattern="Test",
                          pillar="Trust", allow_faults=True)


def test_publication_checks_printed_claim_not_only_book(monkeypatch):
    data = entry()
    monkeypatch.setattr(bib, "load_pool", lambda: [data])
    markdown = f"- **Source:** {data['line']}\n- **Source Claim:** {data['claims'][0]}\n"
    bib.require_deck_support(markdown)
    with pytest.raises(bib.Unverified, match="no matching source"):
        bib.require_deck_support(markdown.replace(data["claims"][0], "An unproved sentence."))
    data.pop("claim_support")
    with pytest.raises(bib.Unverified, match="no usable source"):
        bib.require_deck_support(markdown)


def test_post_command_runs_source_check_before_network(tmp_path, monkeypatch):
    import importlib.util
    path = Path(__file__).resolve().parents[4] / "scripts/post_to_ig.py"
    spec = importlib.util.spec_from_file_location("source_checked_post", path)
    post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post)
    md = tmp_path / "carousel.md"
    md.write_text("### Caption\nA test caption\n")
    monkeypatch.setattr(sys, "argv", ["post_to_ig.py", "--carousel", str(md)])
    monkeypatch.setattr(post, "require_posting_allowed", lambda: None)
    monkeypatch.delenv("DRY_RUN", raising=False)
    def forbidden(*args, **kwargs): pytest.fail("network reached before source check")
    monkeypatch.setattr(post.requests, "post", forbidden)
    with pytest.raises(bib.Unverified, match="one source"):
        post.main()


@pytest.mark.parametrize("phrase", ["shared task", "plain source"])
def test_candidate_to_saved_claim_uses_passages(monkeypatch, tmp_path, phrase):
    evidence = record()
    def get(url, params):
        if url == bib.SEARCH_URL:
            assert "key,ia" in params["fields"]
            return {"docs": [{"key": "/works/OL1W", "ia": ["synthetic-source"],
                "title": "Synthetic Source", "author_name": ["Test Author"],
                "first_publish_year": 2000, "lcc": ["BF1"]}]}
        if url == bib.INSIDE_URL: return {"hits": {"total": 2}}
        if "metadata" in url:
            return {"d1": "ia800204.us.archive.org", "dir": "/27/items/synthetic-source"}
        return {"ia": "synthetic-source", "matches": [{
            "text": evidence["source"]["passages"][0]["text"], "par": [{"page": 1}]}]}
    monkeypatch.setattr(bib, "_get", get)
    monkeypatch.setattr(critic, "available_providers", lambda proposer: PROVIDERS)
    def ask(system, user, schema, **kwargs):
        assert json.loads(user)["source"]["scan_id"] == "synthetic-source"
        return evidence["review"], "groq"
    monkeypatch.setattr(llm, "ask", ask)
    monkeypatch.setattr(bib, "CITATIONS_PATH", tmp_path / "citations.json")
    verified = bib.verify({"author": "Test Author", "title": "Synthetic Source",
                           "year": 2000, "phrase": phrase, "claim": evidence["claim"]},
                          "gemini", ["trust"])
    bib.store(verified)
    saved = bib.load_pool()[0]
    assert bib.supported_indices(saved) == [0]
    assert saved["claim_support"] == verified["claim_support"]
