# One attempt per posting slot

Status: local implementation only. Posting remains paused.

## What the code enforces

1. Both clocks address `YYYY-MM-DD_0800` or `YYYY-MM-DD_2000`, in India time. The Worker uses the trigger's scheduled time. GitHub uses the run's original creation time and cron, not the time a queued job starts.
2. The workflow pushes a record under `state/slots/` before it can use provider quota. A failed state push gives no permission to start. A duplicate skips the build and vocabulary top-up.
3. A retry needs a saved generation result that explicitly permits retry and confirms no publication. Missing results, test errors, posting errors, held decks and completed builds block retry.
4. Telegram's update ID follows the command. Its original message time fixes a retry's slot. Repeated delivery cannot create a second attempt or move a blank `publish` command to another held deck.
5. A crash leaves its reservation in place. Do not delete it to retry blindly. First establish whether any work or publication occurred.

Manual build and force commands use separate request records. Force still cannot
publish. The existing safety and image checks are unchanged.

## Tests

`test_posting_slots.py` includes real temporary Git repositories: one remote and
two competing checkouts. It checks that only the first reservation reaches the
remote and that a rejected push never emits `accepted=true`. It also checks
duplicate schedules, repeated Telegram IDs, midnight boundaries, stale/future
slots, invalid state, retry restrictions, ownership of results, and preservation
of unrelated edits. All test state stays in temporary directories.

The Worker tests exercise real handlers with intercepted HTTP requests. No live
workflow is dispatched by those tests.
The Python runner passed all 40 suites; its logs are at
`/tmp/suresilly-tests-76094`. The slot suite passed 37 tests after the last
workflow edit. The Worker passed 56 checks. A failed GitHub dispatch now gets
a failure response, not a false acknowledgement that work started.

## Still required before release

The workflow and Worker must be deployed together, with the new workflow inputs
installed first. Keep `SS_HALT=1` until isolated live tests are complete. The
held-decision path still needs its structured final result. Complete recovery
after ambiguous publication and the bounded service retry policy remain open.

GitHub's scheduled event does not supply the intended date separately. The code
uses the most recent occurrence of that cron before run creation. It handles
queue delays and overnight arrivals, but cannot recover an intended date from a
schedule event delayed by more than a full day. The independent Worker supplies
an explicit date; workflow dispatches older than a day are refused.

The Worker time field is documented in the
[Cloudflare scheduled handler reference](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/).
