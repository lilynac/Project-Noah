"""A conversation's question and its sourced follow-up, with delivery receipts."""
from uuid import uuid4


def remember_thread(state, topic, reason, event, now):
    if not event or not event.get('user') or not event.get('id'):
        return
    if any(t['topic'] == topic and t['event_id'] == event['id'] for t in state['conversation_threads']):
        return
    state['conversation_threads'].append(dict(id=uuid4().hex, topic=topic,
        question=reason, event_id=event['id'], user_words=event['user'][:600],
        conversation_at=event.get('at', now), at=now, finding_ids=[], delivered_ids=[]))
    state['conversation_threads'] = state['conversation_threads'][-20:]


def link_finding(state, finding):
    for thread in state['conversation_threads']:
        if thread['topic'] == finding.get('topic') and finding['id'] not in thread['finding_ids']:
            thread['finding_ids'] = (thread['finding_ids'] + [finding['id']])[-20:]


def apply_links(state, result, batch):
    """Reflection can connect different topic wording, only using known IDs."""
    threads = {t['id']: t for t in state['conversation_threads']}
    known_threads = {t['id'] for t in batch.get('conversation_threads', [])}
    sources = {f['id']: f for f in batch['findings'][-2:] + batch['video_observations'][-3:]}
    links = result.get('conversation_links', [])
    if not isinstance(links, list):
        return
    for link in links[:2]:
        if not isinstance(link, dict):
            continue
        thread = threads.get(link.get('thread_id'))
        source = sources.get(link.get('finding_id'))
        reason = link.get('connection', '')
        if not thread or thread['id'] not in known_threads or not source or not isinstance(reason, str) or not 4 <= len(reason) <= 300:
            continue
        if source['id'] not in thread['finding_ids']:
            thread['finding_ids'] = (thread['finding_ids'] + [source['id']])[-20:]
        thread['connection'] = reason


def continuation(state, finding_id):
    for thread in reversed(state['conversation_threads']):
        if finding_id in thread['finding_ids'] and finding_id not in thread['delivered_ids']:
            return {k: thread[k] for k in ('id', 'topic', 'question', 'user_words', 'conversation_at', 'connection') if k in thread}
    return None


def acknowledge(state, finding_id):
    for thread in state['conversation_threads']:
        if finding_id in thread['finding_ids'] and finding_id not in thread['delivered_ids']:
            thread['delivered_ids'] = (thread['delivered_ids'] + [finding_id])[-20:]
