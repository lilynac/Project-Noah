"""Local VOICEVOX Nemo client; no cloud TTS or fixed numeric voice IDs."""
import json
import re
import subprocess
from pathlib import Path
from threading import Event, Lock
import urllib.parse
import urllib.request

VOICES = {'female1': ('女性1', '亜咲比 凛'), 'female6': ('女性6', '藤田昌代')}
BASE_URL = 'http://127.0.0.1:50121'
SAMPLE = 'おかえり。今日は、少し話せるのがうれしい。わたしは、言葉にしなかった気持ちが残る物語に惹かれるよ。'


def speech_text(value):
    value = value.split('\n\n出典：', 1)[0]
    value = re.sub(r'```.*?```', '', value, flags=re.S)
    value = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', value)
    value = re.sub(r'https?://\S+', '', value)
    value = re.sub(r'[*#`]', '', value).strip()
    if len(value) > 600:
        prefix = value[:600]
        end = prefix.rfind('。')
        value = prefix[:end + 1] if end >= 0 else prefix
    return value


class NemoClient:
    def __init__(self, engine_path, log_path):
        self.engine_path, self.log_path = Path(engine_path), Path(log_path)
        self.process = None
        self.lock = Lock()
        self.closed = Event()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, route, *, params=None, payload=None, post=False, timeout=40):
        url = BASE_URL + route
        if params:
            url += '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else (b'' if post else None),
                                     headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=timeout) as response:
            return response.read(20_000_000)

    def speakers(self):
        manifest = json.loads(self.request('/engine_manifest', timeout=2))
        if manifest.get('uuid') != '208cf94d-43d2-4cf5-abc0-9783cac36d29':
            raise ValueError('Port 50121 is not VOICEVOX Nemo')
        return json.loads(self.request('/speakers', timeout=2))

    def ensure_started(self):
        try:
            return self.speakers()
        except OSError:
            pass
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError('Voice stopped')
            if self.process is None or self.process.poll() is not None:
                if not self.engine_path.is_file():
                    raise FileNotFoundError('Nemo engine is not installed')
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open('ab') as log:
                    self.process = subprocess.Popen([str(self.engine_path.resolve()), '--host', '127.0.0.1', '--port', '50121'],
                        cwd=self.engine_path.parent, stdout=log, stderr=log)
        for _ in range(60):
            if self.closed.wait(.5):
                raise RuntimeError('Voice stopped')
            try:
                return self.speakers()
            except OSError:
                pass
        raise TimeoutError('Nemo startup timed out')

    def synthesize(self, value, voice, cancelled=lambda: False):
        name, _ = VOICES[voice]
        speakers = self.ensure_started()
        speaker = next((s for s in speakers if s['name'] in (name, name.replace('女性', '女声'))), None)
        if not speaker or not speaker.get('styles'):
            raise ValueError('Requested Nemo voice is unavailable')
        style = next((s for s in speaker['styles'] if s['name'] == 'ノーマル'), speaker['styles'][0])
        if cancelled():
            return b''
        query = json.loads(self.request('/audio_query', params={'text': speech_text(value), 'speaker': style['id']}, post=True))
        query['speedScale'] = 0.95
        if cancelled():
            return b''
        wav = self.request('/synthesis', params={'speaker': style['id']}, payload=query)
        if not wav.startswith(b'RIFF') or wav[8:12] != b'WAVE':
            raise ValueError('Invalid synthesized WAV')
        return wav

    def close(self):
        self.closed.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
