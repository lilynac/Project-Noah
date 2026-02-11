# src/scoring.py
from __future__ import annotations

TAG_TO_DELTA = {
  "kindness":            {"joy": +2, "trust": +2, "sadness": -1},
  "respect":             {"trust": +2, "joy": +1, "anger": -1},
  "reliability":         {"trust": +3, "anticipation": +1, "fear": -1},
  "honesty":             {"trust": +3, "joy": +1, "disgust": -1},
  "inconsistency":       {"surprise": +2, "trust": -2, "anticipation": -1},
  "rejection":           {"sadness": +3, "anger": +1, "trust": -2},
  "intimacy_progress":   {"joy": +3, "trust": +2, "anticipation": +2},
  "vulnerability_shared":{"trust": +2, "sadness": +1, "joy": +1},
  "support":             {"trust": +2, "joy": +2, "fear": -1},
  "admiration":          {"joy": +2, "trust": +1, "anticipation": +1},

  "boundary_violation":  {"disgust": +3, "anger": +2, "trust": -2, "fear": +1},
  "manipulation":        {"disgust": +3, "anger": +2, "trust": -3, "fear": +1},
  "jealousy_trigger":    {"anger": +2, "sadness": +1, "fear": +1, "trust": -1},
  "insult":              {"anger": +3, "sadness": +2, "trust": -2, "disgust": +1},
  "apology_repair":      {"trust": +2, "sadness": -2, "anger": -2, "joy": +1},
  "betrayal":            {"sadness": +3, "anger": +3, "trust": -4, "disgust": +2},
  "threat":              {"fear": +4, "anger": +2, "trust": -2, "surprise": +1},

  "warmth":              {"joy": +2, "trust": +1, "sadness": -1},
  "coldness":            {"sadness": +2, "trust": -1, "fear": +1},
  "chemistry":           {"joy": +2, "anticipation": +2, "trust": +1, "surprise": +1}
}

EMOTIONS = ["joy","trust","fear","surprise","sadness","disgust","anger","anticipation"]

def clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))

def merge_deltas(tags: list[str], intensity: float = 1.0) -> dict[str, float]:
    delta = {e: 0.0 for e in EMOTIONS}
    for t in tags:
        base = TAG_TO_DELTA.get(t, {})
        for e, v in base.items():
            delta[e] += float(v) * float(intensity)
    return delta

def apply_decay(scores_i: dict[str, float], scores_b: dict[str, float],
                decay_i: float = 0.92, decay_b: float = 0.995) -> None:
    for e in EMOTIONS:
        scores_i[e] *= decay_i
        scores_b[e] *= decay_b

def apply_delta(scores_i: dict[str, float], scores_b: dict[str, float],
                delta: dict[str, float], belief_weight: float = 0.35) -> None:
    for e in EMOTIONS:
        scores_i[e] = clamp(scores_i[e] + float(delta.get(e, 0.0)))
        scores_b[e] = clamp(scores_b[e] + float(delta.get(e, 0.0)) * belief_weight)

def summarize(scores_i: dict[str, float], scores_b: dict[str, float],
              w_b: float = 0.7, w_i: float = 0.3) -> dict[str, float]:
    return {e: w_b*scores_b[e] + w_i*scores_i[e] for e in EMOTIONS}
