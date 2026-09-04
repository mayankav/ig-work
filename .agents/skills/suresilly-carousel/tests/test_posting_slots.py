"""Both clocks, repeated deliveries, crash safety, and real git push conflicts."""
from pathlib import Path
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import posting_slots as slots
from run_result import result as run_result

CREATED = "2026-09-04T02:30:00Z"
SLOT = "2026-09-04_0800"


@pytest.mark.parametrize("created,cron,want", [
    (CREATED, "30 2 * * *", SLOT),
    ("2026-09-04T07:30:00Z", "30 2 * * *", SLOT),
    ("2026-09-04T19:15:00Z", "30 14 * * *", "2026-09-04_2000"),
    ("2026-09-05T00:15:00Z", "30 14 * * *", "2026-09-04_2000"),
    ("2026-09-04T02:29:59Z", "", "2026-09-03_2000"),
    ("2026-09-04T14:30:00Z", "", "2026-09-04_2000"),
])
def test_slot_date_is_event_time_not_job_start(created, cron, want):
    assert slots.slot_at(created, cron) == want


def test_clocks_share_a_slot():
    gh = slots.identify({"schedule": "30 2 * * *"}, "schedule", CREATED, "100")
    cf = slots.identify({"inputs": {"mode": "publish", "slot_id": SLOT}},
                       "workflow_dispatch", CREATED, "101")
    assert gh[0] == cf[0] == SLOT


@pytest.mark.parametrize("supplied", ["../../bad", "2026-09-04_0900", "2026-09-05_0800",
    "2026-09-03_0800", "2026-02-31_0800"])
def test_invalid_or_stale_slot_refuses(supplied):
    with pytest.raises(ValueError):
        slots.identify({"inputs": {"mode": "publish", "slot_id": supplied}},
                      "workflow_dispatch", CREATED, "100")


def save(path, value):
    path.write_text(json.dumps(value))


def first(path):
    value, _, _ = slots.reserve(path, SLOT, "gh-100", "100", CREATED, False)
    save(path, value)
    return value


def final(**updates):
    return dict(stage="generation", outcome="stopped", fault_code="quality_refused",
                reason="A temporary failure can recover.", retryable=True, published=False) | updates


def test_duplicate_clocks_do_no_work(tmp_path):
    path = tmp_path / (SLOT + ".json")
    first(path)
    before = path.read_bytes()
    assert slots.reserve(path, SLOT, "gh-101", "101", CREATED, False)[0] is None
    assert path.read_bytes() == before


def test_crash_is_not_a_retry_permission(tmp_path):
    path = tmp_path / (SLOT + ".json")
    first(path)
    assert slots.reserve(path, SLOT, "tg-2", "102", CREATED, True)[0] is None


@pytest.mark.parametrize("outcome", [final(retryable=False), final(stage="tests"),
    final(stage="posting"), final(published=True), final(outcome="held"), final(outcome="built"),
    final(outcome="ok"), final(stage="state saving"), final(retryable="true")])
def test_unsafe_retries_do_not_create_an_attempt(tmp_path, outcome):
    path = tmp_path / (SLOT + ".json")
    value = first(path)
    value["attempts"][-1]["result"] = outcome
    save(path, value)
    assert slots.reserve(path, SLOT, "tg-2", "102", CREATED, True)[0] is None


def test_one_useful_retry_and_repeated_delivery(tmp_path):
    path = tmp_path / (SLOT + ".json")
    first(path)
    save(path, slots.finish(path, "100", final()))
    value, _, _ = slots.reserve(path, SLOT, "tg-2", "102", CREATED, True)
    assert len(value["attempts"]) == 2
    save(path, value)
    save(path, slots.finish(path, "102", final()))
    # Even after the retry finishes, repeated delivery cannot start attempt 3.
    assert slots.reserve(path, SLOT, "tg-2", "103", CREATED, True)[0] is None
    assert len(slots.load(path)["attempts"]) == 2


def test_no_prior_attempt_no_retry(tmp_path):
    assert slots.reserve(tmp_path / (SLOT + ".json"), SLOT, "tg-2", "102", CREATED, True)[0] is None


def test_finish_must_own_reservation_and_cannot_replace_result(tmp_path):
    path = tmp_path / (SLOT + ".json")
    first(path)
    with pytest.raises(ValueError):
        slots.finish(path, "101", final())
    save(path, slots.finish(path, "100", final()))
    with pytest.raises(ValueError):
        slots.finish(path, "100", final(published=True))


def test_corrupt_state_fails_closed(tmp_path):
    path = tmp_path / (SLOT + ".json")
    for content in ("{", "[]", '{"version":1,"attempts":[]}'):
        path.write_text(content)
        with pytest.raises(ValueError):
            slots.reserve(path, SLOT, "tg-2", "102", CREATED, False)


def test_manual_build_and_force_do_not_claim_posting_slot():
    for mode in ("build", "force"):
        slot, request, retry = slots.identify({"inputs": {"mode": mode, "request_id": "tg-2"}},
                                            "workflow_dispatch", CREATED, "100")
        assert slot == "manual-tg-2" and request == "tg-2" and not retry


