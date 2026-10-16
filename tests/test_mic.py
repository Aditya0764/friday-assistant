import numpy as np

from friday.voice.mic import CHUNK, MAX_QUEUED_CHUNKS, MicHub


class _Stream:
    def __init__(self):
        self.started = self.stopped = self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def _hub():
    made, callbacks = [], []

    def factory(callback):
        callbacks.append(callback)
        made.append(_Stream())
        return made[-1]

    hub = MicHub(stream_factory=factory)
    hub.start()
    return hub, callbacks[0], made


def _block(samples, value=0):
    return np.full((samples, 1), value, dtype=np.int16)


def test_whole_chunks_come_out_in_order():
    hub, feed, _ = _hub()
    feed(_block(CHUNK * 2, 7), CHUNK * 2, None, None)
    first, second = hub.read(0.01), hub.read(0.01)
    assert first.shape == (CHUNK,) and int(first[0]) == 7 and int(second[-1]) == 7
    assert hub.read(0.01) is None


def test_odd_sized_blocks_are_joined_without_gaps():
    hub, feed, _ = _hub()
    for value in (1, 2, 3):
        feed(_block(1000, value), 1000, None, None)
    first, second = hub.read(0.01), hub.read(0.01)
    assert int(first[999]) == 1 and int(first[1000]) == 2  # chunk 1 spans blocks 1 and 2
    assert second is not None  # 3000 samples = 2 whole chunks (2560) plus 440 left over
    assert hub.read(0.01) is None


def test_oldest_chunks_are_dropped_when_nobody_reads():
    hub, feed, _ = _hub()
    for value in range(MAX_QUEUED_CHUNKS + 3):
        feed(_block(CHUNK, value), CHUNK, None, None)
    assert hub.dropped == 3
    assert int(hub.read(0.01)[0]) == 3


def test_a_status_flag_is_counted():
    hub, feed, _ = _hub()
    feed(_block(CHUNK), CHUNK, None, "input overflow")
    assert hub.overflows == 1


def test_flush_empties_the_queue():
    hub, feed, _ = _hub()
    feed(_block(CHUNK * 3), CHUNK * 3, None, None)
    assert hub.flush() == 3
    assert hub.read(0.01) is None


def test_start_is_once_and_stop_closes_the_stream():
    hub, _, made = _hub()
    hub.start()
    assert len(made) == 1 and made[0].started
    hub.stop()
    assert made[0].stopped and made[0].closed