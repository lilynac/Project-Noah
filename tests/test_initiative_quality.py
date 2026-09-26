import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src.initiative.quality import review_initiative


def client_for(value):
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(value))
    return client


def test_only_four_explicit_positive_verdicts_pass():
    verdict = dict(concrete=True, grounded=True, honest=True, novel=True)
    client = client_for(verdict)
    result = review_initiative(client, '目線を遅らせる工夫が気になったよ。', '{}')
    assert result.approved
    args = client.responses.create.call_args.kwargs
    assert args['store'] is False
    assert json.loads(args['input'][1]['content'])['candidate'] == '目線を遅らせる工夫が気になったよ。'


@pytest.mark.parametrize('field', ['concrete', 'grounded', 'honest', 'novel'])
def test_each_quality_problem_blocks_delivery(field):
    verdict = dict(concrete=True, grounded=True, honest=True, novel=True)
    verdict[field] = False
    result = review_initiative(client_for(verdict), '候補。', '{}')
    assert not result.approved and result.reason == field


@pytest.mark.parametrize('verdict', [{}, [], {'concrete': 'true', 'grounded': True, 'honest': True, 'novel': True}])
def test_incomplete_or_wrong_type_verdict_does_not_pass(verdict):
    assert review_initiative(client_for(verdict), '候補。', '{}').reason == 'unavailable'


def test_repeated_utterance_is_rejected_without_api_even_with_sources():
    client = Mock()
    context = json.dumps({'recent_noah_messages': [{'text': '目線の工夫が気になるよ。\n\n出典：\nhttps://example.org'}]})
    result = review_initiative(client, '目線の工夫が気になるよ！', context)
    assert result.reason == 'duplicate'
    client.responses.create.assert_not_called()


def test_api_failure_is_not_a_fallback_utterance():
    client = Mock()
    client.responses.create.side_effect = TimeoutError()
    assert review_initiative(client, '候補。', '{}').reason == 'unavailable'
    assert review_initiative(None, '候補。', '{}').approved is False
