"""Whole-deck source evidence must survive text, source and code changes."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import content_review as review

@pytest.fixture
def deck(tmp_path,monkeypatch):
    (tmp_path/'carousel.md').write_text('A checked deck')
    monkeypatch.setattr(review,'source_record',lambda md:{'sha256':'source','claim':'bounded claim','source':{'passages':[{'text':'exact passage'}]}})
    review.save(tmp_path,'gemini','publish',85,'No veto',[])
    return tmp_path

def test_missing_evidence_blocks(tmp_path):
    with pytest.raises(ValueError,match='Missing'):review.validate(tmp_path)

def test_changed_text_blocks(deck):
    (deck/'carousel.md').write_text('Now promises a cure')
    with pytest.raises(ValueError,match='changed'):review.validate(deck)

def test_changed_source_blocks(deck,monkeypatch):
    monkeypatch.setattr(review,'source_record',lambda md:{'sha256':'another source'})
    with pytest.raises(ValueError,match='changed'):review.validate(deck)

def test_changed_check_blocks(deck,monkeypatch):
    monkeypatch.setattr(review,'contract',lambda:'new check')
    with pytest.raises(ValueError,match='changed'):review.validate(deck)

def test_rejected_review_cannot_be_saved(deck):
    with pytest.raises(ValueError,match='did not pass'):review.save(deck,'gemini','block',30,'Unsupported effect',[])

def test_passage_reaches_reviewer(deck):
    assert 'exact passage' in review.context('A checked deck','A scene')
    assert review.validate(deck)['outcome']=='publish'


def test_style_notes_do_not_block_preview(deck):
    review.save(deck,'gemini','review',70,'Tone could improve',[],style_notes=['Repeated heading'])
    assert review.validate(deck)['style_notes']==['Repeated heading']


def test_source_concern_can_reach_owner_but_harm_cannot(deck):
    issues=[{'category':'H3_FALSE_PSYCH','slide':6,'quote':'A pause reduces threats','why':'No support'}]
    assert review.owner_decidable('block',issues)
    review.save(deck,'gemini','block',30,'No support',issues)
    assert review.validate(deck)['outcome']=='owner_review'
    assert not review.owner_decidable('block',issues+[{'category':'H1_HARM_ADVICE'}])
    assert not review.owner_decidable('block',[])
