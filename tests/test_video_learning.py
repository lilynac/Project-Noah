import json
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from src.companion import CompanionStore
from src.companion_life import CompanionLife
from src import video_learning as video

URL = 'https://www.youtube.com/watch?v=abcdefghijk'

@pytest.mark.parametrize('url', ['http://youtube.com/watch?v=abcdefghijk', 'https://evil.test/watch?v=abcdefghijk',
    'https://youtube.com.evil.test/watch?v=abcdefghijk', 'https://a@youtube.com/watch?v=abcdefghijk',
    'https://youtube.com:123/watch?v=abcdefghijk', 'file:///etc/passwd', 'https://youtube.com/playlist?list=xx'])
def test_video_urls_reject_non_video_and_untrusted_hosts(url):
    assert video.canonical_video(url) is None


def test_video_url_normalizes_tracking_and_shortlinks():
    assert video.canonical_video('https://youtu.be/abcdefghijk?t=50') == URL
    assert video.canonical_video(URL+'&tracking=x') == URL


def rows():
    return [{'id':f's{i}', 'at':i*2, 'text':'相手の感想に短い感想を返す会話。'} for i in range(8)]


def test_caption_parser_keeps_times_and_bounds_and_deduplicates():
    raw = json.dumps({'events':[{'tStartMs':i*1000,'segs':[{'utf8':f'{i}番目の発言の内容が続いている。'}]} for i in range(1000)]})
    result = video.parse_captions(raw)
    assert len(result) <= 105
    assert sum(len(r['text']) for r in result) <= 6500
    assert result[0]['at'] == 0 and result[-1]['at'] > 600
    assert video.parse_captions('{"events":[]}') == []


def test_caption_command_only_downloads_subtitles(tmp_path, monkeypatch):
    def run(args, **kwargs):
        assert '--skip-download' in args and '--ignore-config' in args and '--no-plugin-dirs' in args
        assert '--cookies-from-browser' not in args
        assert kwargs['timeout'] == 75
        path = args[args.index('-o')+1].replace('%(ext)s','ja.json3')
        from pathlib import Path
        Path(path).write_text(json.dumps({'events':[{'tStartMs':i*1000,'segs':[{'utf8':f'{i}発言の内容をここに記載しています。'}]} for i in range(10)]}))
    monkeypatch.setattr(video.subprocess, 'run', run)
    assert len(video.read_captions(URL)) == 10
    assert video.read_captions('https://127.0.0.1') == []


def test_discovery_diversifies_and_never_sends_private_preferences(monkeypatch):
    entries=[{'id':'abcdefghijk','title':'対談','channel':'A'},
             {'id':'bbcdefghijk','title':'対談2','channel':'A'},
             {'id':'cbcdefghijk','title':'対談3','channel':'B'}]
    runner=Mock(return_value=NS(stdout=json.dumps({'entries':entries}).encode()))
    monkeypatch.setattr(video.subprocess,'run',runner)
    client=Mock()
    assert len(video.discover(client, [])) == 2
    client.responses.create.assert_not_called()
    assert 'ytsearch9:' in runner.call_args.args[0][-1]


def analysis_client(window='w0', approved=True, preference='p'):
    note={'eligible':True,'window_id':window,'observation':'感想を返し合う',
          'technique':'share_without_question','preference_id':preference,'fit_reason':'追加の質問を避けたい希望に合う',
          'prototype':'その色の感じ、わたしも気になる。','use_when':'短い感想','avoid_when':'作業依頼'}
    return NS(responses=NS(create=Mock(side_effect=[NS(output_text=json.dumps(note)),NS(output_text=json.dumps({'approved':approved}))])))


def test_analysis_requires_real_evidence_and_review():
    state={'video_preferences':[{'id':'p','text':'質問を重ねないで'}],'conversation_trials':[]}
    assert video.analyze(analysis_client(window='invented'),{'url':URL},rows(),state) is None
    assert video.analyze(analysis_client(approved=False),{'url':URL},rows(),state) is None
    note=video.analyze(analysis_client(),{'url':URL},rows(),state)
    assert note['evidence_times'] == [i*2 for i in range(8)]
    assert note['preference']['id'] == 'p'
    assert video.analyze(analysis_client(preference='invented'),{'url':URL},rows(),state)['preference'] is None


def test_cannot_join_distant_caption_excerpts():
    data=rows()
    for r in data[2:]: r['at'] += 600 * int(r['id'][1:])
    client=Mock()
    assert video.analyze(client,{},data,{'conversation_trials':[]}) is None
    client.responses.create.assert_not_called()


