# Claim support — local release work

Checked on 4 September 2026. Posting remains paused. These changes are not live.

## What changed

1. The catalogue supplies the work ID and scan IDs. A model cannot choose a
   source URL. Only public passages from those scans are requested.
2. An independent reviewer receives the passages, the exact claim and a known
   unsupported control. Missing coverage, uncertainty, an invented quote, a
   missed control or a veto rejects the claim. No passage means no review call.
3. Each claim retains its own passages, page links, review, reviewer identities
   and content hash. Adding another claim cannot replace the first claim's proof.
4. New inserts and updates require this evidence. Existing claims without it
   remain saved for audit but are excluded from new draft selection. Original
   claim indices are retained, so filtering cannot select another sentence.
5. The draft and publishing boundaries recheck support. This also applies to
   force and to old held decks. The printed source and sentence must match.

The book-level verified flag is no longer sufficient for selection or insertion.
The basic saved-data reader still permits legacy records for audit; it does not
make those records eligible. No legacy claim has been given invented proof.

## Live check

The Open Library catalogue returned the selected book's work and scan IDs.
Internet Archive metadata returned its data host and path. The public passage
request for that scan returned HTTP 403. It was not accepted as source evidence.
No access restriction was bypassed. No model request was made for this check.

The transport follows the [Open Library individual-book search documentation](https://openlibrary.org/dev/docs/api/search_inside).
That API is experimental. A documented request is not proof of live availability.

## Successful public-source trial

The public James scan `principlesofpsyc01jame` returned whole passages through
the documented API. A later complete catalogue-to-review trial selected another
catalogue-linked edition, `theprinciplesofp0000unse`, and also returned a passage.
No login, loan, payment or access workaround was used.

Four trials are preserved under `docs/claim-support-trials/`:

1. `20260904-james-second-nature.json`: refused for missing review coverage.
2. `20260904-james-second-nature-exact.json`: refused because a quote used single
   spaces while the OCR text used double spaces. The text and reply are retained.
3. `20260904-james-second-nature-spacing.json`: passed the corrected source check.
   Groq inspected both claims, vetoed the unsupported control and returned a
   matching source quote. The saved record was replayed successfully.
4. `20260904-james-negated-claim.json`: the claim was changed to say the habit
   cannot change with practice. Groq rejected it because the passage says
   training can undo it. Both that claim and the unsupported control were vetoed.

The implementation now uses exact phrase search, requests explicit highlight
markers, and normalizes whitespace only when matching quotes. It does not drop
words, negation or punctuation. Reviewer membership is checked against the
actual `(name, callable)` provider records, not against a list of strings.
Tests now use the production provider shape. Denied HTTP requests are not
retried; a separate catalogue-linked edition may be tried within the two-scan
limit. Temporary service errors get at most one retry.
Claim refusals now retain the reviewer's specific reason instead of reporting
an ambiguous claim-or-control failure.

The successful trial is outside the active citation pool and has no content
pillar assigned. It demonstrates the source path, not a finished relational
post or complete source coverage. The earlier failures have not been rewritten
as successes. Real provider usage from these trials remains in the quota log.

## Remaining release evidence

The saved pool contains 24 books and 53 claims, with zero passage-based support
records. They are not selectable until audited. Restore a sufficient set of
supported claims using accessible source material before enabling posting.

Unit tests use explicitly synthetic passages in temporary or in-memory fixtures.
They prove transport, storage and refusal behavior, not the truth of real claims.
A matched quote and a reviewer veto test reduce risk; they do not guarantee
that every inference is correct. Real source/claim pairs still need verification,
including negation, scope, causation, missing context and misleading attribution.

No complete supported nine-slide run, deployment or seven-day observation is
claimed here.
# Publisher route check — 4 September 2026

The official Guilford page provides a chapter excerpt for *The Mindful
Self-Compassion Workbook*, Neff and Germer (2018), ISBN 9781462526789.
The web reader returned the chapter, but a direct Python request to the PDF
returned HTTP 403. The initial URL without `?t=1` was an HTML download-tracking
page, not a PDF; its own redirect was followed, without changing identity or
credentials. No access restriction was bypassed.

Open Library's page for the same ISBN lists 2016, unlike the publisher's 2018
date. The direct catalogue API connection also failed during this check.
Exact edition verification and automatic passage ingestion remain unresolved.
No claim was reviewed by a model, inserted into the pool or declared supported.
The evidence is in `docs/claim-support-trials/20260904-publisher-route.json`.

This route is a possible source, not a working production source. Do not replace
the missing passage evidence with a search snippet or treat HTTP 200 HTML as a
downloaded PDF.
