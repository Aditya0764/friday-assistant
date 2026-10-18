"""P7-06a launcher: fake subprocesses only. No servers, no mic, no network, no real taskkill."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("launch", ROOT / "scripts" / "launch.py")
launch = importlib.util.module_from_spec(spec)
sys.modules["launch"] = launch
spec.loader.exec_module(launch)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = 0
        self.on_sleep = None  # optional hook, called on every supervisor/poll sleep
        self.on_grace = None  # optional hook, called on every post-ready grace sleep

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if seconds == launch.READY_GRACE:  # not counted, so on_sleep counts stay as before
            if self.on_grace:
                self.on_grace()
            return
        self.sleeps += 1
        if self.on_sleep:
            self.on_sleep(self.sleeps)


class FakeProc:
    def __init__(self, pid, name):
        self.pid = pid
        self.name = name
        self.rc = None
        self.die_after_polls = None  # exit 0 once poll() was called this many times
        self.polls = 0
        self.killed = False

    def poll(self):
        self.polls += 1
        if self.rc is None and self.die_after_polls and self.polls >= self.die_after_polls:
            self.rc = 0
        return self.rc

    def kill(self):
        self.killed = True
        self.rc = -9


class Rig:
    """Fake popen / kill_tree / ports; records everything the launcher does."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.procs = {}
        self.calls = []  # (name, argv, kwargs)
        self.killed = []  # names, in order
        self.out = []
        self.fc = FakeClock()
        self.free = True
        self.taken = set()
        self.open_ok = True
        self.port_free_fn = lambda host, port: port not in self.taken
        self.kill_raises = set()
        self.start_rc = {}  # name -> exit code right at start

    def popen(self, argv, **kwargs):
        name = "voice" if "friday.voice.loop" in argv else (
            "api" if "uvicorn" in argv else "dashboard")
        proc = FakeProc(100 + len(self.procs), name)
        if name in self.start_rc:
            proc.rc = self.start_rc[name]
        self.procs[name] = proc
        self.calls.append((name, argv, kwargs))
        return proc

    def kill_tree(self, proc):
        self.killed.append(proc.name)
        if proc.name in self.kill_raises:
            raise OSError("boom")
        proc.rc = -9

    def run(self, argv):
        return launch.main(
            argv,
            popen=self.popen,
            port_free=lambda host, port: self.port_free_fn(host, port),
            port_open=lambda host, port: self.open_ok,
            kill_tree=self.kill_tree,
            sleep=self.fc.sleep,
            clock=self.fc.clock,
            out=lambda *a: self.out.append(" ".join(str(x) for x in a)),
            log_dir=self.tmp / "logs",
            root=self.tmp,
            npm="npm.cmd",
        )

    @property
    def text(self):
        return "\n".join(self.out)


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def stop_after(rig, n):
    """Raise Ctrl+C on the n-th sleep (the supervisor loop's first sleeps)."""

    def hook(count):
        if count == n:
            raise KeyboardInterrupt

    rig.fc.on_sleep = hook


def names(rig):
    return [c[0] for c in rig.calls]


def test_default_starts_three_in_order_with_exact_commands(rig):
    stop_after(rig, 1)
    assert rig.run([]) == 0
    assert names(rig) == ["api", "dashboard", "voice"]
    api, dash, voice = rig.calls
    assert api[1] == [sys.executable, "-u", "-m", "uvicorn", "friday.api.app:app",
                      "--host", "127.0.0.1", "--port", "8000"]
    assert "--reload" not in api[1]
    assert dash[1] == ["npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--strictPort"]
    assert dash[2]["cwd"] == str(rig.tmp / "dashboard")
    assert voice[1] == [sys.executable, "-m", "friday.voice.loop"]
    assert voice[2] == {"cwd": str(rig.tmp)}  # inherits the console: no pipes, no new window


def test_api_and_dashboard_logs_open_in_w_mode_and_are_closed(rig):
    stop_after(rig, 1)
    rig.run([])
    for name in ("api", "dashboard"):
        handle = next(c[2]["stdout"] for c in rig.calls if c[0] == name)
        assert handle.mode == "w"
        assert handle.closed
        assert handle.name == str(rig.tmp / "logs" / f"launch_{name}.log")


