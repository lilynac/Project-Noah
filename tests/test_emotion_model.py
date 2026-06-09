from src.emotion_model import (
    EMOTIONS,
    build_emotion_guidance,
    build_initiative_emotion_bias,
    create_initial_emotion_state,
    emotion_state_from_mapping,
    update_impression,
)


def test_initial_state_has_plutchik_emotions_in_range():
    state = create_initial_emotion_state()
    assert set(state.values) == set(EMOTIONS)
    assert all(0.0 <= v <= 1.0 for v in state.values.values())


def test_update_impression_is_small_and_clamped():
    state = create_initial_emotion_state()
    updated = update_impression(state, "ありがとう。次の実装もお願い", "うん、進めるね", meta={"engaged": True})
    assert updated.values["trust"] > state.values["trust"]
    assert updated.values["anticipation"] > state.values["anticipation"]
    assert all(0.0 <= v <= 1.0 for v in updated.values.values())
    assert updated.values["trust"] - state.values["trust"] <= 0.08


def test_guidance_does_not_expose_scores():
    state = emotion_state_from_mapping({"values": {"trust": 0.5, "sadness": 0.3}})
    guidance = build_emotion_guidance(state)
    assert "0.5" not in guidance
    assert "trust" not in guidance.lower()
    assert "sadness" not in guidance.lower()
    assert "plain" in guidance
    assert "poetic" in guidance


def test_initiative_bias_is_small():
    state = emotion_state_from_mapping({"values": {"trust": 0.6, "anticipation": 0.7, "sadness": 0.08}})
    bias, reasons = build_initiative_emotion_bias(state, suppressed=False, mode="normal")
    assert 0.0 < bias <= 0.08
    assert reasons


def test_initiative_bias_never_overrides_suppression():
    state = emotion_state_from_mapping({"values": {"trust": 1.0, "anticipation": 1.0}})
    bias, reasons = build_initiative_emotion_bias(state, suppressed=True, mode="normal")
    assert bias == 0.0
    assert reasons == ["suppressed:no_bias"]


def test_low_emotion_state_does_not_emit_guidance():
    state = emotion_state_from_mapping({"values": {"trust": 0.25, "anticipation": 0.24}})
    assert build_emotion_guidance(state) == ""


def test_engaged_turn_alone_does_not_raise_anticipation():
    state = create_initial_emotion_state()
    updated = update_impression(state, "こんばんは", "こんばんは", meta={"engaged": True})
    assert updated.values["anticipation"] <= state.values["anticipation"]
    assert updated.values["trust"] - state.values["trust"] <= 0.01