def test_rerun_same_github_run_is_not_new_work(tmp_path):
    path = tmp_path / (SLOT + ".json")
    first(path)
    save(path, slots.finish(path, "100", final()))
    assert slots.reserve(path, SLOT, "new-input", "100", CREATED, True)[0] is None


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()


def repos(tmp_path):
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")
    one, two = tmp_path / "one", tmp_path / "two"
    git(tmp_path, "clone", str(origin), str(one))
    (one / "README.md").write_text("test\n")
    git(one, "add", "README.md")
    git(one, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
        "commit", "-m", "initial")
    git(one, "push", "origin", "main")
    git(tmp_path, "clone", str(origin), str(two))
    return origin, one, two


def test_real_push_conflict_cannot_grant_two_reservations(tmp_path):
    origin, one, two = repos(tmp_path)
    for root, request, run in ((one, "gh-100", "100"), (two, "gh-101", "101")):
        path = root / "state/slots" / (SLOT + ".json")
        value, _, _ = slots.reserve(path, SLOT, request, run, CREATED, False)
        if root == one:
            slots.persist(root, path, value)
        else:
            with pytest.raises(subprocess.CalledProcessError):
                slots.persist(root, path, value)
    saved = json.loads(git(origin, "show", "main:state/slots/" + SLOT + ".json"))
    assert saved["attempts"][0]["run_id"] == "100"
    assert git(one, "status", "--porcelain") == ""


def test_dirty_work_is_preserved(tmp_path):
    _, one, _ = repos(tmp_path)
    (one / "README.md").write_text("user edit\n")
    path = one / "state/slots" / (SLOT + ".json")
    value, _, _ = slots.reserve(path, SLOT, "gh-100", "100", CREATED, False)
    with pytest.raises(ValueError):
        slots.persist(one, path, value)
    assert (one / "README.md").read_text() == "user edit\n" and not path.exists()


def test_cli_never_grants_work_after_push_failure(tmp_path, monkeypatch):
    _, one, two = repos(tmp_path)
    path = one / "state/slots" / (SLOT + ".json")
    value, _, _ = slots.reserve(path, SLOT, "gh-100", "100", CREATED, False)
    slots.persist(one, path, value)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"mode": "publish", "slot_id": SLOT}}))
    output = tmp_path / "output.txt"
    monkeypatch.setattr(slots, "ROOT", two)
    monkeypatch.setattr(sys, "argv", ["posting_slots.py", "reserve"])
    for key, value in dict(GITHUB_RUN_ID="101", GITHUB_EVENT_PATH=str(event),
            GITHUB_EVENT_NAME="workflow_dispatch", RUN_CREATED_AT=CREATED,
            GITHUB_OUTPUT=str(output)).items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit, match="reserve failed"):
        slots.main()
    assert "accepted" not in output.read_text()


def test_result_save_push_and_identical_repeat(tmp_path):
    origin, one, _ = repos(tmp_path)
    path = one / "state/slots" / (SLOT + ".json")
    value, _, _ = slots.reserve(path, SLOT, "gh-100", "100", CREATED, False)
    slots.persist(one, path, value)
    complete = slots.finish(path, "100", final())
    slots.persist(one, path, complete)
    revision = git(origin, "rev-parse", "main")
    slots.persist(one, path, slots.finish(path, "100", final()))
    assert git(origin, "rev-parse", "main") == revision
    saved = json.loads(git(origin, "show", "main:state/slots/" + SLOT + ".json"))
    assert saved["attempts"][0]["result"] == final()


def test_duplicate_result_is_not_broken_or_posted():
    steps = {"slot": {"outcome": "success", "outputs": {"accepted": "false"}}}
    value = run_result(steps, mode="publish", slug="", verdict="", reason="", retry=False, published=None)
    assert value["outcome"] == "duplicate" and not value["retryable"] and not value["published"]


def test_unhelpful_retry_gets_an_answer_not_silent_duplicate():
    outputs = dict(accepted="false", decision="retry_refused", reason="A saved result is missing.")
    value = run_result({"slot": {"outcome": "success", "outputs": outputs}}, mode="publish",
                       slug="", verdict="", reason="", retry=False, published=None)
    assert value["outcome"] == "stopped" and value["reason"] == outputs["reason"]
    assert not value["retryable"]


def test_repeated_blank_publish_cannot_move_to_the_next_held_deck(tmp_path):
    event = {"inputs": {"decision": "publish", "slug": "", "request_id": "tg-77"}}
    key, request, retry = slots.identify(event, "workflow_dispatch", CREATED, "100")
    path = tmp_path / (key + ".json")
    value, _, decision = slots.reserve(path, key, request, "100", CREATED, retry)
    assert decision == "accepted"
    save(path, value)
    # A separate workflow run receives the same Telegram update after the first
    # publish removed a held record. Reservation blocks before resolving a slug.
    other_key, other_request, retry = slots.identify(event, "workflow_dispatch", CREATED, "101")
    assert (other_key, other_request) == (key, request)
    assert slots.reserve(path, key, request, "101", CREATED, retry)[2] == "duplicate"


