"""V1 authority and immutable media; no network or committed state writes."""
import base64
import json
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import owner_art
import review_window as window
import art_eligibility

@pytest.fixture
def deck(tmp_path, monkeypatch):
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1', '1')
    root=tmp_path/'deck';root.mkdir();(root/'slides').mkdir()
    for name in ('carousel.md','contact_sheet.png','slides/checks.json'):
        (root/name).write_bytes(b'fixture')
    for i in range(1,10): (root/'slides'/f'{i:02d}.png').write_bytes(str(i).encode())
    window.prepare(root)
    return root

def test_exact_manifest(deck):
    first=window.read(deck)
    (deck/'slides/04.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):window.read(deck)
    second=window.prepare(deck,parent=first['token'])
    assert second['token'] != first['token']
    assert second['manifest'] != first['manifest']
    assert second['parent']==first['token']

@pytest.mark.parametrize('name',['published.json','publication_pending.json'])
def test_publication_cannot_be_replaced(deck,name):
    (deck/name).write_text('broken marker')
    with pytest.raises(ValueError,match='existing Instagram'):window.prepare(deck)

@pytest.mark.parametrize('change', [dict(state='waiting'),dict(claimed=False),dict(manifest='changed'),dict(action={'decision':'redo','id':'action'}),dict(action={'decision':'publish','id':'old'})])
def test_only_live_exact_publish_claim(deck,monkeypatch,change):
    record=window.read(deck);remote={'manifest':record['manifest'],'state':'working','claimed':True,'action':{'decision':'publish','id':'action'}}
    monkeypatch.setenv('REVIEW_ACTION_ID','action');monkeypatch.setattr(window,'api',lambda *a:remote)
    base=f'https://media.suresilly.com/slides/deck/reviews/{record["token"]}/slides'
    assert window.require_publication(deck,base)==remote
    remote.update(change)
    with pytest.raises(ValueError,match='no live publication'):window.require_publication(deck,base)

def test_wrong_host_rejected_before_service_call(deck,monkeypatch):
    api=Mock();monkeypatch.setattr(window,'api',api)
    with pytest.raises(ValueError,match='URL'):window.require_publication(deck,'https://media.suresilly.com/slides/deck')
    api.assert_not_called()

def test_pixel_checks_cannot_be_bypassed(monkeypatch):
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1','1')
    monkeypatch.setattr(owner_art.art_checks,'pixel_faults_bytes',lambda raw:('text in image',))
    with pytest.raises(ValueError,match='text in image'):owner_art.proof(b'image')

def test_changed_proof_and_disabled_policy(monkeypatch):
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1','1')
    monkeypatch.setattr(owner_art.art_checks,'pixel_faults_bytes',lambda raw:())
    record=owner_art.proof(b'image');assert owner_art.check(record)==b'image'
    record['png']=base64.b64encode(b'new image').decode()
    with pytest.raises(ValueError):owner_art.check(record)
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1','0')
    with pytest.raises(ValueError,match='requires'):owner_art.check(record)

def test_changed_check_code_invalidates_proof(monkeypatch):
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1','1');monkeypatch.setattr(owner_art.art_checks,'pixel_faults_bytes',lambda raw:())
    proof=owner_art.proof(b'image');monkeypatch.setattr(owner_art,'contract',lambda:'new code')
    with pytest.raises(ValueError,match='changed'):owner_art.check(proof)


def test_redo_generator_does_not_receive_old_image(monkeypatch,tmp_path):
    import cv2
    import numpy as np
    import poses_flux as flux
    import fresh_poses
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1','1')
    old=b'old artwork'; identity=b'character reference'
    monkeypatch.setattr(flux,'pick_references',lambda **kw:[('old',old),('identity',identity)])
    monkeypatch.setattr(flux,'credentials',lambda:('account','key'))
    monkeypatch.setattr(flux,'assert_no_text',lambda *a:None)
    monkeypatch.setattr(flux,'correct_palette',lambda x:x)
    monkeypatch.setattr(fresh_poses,'_matte',lambda x:cv2.cvtColor(x,cv2.COLOR_BGR2BGRA))
    monkeypatch.setattr(owner_art,'proof',lambda raw:{})
    image=cv2.imencode('.png',np.zeros((20,20,3),dtype=np.uint8))[1].tobytes()
    generate=Mock(return_value=(image,1));monkeypatch.setattr(flux,'generate',generate)
    ledger=Mock()
    path=owner_art.generate_one({'mascot':'A donkey sits beside a chair and looks at a door.'},tmp_path/'new.png',previous=old,ledger=ledger)
    assert generate.call_args.args[1]==[('identity',identity)]
    assert 'chair' in generate.call_args.args[0]
    assert path.read_bytes()!=old
    ledger.spend.assert_called_once()


def test_redo_service_failure_leaves_no_replacement(monkeypatch,tmp_path):
    import poses_flux as flux
    monkeypatch.setenv('SS_REVIEW_WINDOW_V1','1')
    monkeypatch.setattr(flux,'pick_references',lambda **kw:[('identity',b'ref')])
    monkeypatch.setattr(flux,'credentials',lambda:('account','key'))
    monkeypatch.setattr(flux,'generate',Mock(side_effect=RuntimeError('service failed')))
    path=tmp_path/'replacement.png'
    with pytest.raises(RuntimeError,match='service failed'):
        owner_art.generate_one({'mascot':'A donkey sits beside a chair and looks at a door.'},path,previous=b'old',ledger=Mock())
    assert not path.exists()


@pytest.mark.parametrize('stage',['owner_preview','owner_archive','owner_host','owner_delivery'])
def test_failed_preview_is_not_reported_as_waiting(stage):
    sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'scripts'))
    import run_result
    value=run_result.result({'build':{'outcome':'success'},stage:{'outcome':'failure'}},
        mode='publish',slug='deck',verdict='held',reason='',retry=False,published=None)
    assert value['outcome']=='error'
    assert value['fault_code']==stage+'_failed'
    assert value['held'] is False
