# Leave automatic posting paused

Checked on 4 September 2026. **Not ready for production.**

Last full double check: all 56 Python suites and all 56 Worker checks passed locally.
`git diff --check` passes. GitHub still runs `db0f08d`; `SS_HALT` is `1`.
No running or queued jobs were found. No image reviewer is qualified.
Python test logs: `/tmp/suresilly-tests-78051`.
This full run includes the shared artwork, render assets, hosted images,
publication recovery, outline repair and performance checks.
The 147 browser checks pass. The later import-preview adjustment also passed its
53 focused import and artwork checks.
The active pool still has **0 supported claims** and **0 qualified image reviewers**.
The complete image check now reports **0 eligible library images**. Saved images
are no longer treated as checked merely because they are in the library.
Passing these tests does not remove those release blockers.
These checks did not publish a post, deploy changes, or accept model terms.

The later performance-report change passed 18 new checks plus the existing
insights, wiring and affected workflow checks. It compares readings at 72–73
hours and leaves missing numbers blank. There are no saved readings yet.
It is not deployed, and the live reporting permission is not yet verified.

Outline repair now preserves clean fields and the chosen source. Its focused
checks passed; a full live generation run remains unverified.

The latest render double check passed 155 tests, plus 18 publication checks and
28 workflow wiring checks. Missing or broken fonts and images stop the export
without replacing the previous complete slides. The running browser must match
the bundled version. Changed render code, fonts or render dependencies require
a new render. These are local results, not a deployed release. A fixed Linux
visual baseline still needs verification.

The held-post workflow now installs the required checks. Publication also checks
all nine hosted images against the checked local files before contacting
Instagram. The 56 affected checks pass, including the four previously failing
publication tests. These changes are not live yet.

Cloudflare now reserves usage before each request and keeps room for its image
checks before drawing. The focused tests pass without model calls. This does
not accept the model terms or qualify an image reviewer. Gemini/Groq fresh art
also requires a recent remaining-quota report for the exact reviewer. Unknown
allowance uses checked library art; Gemini's current call tally cannot prove
remaining quota. The remaining release checks are still unfinished.

## Your steps — about 1 minute

1. Open [GitHub's saved settings](https://github.com/mayankav/ig-work/settings/variables/actions). Leave `SS_HALT` set to `1`. I checked it: it is already correct.
2. Do not send `retry`, `force`, or `publish` in Telegram. The old live code can still publish a held deck through a separate path.
3. Do not upload these local changes as a finished release. No new key, account, or payment is needed for the faults found in this check.

If the pause setting is missing, click **New repository variable**. Copy these values:

Name:
```text
SS_HALT
```

Value:
```text
1
```

Click **Add variable**. If `SS_HALT` already exists, edit it instead.

This stops new automatic posting jobs. It does not cancel a job that has already
started. No running or queued jobs were found during the last live check.

## One optional decision: test Cloudflare's image reviewer

All configured Gemini and Groq image models have now failed a qualification
trial. The latest two each missed the known extra leg and were stopped after
one request. Cloudflare is the remaining configured candidate that has not
been tested. No image model is currently qualified for production.

Cloudflare refused the test because Meta's model terms have not been accepted.
I have not accepted them. Acceptance only lets the test run; the model can still
fail the image checks.

1. Read the [Llama 3.2 license](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE) and [use rules](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/USE_POLICY.md).
2. If you accept both and authorize me to submit the agreement for your account, copy this reply:

   ```text
   I accept the Llama 3.2 license and use rules. Submit the agreement for my Cloudflare account and test the image reviewer. Keep posting paused.
   ```

   Otherwise reply:

   ```text
   Keep the Cloudflare image model disabled.
   ```

Other repair work can continue without this decision.

## Work still assigned to me

1. Qualify an image reviewer and check the saved library. The shared evidence check is now connected to fresh art, imports, fallback selection, references, rendering and publishing. The tested live reviewers still miss the extra leg; none has passed qualification.
2. Prove the new repeated-run protection on the live system. Verify usable source passages for claims and finish useful-tool checks. The 53 older claims are now excluded from new drafts until checked. Scene-first covers and the new source checks pass local tests, but are not live.
3. Finish the release tests, install the changes on the live services, and prove a full run without posting. Then observe seven days of normal runs.

The new pause and confirmed-publication checks pass locally. They are not live
yet. GitHub still uses `db0f08d`. Its [latest posting run](https://github.com/mayankav/ig-work/actions/runs/33787629521)
failed because a saved claim had 20 words against an 18-word limit.

Passing local tests alone does not prove that the full system is ready.

One public-source trial has passed and is saved outside the posting pool.
It proves that the source path can work. It does not yet supply the range of
checked claims needed for normal posts.

Next: leave `SS_HALT` at `1`. Choose whether to permit the optional model test above.
