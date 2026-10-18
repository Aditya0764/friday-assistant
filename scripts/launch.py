"""One-command launcher (P7-06a): API, dashboard dev server and voice loop together.

Run from the repo root with the venv active:  python scripts\\launch.py
Flags: --no-api, --no-dashboard, --no-voice (each part is optional).

NOTE: RAM with all three parts running together has NOT been measured.

How it behaves:
- Ports 8000 (API) and 5173 (dashboard) are checked first: a port is free only if a bind of
  127.0.0.1 works and a connect to it is refused. If one is taken it says which and stops.
  It never kills other programs. "<part>: up" is printed only if the child is still alive
  about 1 s after its port answers.
- The voice loop inherits this console, so the push-to-talk key and the mic work as usual.
- API and dashboard output goes to data\\logs\\launch_api.log and launch_dashboard.log
  (data\\ is gitignored). The tail of the log is printed if that part fails.
- If any part exits, the others are stopped and the exit code is 1 (0 if the voice loop ended
  cleanly by itself). Ctrl+C stops everything: dashboard and API first (taskkill /T /F kills
  the whole npm -> node -> vite tree), then the voice loop gets 8 s to exit on its own.
- It prints only fixed text, ports, URLs, PIDs and log paths. No environment values.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "logs"
HOST = "127.0.0.1"
API_PORT = 8000
DASH_PORT = 5173
READY_TIMEOUT = 60.0  # seconds to wait for the API / dashboard port to answer
VOICE_GRACE = 8.0  # seconds the voice loop gets to exit on its own before taskkill
POLL = 0.5
PREFLIGHT_CONNECT_TIMEOUT = 0.3  # a refused connect means nothing listens on the port
READY_GRACE = 1.0  # after the port answers, wait this long and confirm the child is still alive
TAIL_LINES = 15


@dataclass
class Part:
    name: str
    argv: list[str]
    cwd: Path
    port: int | None = None
    logged: bool = True  # output goes to a log file (False: inherits this console)
    proc: object | None = None
    log: object | None = None
    extra: dict = field(default_factory=dict)


def build_parts(args: argparse.Namespace, npm: str | None = None, root: Path = ROOT) -> list[Part]:
    parts: list[Part] = []
    if not args.no_api:
        parts.append(
            Part(
                "api",
                [sys.executable, "-u", "-m", "uvicorn", "friday.api.app:app",
                 "--host", HOST, "--port", str(API_PORT)],
                root,
                API_PORT,
            )
        )
    if not args.no_dashboard:
        npm = npm or shutil.which("npm.cmd") or "npm.cmd"
        parts.append(
            Part(
                "dashboard",
                [npm, "run", "dev", "--", "--host", HOST, "--strictPort"],
                root / "dashboard",
                DASH_PORT,
            )
        )
    if not args.no_voice:
        parts.append(
            Part("voice", [sys.executable, "-m", "friday.voice.loop"], root, None, logged=False)
        )
    return parts


def _can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def _can_connect(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _port_free(host: str, port: int, can_bind=_can_bind, can_connect=_can_connect) -> bool:
    """Free only if the bind works AND nothing answers a connect. Windows lets a specific-address
    bind succeed next to a wildcard (0.0.0.0 / ::) listener, so the bind alone is not enough."""
    return can_bind(host, port) and not can_connect(host, port, PREFLIGHT_CONNECT_TIMEOUT)


def _port_open(host: str, port: int) -> bool:
    return _can_connect(host, port)


def _kill_tree(proc, run=subprocess.run, windows: bool | None = None) -> None:
    """Kill a child and everything it started. taskkill /T is what reaches npm's children."""
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        result = run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False
        )
        if result.returncode == 0:
            return
    proc.kill()


def _log_tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(no log)"
    return "\n".join(lines[-TAIL_LINES:]) or "(log is empty)"


def _wait_ready(part: Part, port_open, sleep, clock) -> str | None:
    """None when the port answers, else a short reason."""
    deadline = clock() + READY_TIMEOUT
    while clock() < deadline:
        rc = part.proc.poll()
        if rc is not None:
            return f"exited with code {rc}"
        if port_open(HOST, part.port):
            # something answers; make sure it is our child and not another program on the port
            sleep(READY_GRACE)
            rc = part.proc.poll()
            return None if rc is None else f"exited with code {rc}"
        sleep(POLL)
    return f"not answering on port {part.port} after {int(READY_TIMEOUT)} s"


