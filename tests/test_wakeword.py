import numpy as np
import pytest

from friday.voice.wakeword import CHUNK, WakeWordDetector


class _Model:
    def __init__(self, scores):
        self.scores = list(scores)
        self.resets = 0

    def predict(self, chunk):
        return {"ww_B": self.scores.pop(0)}

    def reset(self):
        self.resets += 1


def _run(scores, **kwargs):
    detector = WakeWordDetector(model=_Model(scores), **kwargs)
    chunk = np.zeros(CHUNK, dtype=np.int16)
    return [detector.feed(chunk) for _ in scores]


def test_threshold_is_inclusive():
    assert _run([0.89, 0.9])[1] == (0.9, True)
    assert _run([0.89])[0][1] is False


def test_noise_above_threshold_is_one_event():
    results = _run([0.95] * 40)
    assert [fired for _, fired in results].count(True) == 1


def test_a_new_event_needs_more_than_25_chunks_since_the_last_crossing():
    scores = [0.0] * 100
    for index in (1, 20, 46, 47, 80):  # 1 fires; 20 (19 later) no; 46 (26 later) fires; 47 no; 80 (33 later) fires
        scores[index] = 0.95
    fired = [i for i, (_, f) in enumerate(_run(scores)) if f]
    assert fired == [1, 46, 80]


def test_a_crossing_restarts_the_cooldown():
    scores = [0.0] * 100
    for index in (1, 20, 40):  # each crossing is only 19-20 chunks after the one before
        scores[index] = 0.95
    assert [i for i, (_, f) in enumerate(_run(scores)) if f] == [1]


def test_reset_clears_the_cooldown_and_resets_the_model():
    model = _Model([0.95, 0.95])
    detector = WakeWordDetector(model=model)
    chunk = np.zeros(CHUNK, dtype=np.int16)
    assert detector.feed(chunk)[1] is True
    detector.reset()
    assert model.resets == 1
    assert detector.feed(chunk)[1] is True


@pytest.mark.parametrize(
    "bad",
    [np.zeros(CHUNK, dtype=np.float32), np.zeros(CHUNK - 1, dtype=np.int16), np.zeros((CHUNK, 1), dtype=np.int16)],
)
def test_wrong_chunks_are_rejected(bad):
    with pytest.raises(ValueError):
        WakeWordDetector(model=_Model([0.0])).feed(bad)