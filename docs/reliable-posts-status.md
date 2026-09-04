# Reliable posts — implementation checkpoint

Latest source trial: James's advice to act on a plan at the first chance was
tested through the real bibliography entry point. It stopped at catalogue
access before model review: Open Library returned a local connection refusal
(`ConnectionRefusedError`, errno 61). The earlier successful passage concerns
hand movements and was not promoted as evidence about relationships. The new
trial is preserved in `docs/claim-support-trials/20260904-james-first-chance.json`.
No active claim was added. Web access to the text is not proof that the Python
source path works; it still requires an end-to-end source check.

Review-request headroom now gates optional fresh generation for Gemini and
Groq. It requires a recent provider-reported remaining count for the exact model,
enough for all groups. Missing, stale, future, malformed and counted-only records
choose checked library art before importing or calling the generator. Gemini's
current local tally does not report remaining quota, so it cannot clear this
guard. Offline qualification/auditing is unchanged and still bounded separately.
Fifty-nine focused tests pass, including actual fresh-generation fallback before
generator access. Provider-side quota cannot be reserved by this local check;
token/minute limits or other account users may still cause a later review to
fail. Such a group remains rejected. No live models were called.

Cloudflare requests now reserve a conservative cost before HTTP, including
failed requests and image-review calls. Unknown model prices or an unsaved
reservation stop the request. Billing headers can increase usage, never refund
it. Fresh art keeps enough shared allowance for the required Cloudflare review
groups; a boundary test proves an image cannot consume that headroom.
Verification: 96 focused budget/fallback/quota checks and 17 existing LLM checks
passed, with no live model calls. Full-context reservations are deliberately
conservative and can reduce free throughput. Other applications on the same
account remain outside the local ledger. The later Gemini/Groq headroom guard
is described above. No terms were accepted and no reviewer was qualified by this work.

Shared budget check: image allowance now accounts for text usage in the same
Cloudflare ledger, while retaining the lower image-only cap. Invalid or unreadable
usage no longer resets spending to zero. Usage saves replace the file atomically;
a failed replacement preserves the previous record. A fresh-art budget of zero
is no longer mistaken for an omitted budget. The initial affected run passed
163 checks; a broken-link case was added afterward and checked separately.
The later Cloudflare reservation change above replaces after-response accounting
on its live request path. The local ledger does not measure other applications
on the account. Cross-provider request headroom is now checked as described above.
The 10,000-neuron free daily allowance was rechecked against
[Cloudflare pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/).

Full checkpoint after the hosting change: all 56 Python suites pass, with logs
at `/tmp/suresilly-tests-78051`. Both Worker suites pass (41 reply checks and 15
slot checks). `git diff --check` passes. GitHub was rechecked: `SS_HALT=1`, main
remains `db0f08d454a0f856f7ccc7ed0d8234b10a5a6128`, and no jobs are running or queued.
The prior four test failures are resolved. None of these results proves live
model qualification, sufficient supported claims or production readiness.

Held-post startup and hosting checks: the review workflow now installs the same
pinned engine dependencies as automatic posting. Its startup check loads the
actual source, artwork and render checks without network access. Before any
Instagram write, the publisher fetches all nine hosted images and compares
their bytes with the checked local files. Missing, changed, oversized, truncated
or redirected images stop the post and name hosting as the failed stage.
The affected 56 tests pass. Four publication-recovery fixtures initially had no
slide files; they now exercise the hosting check with nine temporary files and
fake HTTP replies before checking publication receipts. No gate was bypassed.
These changes remain local and undeployed.

Latest local render verification: 155 browser/asset checks passed in 28.43s;
18 publication checks and 28 wiring checks also passed. Font checks require an
actual loaded FontFace, not a fallback-compatible `document.fonts.check` result.
Image decode failure stops export. Failed renders preserve previous slide bytes
but leave a blocking marker. Render evidence includes the installed dependency
versions and bundled Chromium revision. The actual launched Chromium version is
checked. Changed render code, fonts or dependencies invalidate old export proof.
No live model request, deployment or publication occurred. A pinned Linux
visual baseline and the remaining release requirements are still open.