def _stop_all(parts: list[Part], kill_tree, sleep, clock, out) -> None:
    started = [p for p in parts if p.proc is not None]
    # dashboard and API first (reverse start order), the voice loop last with a grace period
    order = [p for p in reversed(started) if p.name != "voice"]
    order += [p for p in started if p.name == "voice"]
    stopped = []
    for part in order:
        try:
            if part.proc.poll() is None:
                if part.name == "voice":
                    deadline = clock() + VOICE_GRACE
                    while part.proc.poll() is None and clock() < deadline:
                        sleep(0.2)
                if part.proc.poll() is None:
                    kill_tree(part.proc)
            stopped.append(part.name)
        except Exception as exc:  # noqa: BLE001 - one failed kill must not skip the others
            out(f"{part.name}: could not stop it cleanly ({exc})")
    if stopped:
        out("stopped: " + ", ".join(stopped))


def _fail(part: Part, why: str, log_dir: Path, out) -> None:
    out(f"{part.name}: FAILED, {why}")
    if part.logged:
        log_path = log_dir / f"launch_{part.name}.log"
        out(f"--- last lines of {log_path} ---")
        out(_log_tail(log_path))
        out("--- end ---")


def main(
    argv: list[str] | None = None,
    *,
    popen=subprocess.Popen,
    port_free=_port_free,
    port_open=_port_open,
    kill_tree=_kill_tree,
    sleep=time.sleep,
    clock=time.monotonic,
    out=print,
    log_dir: Path = LOG_DIR,
    root: Path = ROOT,
    npm: str | None = None,
) -> int:
    ap = argparse.ArgumentParser(description="Start Friday's API, dashboard and voice loop.")
    ap.add_argument("--no-api", action="store_true", help="do not start the API")
    ap.add_argument("--no-dashboard", action="store_true", help="do not start the dashboard")
    ap.add_argument("--no-voice", action="store_true", help="do not start the voice loop")
    args = ap.parse_args(argv)

    parts = build_parts(args, npm=npm, root=root)
    if not parts:
        out("Nothing to start: all three parts are switched off.")
        return 2

    if sys.prefix == sys.base_prefix:
        out("Warning: no virtual environment is active (.venv\\Scripts\\activate).")

    taken = [p for p in parts if p.port and not port_free(HOST, p.port)]
    if taken:
        for p in taken:
            out(f"{p.name}: port {p.port} is already in use. Close what uses it and try again.")
        out("Nothing was started and nothing was stopped.")
        return 1

    log_dir.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    code = 0
    try:
        for part in parts:
            kwargs: dict = {"cwd": str(part.cwd)}
            if part.logged:
                part.log = open(log_dir / f"launch_{part.name}.log", "w", encoding="utf-8")  # noqa: SIM115
                kwargs.update(
                    stdin=subprocess.DEVNULL,
                    stdout=part.log,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                )
            part.proc = popen(part.argv, **kwargs)
            if part.port is not None:
                why = _wait_ready(part, port_open, sleep, clock)
                if why:
                    _fail(part, why, log_dir, out)
                    return 1
                out(f"{part.name}: up http://{HOST}:{part.port}")
            else:
                out(f"{part.name}: started (pid {part.proc.pid}), models loading")
        if not any(p.name == "voice" for p in parts):
            out("Ctrl+C to stop.")

        while True:
            for part in parts:
                rc = part.proc.poll()
                if rc is None:
                    continue
                if part.name == "voice" and rc == 0:
                    out("voice: exited")
                    return 0
                _fail(part, f"exited with code {rc}", log_dir, out)
                return 1
            sleep(POLL)
    except KeyboardInterrupt:
        out("\nCtrl+C: stopping everything I started...")
        code = 0
    finally:
        _stop_all(parts, kill_tree, sleep, clock, out)
        for part in parts:
            if part.log is not None:
                part.log.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
