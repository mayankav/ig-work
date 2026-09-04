"""Restore only the checked files of an earlier deck. Never generate new copy."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from posting_slots import ROOT, safe_id, output


def restore(source: Path, root: Path, slug: str) -> None:
    deck = root / 'carousels' / safe_id(slug)
    if (root / 'state/pending' / f'{slug}.json').exists():
        raise ValueError('This deck is held for review. Use the separate publish decision.')
    if source.is_symlink() or not source.is_dir():
        raise ValueError('The saved deck is missing.')
    files = list(source.rglob('*'))
    if any(p.is_symlink() for p in files):
        raise ValueError('The saved deck contains a link.')
    # Publication records belong to committed state, never to an older artifact.
    ignored = {'published.json', 'publication_pending.json'}
    report = json.loads((source / 'slides/checks.json').read_text())
    md = source / 'carousel.md'
    if hashlib.sha256(md.read_bytes()).hexdigest() != report.get('markdown_sha256'):
        raise ValueError('The saved copy does not match its render check.')
    if (deck / 'carousel.md').exists() and (deck / 'carousel.md').read_bytes() != md.read_bytes():
        raise ValueError('The saved copy was changed. Recovery cannot replace it.')
    for p in files:
        if p.is_file() and p.name not in ignored:
            dest = deck / p.relative_to(source)
            if dest.is_symlink() or any(a.is_symlink() for a in dest.parents):
                raise ValueError('The deck path contains a link.')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
    from post_to_ig import check_export
    check_export(deck, deck / 'carousel.md')


def main():
    slug, run = safe_id(os.environ['RESUME_SLUG']), safe_id(os.environ['RESUME_RUN'])
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['gh', 'run', 'download', run, '--repo', os.environ['GITHUB_REPOSITORY'],
                        '--name', 'recovery-deck', '--dir', tmp], check=True)
        restore(Path(tmp), ROOT, slug)
    output(slug=slug, deck=f'carousels/{slug}/carousel.md')


if __name__ == '__main__':
    main()