This is a partial implementation, not a completed release. No new code has been
pushed or deployed. Normal operation has not been re-enabled by this work.
The GitHub repository variable `SS_HALT` is now set to `1` and was verified.
The old held-publish workflow does not read that variable; do not use it during
the repair. The local code now passes the pause to both posting workflows and
checks it in held release and each Instagram write path. These changes are not
live yet. The pause does not cancel an already-started remote run.

## Latest release-path check

The last full verification passed all 51 Python suites and all 56 Worker checks.
Python logs are `/tmp/suresilly-tests-60608`. All 147 browser checks pass. A later
import-preview adjustment passed the 53 focused import/artwork tests. No live
model requests, publication, deployment or agreement acceptance occurred in
this verification. Normal bibliography tests are now
offline, including controlled outages. `test_bibliography.py --live-catalogue`
explicitly checks the external catalogue and fails rather than quietly skipping
an outage. Two tests pin this separation. Current live checks show `SS_HALT=1`,
remote main `db0f08d`, and no queued or running jobs. The active 24-book,
53-claim pool has zero supported claims and the image reviewer list is empty.
The release is not ready, despite the successful local test sets.

Outline repair now uses bounded field edits through `plan_repair.py`, not a
replacement outline. Text, numbers and dependency/export arrays can be repaired;
the citation and claim index cannot change. The shared repair logic retains an
edit only when all outline checks remove faults without introducing new ones,
and restores unsolicited clean-field changes. Repairs use the original provider
and stop after three unchanged fault signatures. Outline dependencies now reject
self-links, forward links and duplicate links. Seventy-two focused tests passed,
plus the existing 98 writer and 15 outcome checks. These tests use controlled
responses, not live model calls; the full source-to-nine-slide run still needs
release verification.

Performance reporting has since been implemented and checked separately:
18 fixed-age/isolation tests, the existing 35 insights checks, 28 wiring checks,
and focused workflow/publication tests pass. `insights_report.py` recomputes
saves/reach and shares/reach from the stored counts. Missing or invalid counts,
and zero reach, produce unavailable ratios. Only readings taken at 72–73 hours
are marked comparable; the actual age is retained, and late readings are never
relabelled as three-day readings. The hourly workflow prioritizes timely posts
over old backlog and publishes the read-only report in its run summary. A partial
fetch failure preserves successful records but leaves the job failed.

Reporting no longer imports the publisher or image engine. `instagram_api.py`
holds shared host identifiers without optional dependencies. A subprocess test
with installed packages disabled proves the report imports independently.
The repository was verified public; no paid service was added. No Instagram
request or live workflow change was made. The saved readings file is absent,
so the current report correctly makes no performance claim. Live permission
and scheduled collection remain unverified until rollout.

`art_eligibility.py` now supplies the mandatory shared evidence path for fresh
art, imports, fallback selection and generation references. It binds exact PNG
bytes to current pixel/check code, a qualified model and the actual group
response. It replays the inspection sheet, full coverage, known control and
vetoes rather than trusting a saved approval flag. A later failed review revokes
the old pointer; duplicate image bytes share any veto. The renderer freezes the
checked bytes and keeps all nine evidence references. Both direct publishing
and held publishing check those records again. The pre-publication commit now
includes the exact art evidence needed to survive runner loss; a replacement
checkout was tested. The normal workflow also saves evidence on failure.

The current result is **zero eligible library images**, not an approved library.
No source image was deleted or granted a live body review. Fewer than nine
checked images stops a run before fetching a topic or spending generation quota,
including `force`, with retry disabled. A qualified reviewer, actual library
audit and quota-aware reservation still remain release work.

Publication intent is now committed and pushed before the external publish
request. `scripts/reserve_publication.py` requires matching local/remote main,
commits only the exact deck's markdown, contact sheet, render-check record,
artwork evidence and pending marker, and refuses a failed push. A new checkout sees the
unresolved intent even after the original runner disappears. Unrelated staged
and unstaged edits are preserved. Six real-local-git tests cover replacement
runners, stale main, feature branches, push failure/lost acknowledgement, and
index preservation; 58 receipt/result/pause tests pass, including proof that a
failed reservation does not call Instagram publication. No live repository was
pushed. Deployment and live workflow verification are still required.

