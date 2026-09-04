from pathlib import Path
import sys,copy
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import publisher_sources as source
import claim_support


def test_excerpt_excludes_praise_and_other_panels():
    html='<div>Praise</div><div class="book-detail-excerpt">Real <i>book</i><div>words</div>here.</div><div>Reviews</div>'
    assert source.excerpt(html)=='Real book words here.'
    with pytest.raises(ValueError):source.excerpt('<div>No excerpt</div>')


def test_actual_registry_matches_proof_and_changed_source_is_rejected(monkeypatch):
    entry=source.entries()['nagoski-burnout-excerpt'];book=entry['book']
    class Response:
        status_code=200
        text='<h1>Burnout</h1>'+entry['isbn']+'<div class="book-detail-excerpt">'+entry['passages'][0]+'</div>'
        content=text.encode()
    monkeypatch.setattr(source.requests,'get',lambda *a,**k:Response())
    evidence=source.fetch('nagoski-burnout-excerpt',book);source.validate(evidence,book)
    altered=copy.deepcopy(evidence);altered['passages'][0]['text']='invented quote'
    with pytest.raises(ValueError):source.validate(altered,book)
    with pytest.raises(ValueError):source.validate(evidence,{**book,'work_key':'/works/OL123W'})
    Response.status_code=403
    with pytest.raises(ValueError,match='403'):source.fetch('nagoski-burnout-excerpt',book)


def test_another_book_with_same_words_is_rejected(monkeypatch):
    entry=source.entries()['nagoski-burnout-excerpt']
    class Response:
        status_code=200;text='<h1>Another Book</h1>'+entry['isbn'];content=text.encode()
    monkeypatch.setattr(source.requests,'get',lambda *a,**k:Response())
    with pytest.raises(ValueError,match='different book'):source.fetch('nagoski-burnout-excerpt',entry['book'])


def test_control_still_required_for_publisher_quotes():
    payload={'passages':[{'text':'A source passage with enough words.'}]}
    with pytest.raises(claim_support.Unsupported,match='control'):
        claim_support.check_reply({'inspected':['claim','control'],'uncertain':[],'vetoes':[],
                                  'quotes':[{'passage':0,'text':'A source passage with enough words.'}]},payload)
