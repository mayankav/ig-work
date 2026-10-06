# Cloud sprint: write a month of @suresilly India Reels

You are Claude in a cloud session on this repo (branch `feat/india-two-beat`). You have no API keys and no web keys. Do not ask for any. Never print or commit secrets.

## Goal
Write 30 ready-to-review Reel scripts for first-job India (age 18 to 30). Silly is the green mascot; never call Silly a donkey. Two thirds speak to the employee, one third (at least 10) teach managers and bosses to be professional. Managers in India are pushy; the content must show that honestly.

## Rules
1. Read `suresilly/script.py` (templates: mirror, contrast, can_they, story, news), `suresilly/reeltypes.py`, `suresilly/craft.md`, `AGENTS.md` and `docs/` first.
2. Evergreen types only: mirror, contrast, can_they. No news items.
3. Facts about law, pay, PF, notice or leave must come from an official site (`suresilly/sources.json`, `official_domains`). If you cannot open the page, write the script as "reasoned": no source named, no number except a time.
4. Own views are marked ("it may", "often"). No first-person claims ("my boss told me").
5. No phrase banks, no stock fallbacks. Each script is its own idea.
6. Each script must pass the checks in `script.py` (run `python -m pytest -q` and the script checker for each one).
7. Nothing goes live. Save to `stock/evergreen/<slug>.json` in the shape `script.py` writes.

## Output
Commit in batches of 5. Last, write `stock/evergreen/INDEX.md`: one line per script (type, audience, hook, status verified or reasoned). Then stop and wait for the owner.