Publication receipts now use complete, exclusive writes and one shared
deck-bound numeric-ID check in the publisher, held release, and final result.
The publisher writes `publication_pending.json` before requesting publication.
Lost responses and failed receipt saves retain it; both republishing and
rebuilding that deck refuse while it exists. API confirmation is also carried
through workflow outputs, so a receipt-save failure reports state saving with
publication confirmed, not a generic claim that Instagram refused the post.
Fifty-seven focused receipt/result/pause checks pass, including interrupted
publication, failed saves, corrupt or wrong-deck receipts, and archive guards.
The existing release, insights, and wiring suites pass. No Instagram calls
were made. Durable pre-publication coordination has since been added as
described above. Reconciliation of an ambiguous Instagram outcome remains a
manual check; an unresolved attempt never authorizes an automatic repeat.

The remaining configured Gemini models, `gemini-3.1-flash-lite` and
`gemini-3.5-flash-lite`, each missed the known extra leg in a single-request
trial. Both stopped immediately. Their evidence files end in
`20260904-gemini31-lite-control.json` and `20260904-gemini35-lite-control.json`
under `references/image_review_qualifications/`. Every configured Gemini/Groq
image model has now failed at least one qualification trial. None is qualified.
Cloudflare's configured image model remains untested because its license
agreement has not been accepted. User authorization is required to submit it;
the persistent readiness goal is not license acceptance. Even acceptance would
only permit testing, not prove readiness. Other release work remains incomplete.

The corrected draft-edit format passed one live Groq request, recorded at
`docs/draft-repair-trials/20260904-groq-short-ids.json`. The reply changed only
the failed spoken line and retained the caption. This closes the isolated
edit-format check, not the full-deck or end-to-end release test.

Gemini `gemini-2.5-flash-lite` was tested once with the current body/upper/lower
inspection sheet. It reported two arms and two legs for every panel and no
faults, missing the known extra-leg control. Qualification stopped immediately;
the model remains ineligible. Evidence is
`.agents/skills/suresilly-carousel/references/image_review_qualifications/20260904-gemini25-lite-control.json`.
No library image has been granted body eligibility by this failed trial.

One live Groq draft-edit format trial used exactly one HTTP request. Its record
is `docs/draft-repair-trials/20260904-groq-format.json`; status remains refused.
The model returned a useful conversational question, but the long fault enum
had over-escaped quotation marks. Offline replay also found that the speech
check rejected any question containing 'you', including questions to another
person. Repair replies now use short fault IDs, with descriptions kept in the
prompt. The speech check preserves ordinary conversational questions and still
rejects the measured 'smallest/next action/step' coaching prompt. All 26 focused
repair/speech checks pass. These fixes have not had a second live trial. Quota
use from the first trial is retained; no deck was built or posted.

The current `Say` and `When` fields now participate in duplicate-line checks.
The researcher-in-speech check now reads `Say`, not only the obsolete response
labels. It rejects the exact Nolen-Hoeksema explanation from the supplied
September 3 screenshot. The historical deck sweep had incorrectly treated that
deck as a clean example; it is now an explicit known rejection. Seven focused
checks and all 98 writer checks pass. This fixes a missed fault that the repair
loop previously never received.

Draft repair now returns up to 12 edits to existing text fields, not a complete
replacement draft. Code requires a strict reduction in the set of current
faults without new faults. It restores each edited field when the old text
passes equally well, removing unneeded clean-line rewrites. The complete
assembled draft is checked after merging. Plan, source claim, and cover remain
outside this edit path. Repairs use the original writing provider so the later
independent critic cannot review its own partial rewrite. Three unchanged
fault signatures still stop the loop. Thirteen focused repair tests pass,
including the real researcher-in-Say defect, alongside 98 writer, 15 outcome,
and 91 message checks. No live model requests were used in those tests.
Plan-field repair remains release work; the isolated live draft-edit format
check was completed subsequently, as recorded below.

