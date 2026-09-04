import sys
from pathlib import Path
import html
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'scripts'))
import review_report
TOKEN='a'*16

def test_complete_report_and_commands():
    data={'outcome':'owner_review','style_notes':['same heading'],'objections':[{'slide':6,'category':'H3_FALSE_PSYCH','quote':'A <pause> helps','why':'No evidence'}]}
    pages=review_report.pages(TOKEN,data,'https://example.com')
    text=html.unescape('\n'.join(pages))
    for expected in ('stays paused','Slide 6','A <pause> helps','No evidence','same heading','images 2,4,7','images all','No partial replacement','Text problems need full redo'):
        assert expected in text
    assert 'H3_FALSE_PSYCH' not in text
    assert all(len(p)<3900 and 'Review ID: '+TOKEN in p for p in pages)

def test_long_findings_are_never_dropped():
    notes=[str(n)+': '+('&<>"'*1000) for n in range(12)]
    pages=review_report.pages(TOKEN,{'style_notes':notes},'https://example.com')
    assert all(len(p)<3900 for p in pages)
    text=html.unescape(''.join(pages))
    for n in range(12):assert str(n)+': ' in text

def test_clean_review_retains_hour():
    assert 'one hour' in '\n'.join(review_report.pages(TOKEN,{},'https://example.com'))
    assert len(review_report.caption(TOKEN,True))<1000