def test_schedule_caps_survive_restart_and_disable(tmp_path):
    store=CompanionStore(tmp_path/'state.json')
    now=datetime(2026,9,26,9).timestamp()
    assert store.claim('video',now) is None
    store.set_enabled('video_learning_enabled',True)
    assert store.claim('video',now)
    assert CompanionStore(store.path).claim('video',now+60) is None
    assert store.claim('video',now+6*3600)
    store.change(lambda s:s.update(next_video_at=0))
    assert store.claim('video',now+7*3600) is None
    assert store.snapshot()['daily']['video'] == 2


def test_observation_starts_bounded_trial_only_with_preference(tmp_path):
    store=CompanionStore(tmp_path/'state.json')
    state={'video_preferences':[{'id':'p','text':'質問を重ねないで'}],'conversation_trials':[]}
    note=video.analyze(analysis_client(),{'url':URL},rows(),state)
    candidate={'url':URL,'title':'対談'}
    store.save_video_candidate(candidate,'字幕確認',1,{**note,'preference':None})
    assert not store.snapshot()['conversation_trials']
    other={'url':URL.replace('abcdefghijk','bbcdefghijk'),'title':'別の対談'}
    store.save_video_candidate(other,'字幕確認',2,note)
    trial=store.snapshot()['conversation_trials'][0]
    for i in range(3): store.record_turn('感想','返事',3+i,trial_id=trial['id'])
    assert store.snapshot()['conversation_trials'][0]['status'] == 'awaiting_feedback'
    store.save_video_candidate(other,'字幕確認',8,note)
    assert len(store.snapshot()['video_observations']) == 2
    store.evaluate_trial(trial['id'],'stopped',9)
    store.save_video_candidate({'url':URL.replace('abcdefghijk','cbcdefghijk'),'title':'三本目'},'字幕確認',10,note)
    assert len(store.snapshot()['conversation_trials']) == 1


def test_unavailable_captions_never_analyzed_or_learned(tmp_path, monkeypatch):
    store=CompanionStore(tmp_path/'state.json'); store.set_enabled('video_learning_enabled',True)
    monkeypatch.setattr(video,'discover',lambda *args:[{'url':URL,'title':'対談'}])
    monkeypatch.setattr(video,'read_captions',lambda url:[])
    analyzer=Mock(); monkeypatch.setattr(video,'analyze',analyzer)
    video.run_research(store,Mock(),store.snapshot(),lambda:1)
    analyzer.assert_not_called()
    assert not store.snapshot()['video_observations']
    assert '未学習' in store.snapshot()['video_candidates'][0]['status']


def test_worker_respects_busy_quiet_and_pause(tmp_path,monkeypatch):
    store=CompanionStore(tmp_path/'state.json'); store.set_enabled('video_learning_enabled',True)
    now=datetime(2026,9,26,12).timestamp()
    runner=Mock(); monkeypatch.setattr(video,'run_research',runner)
    life=CompanionLife(store,Mock(),clock=lambda:now,busy=lambda:True)
    life.tick(); runner.assert_not_called()
    life.busy=lambda:False; life.tick(); runner.assert_called_once()
    life.tick(); assert runner.call_count == 1


def test_verified_video_example_reaches_trial_and_adopted_style(tmp_path):
    store=CompanionStore(tmp_path/'state.json')
    note=video.analyze(analysis_client(),{'url':URL},rows(),{'video_preferences':[{'id':'p','text':'質問を重ねないで'}],'conversation_trials':[]})
    store.save_video_candidate({'url':URL,'title':'対談'},'字幕確認',1,note)
    style=store.conversation_style()
    assert style['example']['prototype'] == note['prototype']
    store.record_turn('話したよ','短い感想',2,trial_id=style['trial_id'])
    store.evaluate_trial(style['trial_id'],'adopted',3)
    assert store.conversation_style()['example']['prototype'] == note['prototype']
    context,_=store.context(query='動画で何を学んだの')
    assert json.loads(context)['caption_learning']['observations'][0]['url'] == URL


def test_pause_after_caption_fetch_prevents_analysis(tmp_path, monkeypatch):
    store=CompanionStore(tmp_path/'state.json');store.set_enabled('video_learning_enabled',True)
    monkeypatch.setattr(video,'discover',lambda *args:[{'url':URL,'title':'対談'}])
    def read(url):
        store.set_enabled('video_learning_enabled',False)
        return rows()
    monkeypatch.setattr(video,'read_captions',read)
    analyzer=Mock();monkeypatch.setattr(video,'analyze',analyzer)
    video.run_research(store,Mock(),store.snapshot(),lambda:1)
    analyzer.assert_not_called()
    assert '中断' in store.snapshot()['video_candidates'][0]['status']
