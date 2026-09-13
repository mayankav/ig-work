"""Keep the Instagram and Threads tokens alive, so nobody has to make new ones.

Meta tokens die 60 days after they were made or last renewed, and there is no
token that lasts forever. So the 08:00 and 20:00 runs renew any token whose
repo secret is more than a week old, and save the new one over the secret.
Saving a secret needs SECRETS_PAT: a GitHub token that can write this repo's
secrets and nothing else. Without it, this does nothing.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import requests

# secret name: (renewal endpoint, grant type). Only Instagram-login tokens (IGAA…) renew this way.
RENEW = {
    "IG_ACCESS_TOKEN": ("https://graph.instagram.com/refresh_access_token", "ig_refresh_token"),
    "THREADS_ACCESS_TOKEN": ("https://graph.threads.net/refresh_access_token", "th_refresh_token"),
}
EVERY = timedelta(days=7)


def _gh(*args: str, stdin: str | None = None) -> str:
    env = {**os.environ, "GH_TOKEN": os.environ["SECRETS_PAT"]}
    done = subprocess.run(["gh", *args, "--repo", os.environ["GITHUB_REPOSITORY"]], input=stdin,
                          capture_output=True, text=True, env=env, timeout=60)
    if done.returncode != 0:
        raise RuntimeError(f"GitHub refused `gh {args[0]} {args[1]}`: {done.stderr.strip()[:200]}")
    return done.stdout


def due(now: datetime | None = None) -> list[str]:
    """The token secrets last saved more than a week ago."""
    now = now or datetime.now(timezone.utc)
    saved = {row["name"]: datetime.fromisoformat(row["updatedAt"].replace("Z", "+00:00"))
             for row in json.loads(_gh("secret", "list", "--json", "name,updatedAt"))}
    return [name for name in RENEW if name in saved and now - saved[name] > EVERY]


def renew(name: str) -> None:
    """Swap the token for a fresh 60-day one and save it over the secret. The token is never printed."""
    token = os.environ.get(name, "")
    if name == "IG_ACCESS_TOKEN" and not token.startswith("IGAA"):
        return  # a Facebook-login token renews differently; leave it alone
    url, grant = RENEW[name]
    response = requests.get(url, params={"grant_type": grant, "access_token": token}, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {}
    fresh = body.get("access_token", "")
    if response.status_code != 200 or not fresh:
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        raise RuntimeError(f"Meta said HTTP {response.status_code}: {error.get('message') or 'no new token'}")
    _gh("secret", "set", name, stdin=fresh)


def keep_alive() -> list[tuple[str, str]]:
    """Renew whatever is due. Returns (secret, reason) for each one that could not be renewed."""
    if not os.environ.get("SECRETS_PAT"):
        print("SECRETS_PAT is not set, so the tokens are not renewed automatically.")
        return []
    problems = []
    for name in due():
        try:
            renew(name)
            print(f"Renewed {name}; it now lasts 60 more days.")
        except Exception as error:
            problems.append((name, str(error)[:300]))
    return problems
