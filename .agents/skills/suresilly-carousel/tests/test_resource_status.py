"""Resource figures must keep their unit, timestamp and uncertainty."""
import sys
from pathlib import Path
from datetime import datetime,timezone
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'scripts'))
import resource_status as resources
NOW=datetime(2026,9,4,17,0,tzinfo=timezone.utc)

def test_unknown_is_not_zero():
    text=resources.report({}, {},NOW,{})
    assert 'remaining unknown' in text and 'unknown/unknown' in text
    assert '05 Sep 2026 05:30 IST' in text
    assert '05 Sep 2026 12:30 IST' in text

def test_shared_usage_and_reported_refill():
    vendors={'groq':{'model':'test-model','observed_at':'2026-09-04T16:00:00Z','requests':{'remaining':900,'limit':1000,'reset_seconds':8640}}}
    ledger={'2026-09-04':{'neurons':200,'text_neurons':9700}}
    text=resources.report(vendors,ledger,NOW,{'instagram':{'quota_usage':3,'config':{'quota_total':50,'quota_duration':86400}},'observed_at':'2026-09-04T16:00:00Z'})
    assert '9,900.00/10,000' in text and '100.00 left' in text
    assert '900/1000 left at that reading' in text
    assert '04 Sep 2026 23:54 IST' in text
    assert '3/50 posts used; 47 left' in text
    assert 'no fixed daily reset' in text
