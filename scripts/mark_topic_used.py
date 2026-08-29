#!/usr/bin/env python3
import datetime, os
from pathlib import Path
p = Path('.agents/skills/suresilly-carousel/references/topic-bank.md')
slug = os.environ.get('TOPIC','')
if not slug:
    print("TOPIC env missing")
    raise SystemExit(1)
d = datetime.datetime.utcnow().strftime('%Y%m%d')
lines = p.read_text().splitlines()
out = []
for line in lines:
    if line.startswith('|') and f'| {slug} |' in line:
        parts = line.split('|')
        if len(parts) >= 10:
            parts[9] = f' {d} '
            line = '|'.join(parts)
    out.append(line)
p.write_text('\n'.join(out) + '\n')
print(f'Marked {slug} as used {d}')
