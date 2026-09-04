"""The saved-data boundary must reject bad inserts AND bad updates."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bibliography as bib
from support_fixture import with_support


def test_word_boundary():
    bib.check_claim_is_falsifiable(" ".join(["plain"] * bib.CLAIM_WORD_CAP))
    with pytest.raises(bib.Unverified, match="19 words"):
        bib.check_claim_is_falsifiable(" ".join(["plain"] * (bib.CLAIM_WORD_CAP + 1)))
    assert f"{bib.CLAIM_WORD_CAP} words or fewer" in bib.PROPOSE_SYSTEM


@pytest.mark.parametrize("update", [False, True])
def test_bad_store_leaves_file_unchanged(tmp_path, monkeypatch, update):
    path = tmp_path / "citations.json"
    monkeypatch.setattr(bib, "CITATIONS_PATH", path)
    good = {"id": "book", "claims": ["A plain claim."], "pillars": ["trust"],
            "verified": {"catalogue": "openlibrary"}}
    path.write_text(json.dumps({"citations": [good] if update else []}))
    before = path.read_bytes()
    bad = copy.deepcopy(good)
    bad["claims"] = json.loads((Path(__file__).parent / "fixtures/rejected_claims.json").read_text())["claims"]
    with pytest.raises(bib.Unverified):
        bib.store(bad)
    assert path.read_bytes() == before


def test_valid_update_preserves_old_claim(tmp_path, monkeypatch):
    path = tmp_path / "citations.json"
    monkeypatch.setattr(bib, "CITATIONS_PATH", path)
    one = {"id": "book", "claims": ["First claim."], "pillars": [], "verified": {}}
    bib.store(with_support(one))
    bib.store(with_support({**one, "claims": ["Second claim."]}))
    assert bib.load_pool()[0]["claims"] == ["First claim.", "Second claim."]