The existing full Python run completed successfully; logs are at
`/tmp/suresilly-tests-36967`. A subsequent release-path check found that
auto-post did not stage newly promoted mascot PNGs or `mascot/poses.json`.
Those files are now included before the state push and slot completion.
The regression test executes the workflow's actual staging loop in a temporary
Git repository and confirms that unrelated code changes are not staged.
All 38 posting-slot tests pass after the change. No model requests, deployment,
or publication were made for this check. This does not complete the release.

Background concept top-up and insights no longer suppress git add, commit,
pull, or push failures. A no-change save still succeeds. Top-up saves its
quota snapshot and neuron ledger even when discovery fails; failures retain
recovery files as workflow artifacts. Tests execute both actual save scripts
against temporary local git remotes, inject each of the four git failures,
and prove that usage/measurement records reach the remote on success.
All 48 posting-slot tests pass. The latest live check still reads `SS_HALT=1`;
the latest five GitHub runs are completed and use the old production code.

## 1. Production state and saved claims

Merged remote commit `db0f08d` without discarding local work. The retained stash
`before reliable-posts implementation: preserve user work` is the recovery copy.
The neuron ledger combines independent changes from the common base: local
9 text calls plus the remote 1-call increase gives 10; 777.32 plus 19.23 gives
796.55 text neurons. The quota snapshot uses the newer remote observation,
not an addition of two snapshots.

The rejected 20-word claim is now test evidence. The prompt, production check,
saved-data loader, insertion, update, and tests share an 18-word limit.
Pre-commit validation quarantines rejected content separately from usage data.
Per-claim source support records are implemented; evidence migration remains incomplete.

## 2. Workflow results and repairs

Added a final result record covering setup, tests, build, hosting, posting,
pruning, and state saving. A built deck is not a confirmed post. Missing post
credentials and publication IDs now fail. Test failures are captured as logs;
expected errors no longer become live annotations. Telegram link previews are
disabled. Broken tests and saved-data failures do not offer retry.

Auto-post, held-deck decisions, and insights share a state-writing concurrency
group. Both clocks now identify a date and 08:00/20:00 IST slot. A reservation
must be committed and pushed before dependency installation, tests, generation,
or top-up. Duplicate events skip generation and top-up. GitHub uses its original
run creation time, not a queued runner's start time; the Worker supplies its
scheduled time. A real two-checkout test proves a competing push cannot grant
two reservations. A failed push never emits permission to start work.

Telegram carries its stable update ID. Retry also carries the slot at the
message's original time, so redelivery cannot move it into a later slot. Held
commands reserve before resolving a blank deck ID: a repeated `publish` cannot
publish the next held deck. Force remains a manual held build, outside posting
slots. Explicit retry requires a saved, retryable generation result with no
publication. Failed tests, missing results, uncertain posting, held/built decks,
and repeated delivery do not authorize a new attempt.

Final automatic-run results are saved in the slot record after the main state
push. If that save fails, the run reports a state-saving failure. A reservation
left unfinished by a crash is not automatically released. Held-decision records
currently record receipt, not a structured final decision result; that remains
release work. Worker deployment, live duplicate-trigger verification, and the
full temporary-service retry budget also remain incomplete. A shared concurrency
group prevents overlap; it does not prove that every queued event runs.
The Worker no longer claims a command started when GitHub returns an error.
It reports the refusal and returns a failed delivery response; repeated delivery
keeps the same request ID. Scheduled dispatch failures also fail the Worker
invocation instead of being logged as a successful invocation. Background
vocabulary top-up now requires a successful run with a newly built deck.

Draft and plan repair loops stop after three identical fault signatures, not
three equal counts. Draft edits are field-limited and checked as described
above; plan-field repair remains to be implemented.

## 3. Artwork

The two supplied eye defects now fail the pixel gate. The three supplied bad
poses are preserved under `tests/fixtures/rejected_art`, outside the selectable
library. Eye failures block imports. Body instructions now require two arms and
two legs per character. The conservative pixel gate refuses four difficult
library poses; it does not override those failures.

