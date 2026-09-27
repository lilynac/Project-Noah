import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from src import video_vision as vision
from src.companion import CompanionStore

URL='https://www.youtube.com/watch?v=abcdefghijk'


def frames():
    return [{'id':f'f{i}','at':30+i*3,'jpeg':b'\xff\xd8'+b'0'*200+b'\xff\xd9','sha256':'abc'} for i in range(3)]


@pytest.mark.parametrize('url',['file:///etc/passwd','http://x.googlevideo.com/v','https://googlevideo.com.evil.test/v',
    'https://a@x.googlevideo.com/v','https://x.googlevideo.com:123/v','https://127.0.0.1/v'])
def test_media_source_rejects_non_provider_urls(url):
    assert not vision.trusted_media_url(url)


def test_sampling_is_silent_bounded_and_cleans_files(monkeypatch):
    paths=[]
    def run(args,**kwargs):
        if '--get-url' in args:
            assert '--ignore-config' in args and '--no-plugin-dirs' in args
            return NS(stdout=b'https://x.googlevideo.com/v?signature=private')
        assert '-an' in args and '-nostdin' in args
        assert args[args.index('-frames:v')+1]=='1'
        assert kwargs['timeout']==25
        p=Path(args[-1]);paths.append(p);p.write_bytes(frames()[0]['jpeg'])
    monkeypatch.setattr(vision.subprocess,'run',run)
    result=vision.sample_frames(URL,30)
    assert [f['at'] for f in result]==[30,33,36]
    assert len(paths)==3 and all(not p.exists() for p in paths)
    assert all(len(f['sha256'])==64 for f in result)


def test_invalid_timestamp_or_cancellation_never_fetches(monkeypatch):
    run=Mock();monkeypatch.setattr(vision.subprocess,'run',run)
    for at in (-1,float('nan'),float('inf'),86401,'30'):
        assert vision.sample_frames(URL,at)==[]
    assert vision.sample_frames(URL,30,lambda:True)==[]
    run.assert_not_called()


def test_frames_require_complete_set_and_valid_media_host(monkeypatch):
    run=Mock(return_value=NS(stdout=b'https://localhost/video'))
    monkeypatch.setattr(vision.subprocess,'run',run)
    assert vision.sample_frames(URL,30)==[]
    assert run.call_count==1


def client(approved=True,ids=None):
    note={'eligible':True,'frame_ids':ids or ['f0'],'observation':'口が上向きに描かれている',
          'expression_idea':'返答時の口の形の案','limits':'声色や実際の感情は分からない'}
    return NS(responses=NS(create=Mock(side_effect=[NS(output_text=json.dumps(note)),NS(output_text=json.dumps({'approved':approved}))])))


def test_visual_evidence_review_and_no_image_persistence():
    api=client();result=vision.analyze_frames(api,frames())
    assert result['frame_ids']==['f0']
    assert 'jpeg' not in json.dumps(result)
    first=api.responses.create.call_args_list[0].kwargs
    assert len([c for c in first['input'][1]['content'] if c['type']=='input_image'])==3
    assert first['store'] is False
    assert vision.analyze_frames(client(approved=False),frames()) is None
    assert vision.analyze_frames(client(ids=['invented']),frames()) is None
    assert vision.analyze_frames(client(),frames()[:2]) is None


def test_visual_job_records_separately_and_runs_once(tmp_path,monkeypatch):
    store=CompanionStore(tmp_path/'state.json')
    original={'id':'n','url':URL,'at_seconds':30,'access':'字幕のみ','prototype':'台詞'}
    store.change(lambda s:s.update(video_learning_enabled=True,video_visual_enabled=True,video_observations=[original]))
    sampler=Mock(return_value=frames());monkeypatch.setattr(vision,'sample_frames',sampler)
    vision.run_visual_research(store,client(),lambda:1)
    saved=store.snapshot()['video_observations'][0]
    assert saved['access']=='字幕のみ' and saved['prototype']=='台詞'
    assert saved['visual']['access']==vision.ACCESS
    assert store.snapshot()['conversation_trials']==[]
    vision.run_visual_research(store,client(),lambda:2)
    assert sampler.call_count==1


def test_disabled_and_cancelled_visual_jobs_do_not_fetch(tmp_path,monkeypatch):
    store=CompanionStore(tmp_path/'state.json')
    sampler=Mock();monkeypatch.setattr(vision,'sample_frames',sampler)
    vision.run_visual_research(store,client(),lambda:1)
    store.change(lambda s:s.update(video_learning_enabled=True,video_visual_enabled=True))
    vision.run_visual_research(store,client(),lambda:1,lambda:True)
    sampler.assert_not_called()


def test_failed_frames_do_not_claim_visual_learning(tmp_path,monkeypatch):
    store=CompanionStore(tmp_path/'state.json')
    store.change(lambda s:s.update(video_learning_enabled=True,video_visual_enabled=True,
        video_observations=[{'id':'n','url':URL,'at_seconds':30}]))
    monkeypatch.setattr(vision,'sample_frames',lambda *args:[])
    api=client();vision.run_visual_research(store,api,lambda:1)
    note=store.snapshot()['video_observations'][0]
    assert '映像未確認' in note['visual_status'] and 'visual' not in note
    api.responses.create.assert_not_called()