def test_workflow_reservation_precedes_all_quota_and_duplicates_skip_topup():
    import yaml
    doc = yaml.safe_load((ROOT / ".github/workflows/auto-post.yml").read_text())
    steps = doc["jobs"]["post"]["steps"]
    ids = [s.get("id") for s in steps]
    assert ids.index("slot") < ids.index("install") < ids.index("build")
    for key in ("install", "gates", "verbs", "test_state", "build", "record"):
        assert "steps.slot.outputs.accepted == 'true'" in steps[ids.index(key)]["if"]
    assert "needs.post.outputs.accepted == 'true'" in doc["jobs"]["topup"]["if"]
    assert "needs.post.result == 'success'" in doc["jobs"]["topup"]["if"]
    assert "needs.post.outputs.deck_built == 'true'" in doc["jobs"]["topup"]["if"]
    assert "save_attempt" in ids and ids.index("save_attempt") < ids.index("result")
    review = yaml.safe_load((ROOT / ".github/workflows/review.yml").read_text())
    actions = review["jobs"]["decide"]["steps"]
    reservation = next(i for i, step in enumerate(actions) if step.get("id") == "slot")
    for i, step in enumerate(actions):
        if step.get("name") in {"Install", "Act on the reply, and say what happened", "Record the decision"}:
            assert i > reservation and "steps.slot.outputs.accepted == 'true'" in step["if"]


def test_record_stages_promoted_art_before_slot_completion(tmp_path):
    """Execute the workflow's real staging loop in a disposable repository."""
    import yaml
    doc = yaml.safe_load((ROOT / ".github/workflows/auto-post.yml").read_text())
    record = next(s["run"] for s in doc["jobs"]["post"]["steps"]
                  if s.get("id") == "record")
    loop = record[record.index("for path in state carousels"):]
    loop = loop[:loop.index("\nif ! git diff --staged --quiet;")]
    _, checkout, _ = repos(tmp_path)
    skill = ".agents/skills/suresilly-carousel/"
    owned = ["state/used.jsonl", "carousels/test/contact_sheet.png",
             skill + "mascot/poses.json", skill + "mascot/library/new_pose.png",
             skill + "mascot/library/_contact_sheet.png",
             skill + "mascot/checks/reviews/test.json", skill + "mascot/checks/index/test.json",
             skill + "mascot/usage_history.json", skill + "palette_history.json",
             skill + "citation_history.json"]
    for name in owned:
        target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("test content\n")
    # Never solve a dirty tree by staging unrelated code edits.
    (checkout / "README.md").write_text("unrelated edit\n")
    subprocess.run(["bash", "-e", "-c", loop], cwd=checkout, check=True)
    assert set(git(checkout, "diff", "--cached", "--name-only").splitlines()) == set(owned)
    assert git(checkout, "diff", "--name-only") == "README.md"


def background_record(workflow, job, name):
    import yaml
    doc = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
    steps = doc["jobs"][job]["steps"]
    step = next(s for s in steps if s.get("name") == name)
    assert "always()" in step["if"]
    recovery = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
    assert recovery["if"] == "failure()"
    return step["run"]


BACKGROUND_JOBS = [
    ("auto-post.yml", "topup", "Record what was proved"),
    ("insights.yml", "collect", "Record what was measured"),
]


@pytest.mark.parametrize("workflow,job,name", BACKGROUND_JOBS)
@pytest.mark.parametrize("failed_command", ["add", "commit", "pull", "push"])
def test_background_save_errors_cannot_report_success(tmp_path, workflow, job, name, failed_command):
    _, checkout, _ = repos(tmp_path)
    (checkout / "state").mkdir()
    for filename in ("insights.jsonl", "vendor_quotas.json", "flux_neurons.json"):
        (checkout / "state" / filename).write_text("{}\n")
    script = background_record(workflow, job, name)
    # All unaffected git commands are real, against a local disposable remote.
    inject = ('git() { if [ "$1" = "' + failed_command + '" ]; then return 91; fi; '
              'command git "$@"; }\n')
    completed = subprocess.run(["bash", "-e", "-c", inject + script], cwd=checkout,
                               capture_output=True, text=True)
    assert completed.returncode == 91, completed.stdout + completed.stderr


@pytest.mark.parametrize("workflow,job,name", BACKGROUND_JOBS)
def test_background_no_changes_is_success_and_usage_is_saved(tmp_path, workflow, job, name):
    origin, checkout, _ = repos(tmp_path)
    script = background_record(workflow, job, name)
    subprocess.run(["bash", "-e", "-c", script], cwd=checkout, check=True,
                   capture_output=True)
    files = (["vendor_quotas.json", "flux_neurons.json"] if job == "topup"
             else ["insights.jsonl"])
    (checkout / "state").mkdir()
    for filename in files:
        (checkout / "state" / filename).write_text('{"retained":true}\n')
    subprocess.run(["bash", "-e", "-c", script], cwd=checkout, check=True,
                   capture_output=True)
    for filename in files:
        assert json.loads(git(origin, "show", "main:state/" + filename)) == {"retained": True}