Added a shared image-review path with body and enlarged upper-body views, at
most three candidates per request, and a real extra-leg control. The control
position changes with the candidates. Missing panel coverage, uncertain replies,
wrong panel numbers, or a missed control reject the whole group. One exact-model
call makes one HTTP request, without provider/key/model fallback or retry. Nine
candidates use at most three calls. Fresh artwork now uses this path. Tests prove
that an always-clear reviewer cannot release the supplied extra-leg image.

Model selection now requires replayable qualification evidence. A key alone is
not enough. The fixed set contains 20 visually reviewed clean poses plus the
three supplied defects. All three trials must be complete; every serious defect
must be detected, with at most one clean refusal out of 20 in each trial. The
result is recomputed from replies, not trusted from a saved pass flag. Code,
dependency, test-image, exact-model or inspection-sheet changes invalidate proof.
Fresh generation checks qualification before spending image quota.

Live qualification is NOT complete. Groq's old Scout model is absent from the
authenticated model list. Its replacement candidate, qwen/qwen3.6-27b, accepted
the images but missed the extra-leg control. Gemini 2.5 Flash also missed it;
its next test reached the daily free limit. Gemini 3.5 Flash missed it with
enlarged body details, explicit limb counts, and ultra-high image resolution.
The replies and failures are preserved in references/image_review_qualifications.
None of these attempts qualifies a reviewer. The current qualified-model list
is empty, and fresh image review readiness is false. Usage was recorded normally.
Qwen 3.8 27B was also verified on Groq's authenticated model list and tested with
medium reasoning. It returned two arms and two legs for the defective control,
with no faults. Qualification stopped after one request. Its response is saved
as `20260904-groq-qwen38-medium.json`; it is not eligible for production.

The inspection sheet now includes a full body, upper-body crop and lower-body
crop for each candidate. Observed counts are per character and can only add a
veto. Still required: qualification that succeeds on the full fixed set, a full library
audit, and quota-aware review reservation. These checks remain release blockers.

Pixel audit of all 198 saved PNGs found six failures: chasing, guarded, lab_coat,
and sulking failed eye checks; hoodie_drink and kaleidoscope failed palette
checks. Files were preserved, not deleted. `library.available()` now excludes
pixel failures, and generation references run the same saved-file pixel checks.
The cache is keyed by the image bytes and check source, so changing an image
does not reuse a previous pixel result. Passing these pixel checks is not body
approval. The complete evidence path has since been added, as described above.
Fresh encoded PNGs and exact imports now call the same saved-file pixel checker
as library selection and generation references. A shared refusal occurs before
the fresh PNG or library candidate is written. The cache also includes OpenCV
and NumPy versions. Invalid, empty, truncated and non-PNG input is rejected.
Sixty focused image tests passed, including byte/file parity and a dependency
version change invalidating the prior result.

Cloudflare's Llama 3.2 11B image model was tested once with the real inspection
sheet. It returned HTTP 403 requiring acceptance of the Meta community license
and use policy. No agreement was submitted. Evidence is saved as
`20260904-cloudflare-llama32-control.json`. This is an access prerequisite, not
evidence that the model can detect anatomy faults; it remains unqualified.

Pose selection was remeasured after excluding these files: 19/20 tuned examples
and 5/11 held-out examples matched the labelled choices. The suite's exit status
alone would hide this weakness; better matching remains release work.

## 4. Final rendering and publishing

Removed content-driven font resizing. The browser checks settled text bounds,
text/mascot overlap, images, missing copy, and contrast sampled against the actual
painted background. Fonts remain mandatory. All nine PNGs are staged and checked
before replacing an export. Failed rebuilds retain old images but block posting.
The posting script checks copy and PNG hashes, dimensions, completeness and the
render-failure marker. Preview decks without mascots cannot post.
Held release now requires a nonempty publication ID and matching deck name in
the saved publication record before removing the held record. A child process
that exits successfully without this proof no longer reports a confirmed post.
The 25 new pause and receipt tests pass; the existing 14 run guards and 22
Telegram command checks also pass. These are local tests, not live publication.

