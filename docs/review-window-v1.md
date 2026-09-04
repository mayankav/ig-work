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
- [x] Python and Worker tests and deployment.
- [x] Six source-supported claims cover all eight content topics; old unsupported claims remain excluded.
- [x] First live preview accepted by Telegram (message 68, run 33895172712).
- [ ] Owner reply tests and Instagram publication remain unconfirmed. The preview contains unsupported claims and must not publish.

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

## Validation and live result

- 65 local Python suites passed, including the earlier research suites. All Worker suites passed.
- A real Chromium render and slide-4 replacement preserved the markdown and the other eight PNGs byte for byte.
- 84 recovery/slot tests passed after adding recovery of an unbuilt stopped slot with changed code; 75 focused tests passed after adding saved-preview recovery.
- GitHub main contains the release. Worker deployment: `79c49bfb-85ce-48f4-81e5-13c4d58096b8`. The live private endpoint rejects unauthenticated requests and reaches durable storage with authentication.
- GitHub variables: `SS_REVIEW_WINDOW_V1=1`; `REVIEW_WINDOW_URL=https://suresilly-dispatch.mayankav.workers.dev`. The shared secret is configured in both services.
- Live recovery: https://github.com/mayankav/ig-work/actions/runs/33891116582 . All CI tests passed. The builder found usable artwork, composed and safety-checked a burnout moment, then stopped because no source-supported claim was available. No deck, preview timer or Instagram post was created. The failure notification was accepted by Telegram.
- Citation inventory: 53 saved claims, zero current `claim_support` records. A direct source check for Christina Maslach's *The Truth About Burnout* (1997), Open Library work `/works/OL2528268W`, found its catalogue-linked scan, but the excerpt request returned HTTP 403. The access restriction was not bypassed.

Source recovery: six new claims have exact public publisher passages and independent control-tested reviews. All 66 local Python suites passed. See `docs/source-audit/README.md`. Recovery run: https://github.com/mayankav/ig-work/actions/runs/33895172712 . Live outcomes must still be recorded; passing code tests does not prove publication.


## Whole-deck source correction

The first live V1 preview exposed a content error: the deck claimed that minor tasks drain energy and naming a completed task reduces that drain. The verified Nagoski passage supports neither claim. The reviewer had not received the passage and its instructions exempted some uncited everyday claims.

The reviewer now receives the exact source evidence and checks factual effects throughout the carousel and caption. The same live deck was rejected by Groq in a real recheck; the response is in `docs/source-audit/live-deck-recheck.json`. Writer instructions now forbid invented causes and promised effects. A saved whole-deck review is bound to the markdown, source record and current review code. V1 publication requires that record. Old previews without it stay blocked; changing artwork alone cannot fix unsupported text.

Telegram accepted the preview and a later correction explaining the content hold. The owner signed in to Telegram. Their approve command reached the Worker and dispatched run 33896305256; it stopped before upload because the temporary pause was active. A real disapprove command then closed the preview; the bot confirmed cancellation. The pause was lifted after release 39a5ba0. Replacement recovery run 33896861923 uses the previously failed morning slot. The shared Cloudflare ledger reached 9,928.68 of 10,000 daily free neurons, leaving less than one 114.84-neuron image request. No paid use was enabled. Slide regeneration needs the next allowance. Code tests are separate from these pending live checks.


## Live verification at 22:30 IST

- Source release: `70afc0a`; whole-deck review release: `39a5ba0`; clear action errors: `9c0e460`, all pushed to main.
- All 67 local Python suites and all Worker suites passed after the content changes. The latest recovery also passed its GitHub code tests.
- Preview delivery: confirmed. Owner approval: received and dispatched. Its upload was blocked by the temporary pause before anything reached Instagram.
- Cancellation: confirmed through the real Telegram conversation and successful run 33896847387. The old preview is cancelled, not waiting. `SS_HALT=0` restores the normal schedule.
- Replacement run 33896861923 stopped during writing, before rendering or review delivery. Its three revisions had 8, 8, 8 faults. The saved result names repeated headings and prompt copying. The full rejected edit responses were not retained, so the exact cause of no progress is not proved. No identical retry was started.
- Still unconfirmed: successful full redo, successful slide-image redo, automatic publication after a real hour, Instagram post ID/permalink and Telegram delivery of that permalink. No completion claim is made.
- Next work: retain draft/repair responses on failure and inspect the rejected edits without starting another full posting run. Resume image testing after the free allowance resets; do not enable paid services or weaken checks.


## Owner policy update: approval is final

The owner clarified that approval must be the last content decision. All factual/source, pixel and final-render checks now run before hosting and sending a preview. The publication path checks the frozen manifest, hosted bytes and live decision; it does not re-run source, style, image or render judgments. Caption text is frozen with the nine images. New check code or source records cannot veto unchanged approved content.

V1 makes at most three draft attempts. Remaining style problems are saved as review notes alongside the preview; the owner can approve, cancel or redo. The existing factual/harm critic still runs before preview. Grammar-only prompt matches such as “do not have to” no longer count as copied content; informative copied phrases still fail. Other modes retain their prior behavior.

Every notification includes a resource report or an explicit unavailable reading. A preview has a companion resource message. Gemini shows recorded requests by model and its Pacific-day reset, without inventing an unreported ceiling. Groq shows the vendor's last request/token balances and their observation/refill timestamps. Cloudflare shows the shared recorded usage and UTC reset. Instagram's publishing-limit endpoint is queried when credentials are available; the returned limit is used without a fixed assumed ceiling. Telegram does not report a daily remaining allowance. Failures of resource reporting do not block a post.

Validation covers style-note fallback, fixed captions, no quality recheck in the real publisher entry point, unknown quotas, dated snapshots and rolling refill times. Live verification is still required after deployment.