@pytest.mark.parametrize(
    "flag,expected",
    [
        ("--no-api", ["dashboard", "voice"]),
        ("--no-dashboard", ["api", "voice"]),
        ("--no-voice", ["api", "dashboard"]),
    ],
)
def test_flags_skip_only_that_part(rig, flag, expected):
    stop_after(rig, 1)
    rig.run([flag])
    assert names(rig) == expected


def test_all_parts_off_exits_2_and_starts_nothing(rig):
    assert rig.run(["--no-api", "--no-dashboard", "--no-voice"]) == 2
    assert rig.calls == []


def test_port_taken_names_the_part_and_starts_and_kills_nothing(rig):
    rig.taken = {5173}
    assert rig.run([]) == 1
    assert rig.calls == [] and rig.killed == []
    assert "dashboard: port 5173 is already in use" in rig.text
    assert "api: port" not in rig.text


def test_preflight_only_checks_the_ports_of_enabled_parts(rig):
    rig.taken = {8000, 5173}
    stop_after(rig, 1)
    assert rig.run(["--no-api", "--no-dashboard"]) == 0
    assert names(rig) == ["voice"]


def test_part_crashing_at_start_is_named_with_its_log_tail_and_others_stop(rig):
    rig.start_rc = {"dashboard": 1}
    (rig.tmp / "logs").mkdir()
    # the fake child "writes" to its log after the launcher opened it
    orig = rig.popen

    def popen(argv, **kw):
        proc = orig(argv, **kw)
        if proc.name == "dashboard":
            kw["stdout"].write("Error: port 5173 is already in use\n")
            kw["stdout"].flush()
        return proc

    rig.popen = popen
    assert rig.run([]) == 1
    assert "dashboard: FAILED, exited with code 1" in rig.text
    assert "port 5173 is already in use" in rig.text  # the error is shown, not hidden
    assert "voice" not in names(rig)  # never started
    assert rig.killed == ["api"]  # the part already up was stopped; the dead one was not killed


def test_part_dying_later_stops_the_others_and_exits_1(rig):
    def hook(count):
        if count == 2:
            rig.procs["dashboard"].rc = 3

    rig.fc.on_sleep = hook
    assert rig.run([]) == 1
    assert "dashboard: FAILED, exited with code 3" in rig.text
    assert rig.killed[:1] == ["api"]  # api (alive) is killed; dashboard was already dead
    assert "dashboard" not in rig.killed


def test_ctrl_c_stops_dashboard_then_api_then_voice(rig):
    # voice gets Ctrl+C too (same console) and exits by itself within the grace period
    orig = rig.popen

    def popen(argv, **kw):
        proc = orig(argv, **kw)
        if proc.name == "voice":
            proc.die_after_polls = 4
        return proc

    rig.popen = popen
    stop_after(rig, 2)
    assert rig.run([]) == 0
    assert rig.killed == ["dashboard", "api"]  # voice was not force-killed
    assert "stopped: dashboard, api, voice" in rig.text


def test_voice_that_exits_within_the_grace_period_is_not_force_killed(rig):
    orig = rig.popen

    def popen(argv, **kw):
        proc = orig(argv, **kw)
        if proc.name == "voice":
            proc.die_after_polls = 6
        return proc

    rig.popen = popen
    stop_after(rig, 1)
    rig.run([])
    assert "voice" not in rig.killed
    assert rig.procs["voice"].rc == 0


def test_voice_that_hangs_is_killed_after_the_8_second_grace(rig):
    stop_after(rig, 1)
    started = {}

    def hook(count):
        if count == 1:
            started["t"] = rig.fc.now
            raise KeyboardInterrupt

    rig.fc.on_sleep = hook
    rig.run([])
    assert rig.killed == ["dashboard", "api", "voice"]
    assert rig.fc.now - started["t"] >= launch.VOICE_GRACE


def test_voice_exiting_cleanly_on_its_own_stops_the_rest_and_exits_0(rig):
    def hook(count):
        if count == 2:
            rig.procs["voice"].rc = 0

    rig.fc.on_sleep = hook
    assert rig.run([]) == 0
    assert "voice: exited" in rig.text
    assert rig.killed == ["dashboard", "api"]


