# Recover a failed posting slot

A slot claim means that work started. It does not mean that Instagram has a post.
The saved result records the failed stage, deck name, code revision, and whether
Instagram confirmed a post. Each recovery adds an attempt. It never deletes history.

## Install the changes

Push the checked code and workflow files to `main`. Then deploy
`ops/dispatch-worker` with `wrangler deploy`. A commit alone does not update the
Worker. The Worker now labels clock requests so duplicate clock events stay
quiet while new requests from a person get an answer. Until it is deployed,
old clock requests can produce a blocked-request alert; they still cannot post
twice.

## Start recovery

In GitHub Actions, open **auto-post → Run workflow** and set:

- `mode`: `publish`
- `slot_id`: the exact failed slot, such as `2026-09-03_2000`
- `recover`: `true`
- `retry`: `false`

Use the current `main` branch. Recovery accepts slots less than seven days old.
Ordinary new work keeps the one-day limit. The previous run must have finished
and saved a failed result. A missing result requires manual investigation.

If setup or tests failed before a deck existed, recovery requires a change to
code or test files. A state-only commit does not count. All checks run again.
Old records without a revision use the earlier GitHub run's revision.

If a deck exists, recovery downloads that run's `recovery-deck` artifact. The
artifact is retained for 14 days. Recovery checks the exact copy, image evidence,
and final export. Missing files or changed checks stop recovery. There is no
fallback that writes a replacement deck. A held deck still requires its separate
`publish` decision.

## Check an uncertain post

A saved `published.json` confirms that the deck already posted. Recovery sends
nothing more. Otherwise, a saved `publication_pending.json` identifies the
original Instagram container and the files used for it.

Recovery checks that container and the account's media list. A unique full-caption
match at or after the request time, allowing five minutes for clock differences,
recovers the post ID. If Instagram reports `FINISHED`, recovery can publish only
the original container. It never creates a replacement container for an uncertain
request. Missing, expired, conflicting, or unreadable results stop recovery.

The media scan is capped at 20 pages of 100 items. Reaching that cap stops recovery;
an incomplete scan is not proof that no post exists.

## Messages

A new manual request that cannot start sends a **NO NEW WORK STARTED** message.
It includes the earlier run, its result, the next action, and what silence does.
Repeated clock deliveries stay quiet. Use a new recovery request after a fix;
rerunning the same GitHub run does not grant a second slot claim.

Telegram success requires `ok=true` and a message ID. Each message part gets at
most three attempts. A retry repeats only the failed part. Waiting is capped at
30 seconds per retry; a longer server-requested delay stops retries in that run.
A network timeout can cause a repeated Telegram message if the first request was
accepted but its response was lost. It can never cause a repeated Instagram post.

The `message-delivery-<run-id>` Actions artifact holds safe receipts, including
message IDs and attempt results. It contains no message body or bot token.
Acceptance by Telegram does not prove that a phone displayed a notification.

## Pool refill

**Keep the concept pool ready** runs daily at 05:00 IST and can also run manually.
It does not require a built deck. It checks how many concepts remain outside the
recent-use window. Below 14 ready concepts, it can scan up to 250 terms and prove
up to 25. The pool ceiling is 60 before a refill; one batch can take it above 60.

The usual top-up after each fifth deck remains. Both paths share the same
24-hour refill claim and workflow lock. The claim is pushed before vendor calls,
so a failed or repeated run cannot cause rapid refill attempts. The halt switch
applies to both paths. No existing used-moment records are reset.
