import numpy as np

from friday.voice.endpoint import (
    MIN_SPEECH_RMS,
    SPEECH_OVER_FLOOR,
    Endpointer,
    NoiseFloor,
    rms,
    speech_threshold,
)


def _chunk(level):
    return np.full(1280, int(level * 32768), dtype=np.int16)


def test_rms_of_a_constant_chunk():
    assert abs(rms(_chunk(0.25)) - 0.25) < 0.001
    assert rms(np.zeros(1280, dtype=np.int16)) == 0.0


def test_noise_floor_ignores_short_loud_bursts():
    floor = NoiseFloor()
    for _ in range(50):
        floor.add(0.01)
    for _ in range(5):
        floor.add(0.5)
    assert abs(floor.level - 0.01) < 0.001
    assert NoiseFloor().level == 0.0


def test_threshold_has_a_minimum_and_scales_with_the_floor():
    assert speech_threshold(0.0001) == MIN_SPEECH_RMS
    assert abs(speech_threshold(0.02) - 0.02 * SPEECH_OVER_FLOOR) < 1e-9


def test_nobody_speaking_gives_up():
    ep = Endpointer(0.05)
    results = [ep.update(_chunk(0.0)) for _ in range(50)]
    assert results[:-1] == [None] * 49 and results[-1] == "no_speech"


def test_speech_then_quiet_is_done():
    ep = Endpointer(0.05)
    assert [ep.update(_chunk(0.2)) for _ in range(5)] == [None] * 5
    results = [ep.update(_chunk(0.0)) for _ in range(12)]
    assert results[:-1] == [None] * 11 and results[-1] == "done"


def test_a_pause_inside_the_command_does_not_end_it():
    ep = Endpointer(0.05)
    for level in [0.2] * 3 + [0.0] * 5 + [0.2] * 3:
        assert ep.update(_chunk(level)) is None
    assert [ep.update(_chunk(0.0)) for _ in range(12)][-1] == "done"


def test_never_longer_than_max():
    ep = Endpointer(0.05)
    results = [ep.update(_chunk(0.2)) for _ in range(100)]
    assert results[-1] == "max" and "done" not in results