def test_voice_crash_exits_1(rig):
    def hook(count):
        if count == 2:
            rig.procs["voice"].rc = 2

    rig.fc.on_sleep = hook
    assert rig.run([]) == 1
    assert "voice: FAILED, exited with code 2" in rig.text


def test_one_failing_kill_does_not_skip_the_others(rig):
    rig.kill_raises = {"dashboard"}
    stop_after(rig, 1)
    rig.run([])
    assert rig.killed == ["dashboard", "api", "voice"]
    assert "dashboard: could not stop it cleanly" in rig.text


def test_readiness_timeout_names_the_part_and_stops_everything(rig):
    rig.open_ok = False
    assert rig.run(["--no-voice"]) == 1
    assert "api: FAILED, not answering on port 8000" in rig.text
    assert rig.killed == ["api"]
    assert "dashboard" not in names(rig)


@pytest.mark.parametrize(
    "bind_ok,connects,free",
    [(True, True, False), (True, False, True), (False, False, False), (False, True, False)],
)
def test_port_free_needs_bind_ok_and_connect_refused(bind_ok, connects, free):
    assert launch._port_free(
        "127.0.0.1", 8000,
        can_bind=lambda h, p: bind_ok,
        can_connect=lambda h, p, t: connects,
    ) is free


def test_bind_ok_but_something_answers_is_taken_and_nothing_starts(rig):
    # the http.server case: Windows lets the 127.0.0.1 bind succeed beside a 0.0.0.0 listener
    rig.port_free_fn = lambda host, port: launch._port_free(
        host, port, can_bind=lambda h, p: True, can_connect=lambda h, p, t: True)
    assert rig.run([]) == 1
    assert rig.calls == [] and rig.killed == []
    assert "api: port 8000 is already in use" in rig.text
    assert "dashboard: port 5173 is already in use" in rig.text
    assert "up http" not in rig.text


def test_connect_refused_after_bind_ok_lets_the_launch_proceed(rig):
    rig.port_free_fn = lambda host, port: launch._port_free(
        host, port, can_bind=lambda h, p: True, can_connect=lambda h, p, t: False)
    stop_after(rig, 1)
    assert rig.run(["--no-voice"]) == 0
    assert names(rig) == ["api", "dashboard"]


def test_child_exiting_during_the_grace_period_is_a_failure_not_up(rig):
    # another program answers the port, but our child (api) is already dead
    rig.fc.on_grace = lambda: setattr(rig.procs["api"], "rc", 1)
    assert rig.run(["--no-voice"]) == 1
    assert "api: FAILED, exited with code 1" in rig.text
    assert "api: up" not in rig.text
    assert "dashboard" not in names(rig)


def test_status_lines_urls_and_voice_wording(rig):
    stop_after(rig, 1)
    rig.run([])
    assert "api: up http://127.0.0.1:8000" in rig.text
    assert "dashboard: up http://127.0.0.1:5173" in rig.text
    pid = rig.procs["voice"].pid
    assert f"voice: started (pid {pid}), models loading" in rig.text
    assert "voice: running" not in rig.text


def test_output_never_contains_environment_values(rig, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sekret-value-123")
    stop_after(rig, 1)
    rig.run([])
    assert "sekret-value-123" not in rig.text


def test_kill_tree_on_windows_uses_taskkill_tree_and_force():
    ran = []

    def run(argv, **kw):
        ran.append(argv)
        return SimpleNamespace(returncode=0)

    proc = FakeProc(4242, "x")
    launch._kill_tree(proc, run=run, windows=True)
    assert ran == [["taskkill", "/PID", "4242", "/T", "/F"]]
    assert not proc.killed


def test_kill_tree_falls_back_to_kill_when_taskkill_fails_or_off_windows():
    proc = FakeProc(1, "x")
    launch._kill_tree(proc, run=lambda *a, **k: SimpleNamespace(returncode=128), windows=True)
    assert proc.killed
    proc2 = FakeProc(2, "y")
    launch._kill_tree(proc2, run=None, windows=False)
    assert proc2.killed
