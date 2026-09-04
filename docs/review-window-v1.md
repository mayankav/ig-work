# Version 1: Telegram review window

User-approved behaviour, 4 September 2026:

1. Build a new carousel with strict content checks and practical artwork checks.
2. Deliver its preview to Telegram. Confirm Telegram acceptance before starting a one-hour deadline.
3. Approval publishes; disapproval cancels only this carousel. Silence publishes after the deadline and sends the Instagram link.
4. Full redo retires the current carousel and starts an unrelated concept/content/deck. Slide redo creates a new contextual image from scratch, using no pixels from the previous slide image; content and other images remain unchanged.
5. Every successful redo receives a new preview token and a fresh hour. Failed redo remains held. Old replies and timers cannot affect the replacement.

Implementation:
- [x] Durable review decisions and one-hour alarm, with immediate cancellation of queued automatic posts.
- [x] Explicit V1 artwork policy, generation and render evidence.
- [x] Build/host/preview integration and immutable revision artifacts.
- [x] Review actuator for approve, cancel, full redo and slide redo.
- [ ] Python and Worker tests, deployment and live verification.

No existing experiment records, slot history or publication receipts may be reset. Existing force-held decks are not silently enrolled in timeout publication. A confirmed or uncertain Instagram upload must be reconciled before redo/cancel changes its deck.

## Owner commands
Reply to the preview message with `approve`, `disapprove`, `redo`, or `redo 4`.
If not replying to the preview, include its 16-character Review ID: `redo <id> 4`.
`redo` changes the whole concept and content. `redo 4` changes only slide 4's image.
The hour starts after Telegram accepts the preview. Queue or service delays can make publication later than the deadline.

## Release and recovery
Set the same `REVIEW_WINDOW_SECRET` in GitHub Actions and the Worker. Set the GitHub variable `REVIEW_WINDOW_URL` to the Worker URL. Deploy the SQLite Durable Object migration, then set `SS_REVIEW_WINDOW_V1=1` in GitHub variables.
Keep the existing content, citation, pixel and final-render checks. V1 image records explicitly identify owner review; they never claim model approval. Legacy force-held decks retain their separate rules.

Each preview has an immutable hosted revision, exact-byte manifest, 14-day recovery artifact and a durable decision. A successful redo replaces its token and starts a new hour only after the new preview is delivered. A failed redo has no automatic publication deadline. The old concept remains in the used ledger so a cancelled deck cannot return as a future post.

The decision workflow claims the exact action before starting work. Replies can replace a queued action. Once work has started, the bot reports that the preview is closed. Instagram publication cannot be recalled by a late reply.

An unresolved Instagram upload uses the existing publication reconciliation path. A rerun after confirmed publication only retries delivery of the Instagram link. It cannot publish a second post. Telegram acceptance is saved; it does not prove that a phone displayed a notification.
