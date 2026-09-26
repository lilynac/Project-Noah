import json
from unittest.mock import Mock
import pytest
from src.voice import NemoClient, speech_text


def test_speech_removes_sources_urls_and_code():
    assert speech_text('発見だよ。\n\n出典：\nhttps://example.org') == '発見だよ。'
    assert 'http' not in speech_text('[記事](https://example.org)を読んだ。 https://example.org/path')
    assert 'print' not in speech_text('話。```python\nprint(1)\n```')
    assert len(speech_text('あ。' * 500)) <= 600


@pytest.mark.parametrize('key,name,style_id', [('female1','女声1',10005), ('female6','女声6',10006)])
def test_requested_voice_uses_discovered_style_id(tmp_path, key, name, style_id):
    client = NemoClient(tmp_path/'run', tmp_path/'log')
    client.ensure_started = Mock(return_value=[dict(name=name, styles=[dict(name='ノーマル', id=style_id)])])
    wav = b'RIFF0000WAVEdata'
    client.request = Mock(side_effect=[json.dumps({'speedScale':1}).encode(), wav])
    assert client.synthesize('発見。\n\n出典：\nhttps://example.org', key) == wav
    query, synth = client.request.call_args_list
    assert query.kwargs['params'] == {'speaker':style_id,'text':'発見。'}
    assert synth.kwargs['params']['speaker'] == style_id
    assert synth.kwargs['payload']['speedScale'] == .95


def test_cancelled_synthesis_does_not_send_reply_text(tmp_path):
    client = NemoClient(tmp_path/'run', tmp_path/'log')
    client.ensure_started = Mock(return_value=[dict(name='女声1', styles=[dict(name='ノーマル', id=7)])])
    client.request = Mock()
    assert client.synthesize('文', 'female1', lambda: True) == b''
    client.request.assert_not_called()


def test_wrong_engine_is_rejected(tmp_path):
    client = NemoClient(tmp_path/'run', tmp_path/'log')
    client.request = Mock(return_value=b'{"uuid":"different"}')
    with pytest.raises(ValueError):
        client.speakers()
