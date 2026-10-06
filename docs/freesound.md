# Freesound sounds for the A or B Reel

The evening Reel gets its effects (a tick for each count, a chime at the reveal, a page turn at the cut...)
and, when the words call for it, one accent sound (a phone ring, a coin clink) and a quiet background bed.
`suresilly/sfx.py` fetches them from Freesound on the fly, for each Reel, and mixes them under our own tune.

## What it asks for

- **Creative Commons 0 only.** No credit is needed. The search filter says so, and the code also checks each
  result's own licence before it uses the sound.
- **The preview file** (a 128 kbps mp3), not the original. It is enough for a Reel and needs no login.
- **About 15 searches and 15 downloads per Reel (the beat and the impact are always built in)**, in parallel, within a 45 second budget. Freesound's limit is
  60 requests a minute and 2000 a day, so two Reels a day use a small part of it.
- **If anything fails** (no key, no answer, no fitting sound, too slow) that sound is the built-in one
  (`synth.py`). The post is never held up and never fails because of Freesound.

## What you do once

1. Make a free account at freesound.org.
2. Ask for an API key at https://freesound.org/apiv2/apply and copy the key.
3. In the repo's GitHub settings, add a secret named `FREESOUND_API_KEY` (Settings, Secrets and variables, Actions).
4. For runs on your own computer, add `FREESOUND_API_KEY=...` to `.env.local`.

Without the key everything still works, with the built-in sounds only.

## How to check what it used

- `post.json` keeps `reel.sounds`: for each sound, its role, its Freesound id, name, author, licence and link.
  `reel.sound_notes` says why a role fell back (for example "tick: no CC0 sound fits").
- The Telegram card says how many sounds came from Freesound ("🔊 9 of 13 sounds from Freesound").
- You hear the whole Reel in Telegram before it can post, so a sound you dislike can be sent back with
  `redo images 1`, which picks new poses of Silly and new sounds.

## To change what it looks for

Edit `ROLES` (what to search for, how long, how loud) and `THEMES` (words that call up an accent sound and a bed)
in `suresilly/sfx.py`.

## Two things to know

- **API terms.** Freesound's own terms say the website is not for commercial use. I did not find the API's
  rule on commercial use. If the page earns money, read Freesound's API terms of use first.
- **A wrong upload.** A sound marked CC0 can still have been uploaded by someone who does not own it. Each
  sound's id and author are saved in `post.json`, so a complaint can be answered and the sound removed.