Reduced grain strength and corrected measured palette/card-label contrast faults.
New library candidates are imported only after the complete render, and only
from the current attempt. Candidates now preserve the exact reviewed RGBA PNG
bytes, not the raw frame. Exact import runs all pixel gates but cannot matte,
crop, mirror, recolour or override a fault. All candidate hashes must match
before any candidate reaches the importer. The import reads one byte snapshot,
so a file changed during checking cannot replace the checked image. In run.py,
novelty now runs before rendering and fresh generation, not after library
promotion. A repeated deck cannot spend fresh-image quota or add library art.
The shared body eligibility record described above now supplements these checks.
The builder's old `--generate` and `--model` paths are removed. Both now refuse
before bootstrap, renderer imports, image requests or writes. The live builder
does not import the obsolete mascot module. Eight regression cases cover this
boundary, and the carousel skill instructions now describe the removed flags.
A browser matrix covers ten templates and fourteen
palettes; separate tests cover nine-file promotion, long/hidden/missing copy,
wide/tall art and edits after inspection. Cross-platform pinned screenshot
baselines, missing-font/image fault injection and full end-to-end release tests
remain to be completed. Surface sampling is not proof of all possible defects.

## 5. Content and release — not complete

The local writer now starts the cover with a scene, allows an empty pattern
name, and keeps optional labels off both cover lines. The hook chooser applies
the same rule as plan validation and stops if no valid hook exists; it no longer
falls back to a failed candidate. Source application no longer has to repeat an
invented name. The old named-skill subtitle axis now promises a useful skill,
without changing the axis key or the deterministic draw.

The local bibliography now fetches passages from catalogue-linked scans and
uses a passage-grounded independent veto with an unsupported control. New
claims require separate hashed support records; updates retain prior records.
Legacy claims remain stored for audit but are not selectable. Selected claim
indices stay unchanged. Both drafting and publication recheck the exact claim,
including force and old held decks. The 24-book, 53-claim pool currently has no
passage records, so none of those claims can generate a post. An actual scan
request returned HTTP 403; no source was accepted and no access restriction was
bypassed. See `docs/claim-support-proof.md`. Restoring usable, genuinely supported
source coverage and testing real source/claim pairs remain release work.

The active content playbook and brand guidance no longer claim proven viral
hooks, ranked engagement scores or unsupported share multipliers. The playbook
states the nine slide jobs and distinguishes the target from implementation.
These edits are local, not live. Still required: complete scene/tool validation,
precise slide-role checks and supported source coverage. Outline and draft
field-only repair are now implemented and checked locally.
Fixed-age reporting is now implemented as described above. A prompt is not proof that a
model will follow the specification or that an invented label cannot be
presented as a medical fact elsewhere in the deck.

Do not label this checkpoint as the complete plan. After the remaining work:
run the complete suites, qualify the live free reviewers, audit fallback art,
run isolated non-posting builds, deploy the workflow inputs before the matching
Worker changes, and observe
seven days of normal runs. No seven-day observation has started.

Checkpoint verification: the complete Python suite runner passed on 2026-09-04;
the browser suite passed 147 tests and the Worker parser passed 32 tests.
All three changed workflow YAML files parsed, and `git diff --check` passed.
Full Python logs are in `/tmp/suresilly-tests-4772`. These local checks are not
a deployed workflow test, model qualification, or the seven-day observation.

After the bounded image-review changes, all 36 Python suites passed again.
Logs: `/tmp/suresilly-tests-13735`. This includes the real-extra-leg always-clear
regression, missing control/coverage and uncertainty checks, nine-image request
limits, and exact Gemini model/key request limits. No live image calls were made
by these tests, so they do not qualify a production reviewer.

Qualification-stage verification: the full 37-suite runner passed at
`/tmp/suresilly-tests-19642` before the saved-library filtering change. After
that change, 83 generation/reference tests passed, 76 focused artwork tests
passed, and the selection script completed (accuracy reported above). The
qualification suite was rerun after adding the wink and partly covered eye to
the fixed clean set. No full-suite pass after the library change is claimed.

Latest double check, 4 September 2026: the complete Python runner passed after
the library filtering and publication-pause changes. Logs:
`/tmp/suresilly-tests-40969`. All 32 Worker parser checks passed; all three
workflow files parsed; `git diff --check` passed. GitHub still has `db0f08d`,
`SS_HALT` is `1`, and no running or queued jobs were found. The list of qualified
image reviewers is still empty. Deployment and seven-day observation remain
incomplete. These results do not establish production readiness.

