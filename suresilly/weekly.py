"""The weekly report: what the inbox found, as a short Telegram card and a full-list page, and which buttons are worth showing.

The card follows the three-things rule: what happened, what you can tap, and what happens if you stay quiet. A button is shown
only when it can help: re-running the same search straight away finds nothing new (the seen list blocks repeats), so "retry"
appears only when a source failed and "look wider" only when the good items are fewer than the slots.
"""
from __future__ import annotations

import html
import json
from datetime import datetime

from . import inbox, telegram
from .inbox import SLOTS_A_WEEK

SHAPE = {"event": "news", "story": "story", "rule": "rule", "other": "other"}


def actions(report: dict) -> list[tuple[str, str]]:
    """(button label, callback data) for this report. Every action starts with `stock:` and carries what to do."""
    buttons = [("Use my picks", "stock:picks")]
    if report.get("below_cut"):
        buttons.append(("Show below the cut", "stock:below"))
    if report.get("failed_feeds"):
        buttons.append(("Retry the failed source", "stock:retry"))
    if report.get("kept", 0) < SLOTS_A_WEEK:
        buttons.append(("Look wider", "stock:wider"))
    return buttons


def _short(title: str, size: int = 62) -> str:
    return title if len(title) <= size else title[:size - 1].rstrip() + "…"


def _sources_line(report: dict) -> str:
    named = [s["name"] for key in ("feeds", "pages", "searches") for s in inbox.SOURCES.get(key, [])]
    failed = report.get("failed_feeds", {})
    ok = [name for name in named if name not in failed]
    others = len([n for n in report.get("per_source", {}) if n not in named])
    line = f"{len(ok)} of {len(named)} sources answered" + (f", plus {others} more sites found by search" if others else "")
    if failed:
        gave_up = set(report.get("gave_up", []))
        names = ", ".join(f"{html.escape(n)}{' (gave up)' if n in gave_up else ' (retry tomorrow)'}" for n in failed)
        line += f". Failed: {names}"
    return line + "."


def card(report: dict, page_url: str = "", when: str = "Monday 08:00 IST") -> tuple[str, list[list[tuple[str, str]]]]:
    """The Telegram message and its buttons. `page_url` is the full-list page; without one the card lists more items itself."""
    kept = report["kept"]
    lines = [f"🗞 <b>Weekly stock: {kept} ready for {SLOTS_A_WEEK} slots</b>",
             f"<i>Read {report['collected']} items. {report.get('first_cut', 0)} passed the first cut. {kept} kept.</i>",
             "", _sources_line(report), ""]
    shown = report["stock"][:5 if page_url else 8]
    for number, item in enumerate(shown, 1):
        lines.append(f"{number}. {telegram.esc(_short(item['title']))} <i>· {telegram.esc(item['source'])} · {SHAPE.get(item.get('story_kind'), 'other')}</i>")
    if kept == 0:
        lines.append("Nothing passed the cut this week.")
    lines += ["", "Tap a button. " + (f"If you stay quiet, I use my picks from {when}." if kept else
                                      "If you stay quiet, nothing is planned for next week and the slots wait for new items.")]
    buttons = actions(report)
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if page_url:
        rows.insert(0, [("Open full list", page_url)])
    return "\n".join(lines), rows


def page(report: dict) -> str:
    """The full-list page: every kept item and the ones just under the cut, with filters. Read-only; the buttons live in Telegram."""
    data = json.dumps({"at": report["at"], "kept": report["stock"], "below": report.get("below_cut", []),
                       "collected": report["collected"], "per_source": report.get("per_source", {}),
                       "failed": report.get("failed_feeds", {})}, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data)


def write_page(report: dict, folder) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page(report))
    (folder / "stock.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly stock</title><style>
:root{--bg:#f4f6f5;--card:#fff;--fg:#17201c;--muted:#5d6a64;--line:#d9dfdc;--good:#1f7a4d;--accent:#2c6b4f;--warn:#a05a00}
@media (prefers-color-scheme:dark){:root{--bg:#131815;--card:#1b221e;--fg:#e7ede9;--muted:#9aa8a1;--line:#2c3732;--good:#6fd39b;--accent:#6fd39b;--warn:#f0b35a}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:16px;max-width:760px;margin-inline:auto}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin:0 0 12px}
.bar{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0;position:sticky;top:0;background:var(--bg);padding:8px 0}
button{font:inherit;font-size:13px;padding:5px 12px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;cursor:pointer}
button[aria-pressed=true]{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:10px}
.top{display:flex;justify-content:space-between;gap:10px}.t{font-weight:600}.s{font-size:12px;color:var(--good);white-space:nowrap}
.m{font-size:12px;color:var(--muted);margin:2px 0 6px}.a{font-size:14px}a{color:var(--accent)}
.warn{color:var(--warn);font-size:13px}.note{color:var(--muted);font-size:12px;margin-top:14px}
</style></head><body>
<h1>Weekly stock</h1><p class="sub" id="sub"></p><p class="warn" id="warn"></p>
<div class="bar" id="bar"></div><div id="list"></div>
<p class="note">Read-only. Keep, drop and pin are tapped in Telegram.</p>
<script id="d" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('d').textContent);let f='all';
const E=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const age=iso=>{if(!iso)return 'date not given';const h=Math.max(0,(new Date(D.at)-new Date(iso))/36e5);return h<1?'under an hour ago':h<48?Math.round(h)+' hours ago':Math.round(h/24)+' days ago'};
document.getElementById('sub').textContent='Read '+D.collected+' items. '+D.kept.length+' kept, '+D.below.length+' just under the cut.';
const fl=Object.entries(D.failed);if(fl.length)document.getElementById('warn').textContent='Failed: '+fl.map(x=>x[0]).join(', ');
const kinds=[['all','All'],['story','Story'],['rule','Rule'],['event','News'],['below','Below the cut']];
const bar=document.getElementById('bar');
kinds.forEach(([k,l])=>{const b=document.createElement('button');b.textContent=l;b.setAttribute('aria-pressed',k===f);b.onclick=()=>{f=k;[...bar.children].forEach(x=>x.setAttribute('aria-pressed',x===b));draw()};bar.appendChild(b)});
function draw(){const rows=f==='below'?D.below:D.kept.filter(i=>f==='all'||i.story_kind===f);
document.getElementById('list').innerHTML=rows.length?rows.map(i=>'<div class="item"><div class="top"><div class="t"><a href="'+E(i.link)+'" rel="noopener">'+E(i.title)+'</a></div><div class="s">score '+E(i.score)+'</div></div><div class="m">'+E(i.source)+' · '+age(i.published)+' · '+E(i.story_kind)+((i.also||[]).length?' · also: '+E(i.also.join(', ')):'')+'</div><div class="a">'+E(i.angle)+'</div></div>').join(''):'<p class="note">Nothing here.</p>'}
draw();
</script></body></html>
"""
