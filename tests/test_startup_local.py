from src import startup_display


def test_gui_narration_does_not_call_api(monkeypatch):
    monkeypatch.setattr(startup_display, 'read_emotion_status', lambda: {})
    def forbidden(*args):
        raise AssertionError('GUI startup must not wait for the API')
    monkeypatch.setattr(startup_display, '_api_sequence', forbidden)
    sequence = startup_display.build_wake_sequence(allow_api=False)
    assert sequence.source == 'local'
    assert sequence.opening and sequence.steps and sequence.ready
