"""Reserve a bounded concept refill, including when no deck can be built."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from posting_slots import ROOT, persist, output
sys.path.insert(0, str(ROOT / '.agents/skills/suresilly-carousel/scripts'))

LOW_POOL = 14
MAX_POOL = 60
COOLDOWN = timedelta(hours=24)


def due(*, total, available, decks, previous, now, low_only=False):
    if previous:
        stamp = datetime.fromisoformat(previous['attempted_at'])
        if stamp.tzinfo is None or now - stamp < COOLDOWN:
            return False
    cadence = (not low_only and decks > 0 and decks % 5 == 0
               and previous.get('decks') != decks)
    return total < MAX_POOL and (available < LOW_POOL or cadence)


def main():
    from run_control import pause_reason
    if pause_reason():
        output(due='no', note='Refill paused.')
        print('Refill paused.')
        return
    import discovery
    import memory
    path = ROOT / 'state/maintenance/concept-topup.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    pool, recent = discovery.load_pool(), set(discovery.recent())
    total, available, decks = len(pool), sum(c['id'] not in recent for c in pool), memory.used_count()
    now = datetime.now(timezone.utc)
    wanted = due(total=total, available=available, decks=decks, previous=previous, now=now,
                 low_only='--low-only' in sys.argv)
    if wanted:
        # Save before vendor calls. A crash cannot make every next run spend again.
        persist(ROOT, path, dict(slot_id='concept-topup', attempted_at=now.isoformat(),
                                 decks=decks, available=available, total=total))
    output(due='yes' if wanted else 'no', note=f'{decks} decks, {available} ready concepts, {total} total')
    print(f'Refill {"due" if wanted else "not due"}: {available} ready concepts, {total} total.')


if __name__ == '__main__':
    main()