Slot-stage verification: all 40 Python suites passed at
`/tmp/suresilly-tests-76094`. The 37 slot tests also passed after the final
workflow conditions changed. The Worker suites now pass 56 checks, including
failed GitHub dispatches. No live workflow was dispatched, no new code was
deployed, and no post was published by these tests. The changes still require
isolated live verification with posting paused.

Exact-image handoff verification: all 41 Python suites passed at
`/tmp/suresilly-tests-83661`. The new 15-test suite exercises unchanged PNG
bytes through the real importer, source replacement during checking, a changed
candidate blocking the whole import, real bad eyes, forbidden transformations,
and novelty refusal before rendering. The existing fresh/import checks also
pass. No new generation, library audit, model qualification or deployment was
performed in that earlier check. The evidence path has since been added;
the actual model qualification and library audit remain open.

Obsolete-path check: 50 focused tests passed after removing the old builder path.
The skill validator found old frontmatter fields outside its supported schema.
Author and version now live under `metadata`; the redundant true invocation
flag was removed, preserving normal default invocation. The updated commands
were tested against the real builder argument parser.
The skill validator now passes. All 42 Python suites passed at
`/tmp/suresilly-tests-1544`; the expanded exact-image transport suite passed
27 checks separately. Qwen 3.8's failed live control test remains preserved,
not replaced by these offline passes. No new code was deployed.

Shared-pixel-stage verification: all 42 Python suites passed at
`/tmp/suresilly-tests-7264`. The 60 focused image checks passed separately.
Cloudflare's agreement was not accepted; owner authorization was requested for
that optional test. Other release work is not blocked by this decision. No
production-ready claim, deployment, or normal-operation restart was made.

Scene-first checkpoint: all 43 Python suites passed at
`/tmp/suresilly-tests-10350`. The 13 scene-first tests passed separately after
the final guidance edit. They cover unnamed plans, optional labels explained
later, rejection of labels on either cover line, consistent hook selection,
no fallback to a failed hook, and removal of unsupported engagement claims.
The existing writer suite passes 98 checks. No model request, deployment or
publication was performed. This proves the local boundaries, not the quality
of a complete generated post or the remaining source-support rules.

Source-boundary checkpoint: all 44 Python suites passed at
`/tmp/suresilly-tests-14214`. After the final source-date and publication changes,
57 focused source, claim-boundary and pause checks passed. The source suite has
28 cases, including a synthetic candidate-to-store path, wrong-book and
changed-claim rejection, exact source quotes, missed controls, uncertain replies,
old claims excluded before drafting, retained original indices, force refusal,
and old held-deck checks before network access. These fixtures are not real
source evidence. No model terms were accepted, no new code was deployed, and
no post was published.

Live source transport now has one successful catalogue-to-review trial, saved
outside the active pool at
`docs/claim-support-trials/20260904-james-second-nature-spacing.json`.
Earlier refused trials remain alongside it. The live exercise found and fixed
provider tuple membership, vague review IDs, unquoted phrase searches and OCR
whitespace mismatches. Exact words and punctuation remain mandatory. Only
temporary HTTP failures retry; another catalogue-linked edition can be tried
within the original two-scan bound. No borrowed/private content was unlocked.
Active source coverage remains zero; this trial is not a publishable claim pool
or evidence of a complete post. See `docs/claim-support-proof.md`.

Source-recovery verification: all 45 Python suites passed at
`/tmp/suresilly-tests-24953`; 47 focused source and transport checks also passed.
The live successful source record replayed against the current validator.
No active citation was added, no post was published and no deployment occurred.

The final live negative trial also behaved correctly: Groq rejected a claim
that reversed the passage's meaning about whether practice can change a habit.
Its rejected evidence is saved in
`docs/claim-support-trials/20260904-james-negated-claim.json`.
After preserving specific refusal reasons, all 48 focused source/transport
checks passed. The 45-suite run above preceded that final message-only change.
These two real claim checks are useful evidence, not a complete source-review
qualification set or proof of normal production operation.
