#!/usr/bin/env python3
"""Invoked by smoke-x11.sh on an isolated display and session bus."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def wait_for(predicate, process, description):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        if process.poll() is not None:
            raise RuntimeError(f"application exited while waiting for {description}")
        time.sleep(0.1)
    raise TimeoutError(description)


def main():
    binary = str(Path(sys.argv[1]).resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix="ghostty2-x11-") as directory:
        root = Path(directory)
        env = dict(os.environ)
        for key in ("GHOSTTY_RESOURCES_DIR", "GHOSTTY_CONFIG_DIR", "WAYLAND_DISPLAY"):
            env.pop(key, None)
        env.update(
            HOME=str(root / "home"),
            XDG_CONFIG_HOME=str(root / "config"),
            XDG_CACHE_HOME=str(root / "cache"),
            XDG_STATE_HOME=str(root / "state"),
            XDG_RUNTIME_DIR=str(root / "run"),
            GDK_BACKEND="x11",
            LIBGL_ALWAYS_SOFTWARE="1",
            GHOSTTY2_SMOKE_DIR=str(root),
        )
        for name in ("home", "config", "cache", "state", "run"):
            (root / name).mkdir(mode=0o700)
        config = root / "smoke.conf"
        config.write_text("""title = Ghostty2 beta smoke
gtk-single-instance = false
confirm-close-surface = false
quit-after-last-window-closed = true
window-save-state = never
shell-integration = none
""")
        child = root / "child.sh"
        child.write_text("""set -eu
test -t 0 && test -t 1
test "$TERM" = xterm-ghostty
stty size > "$GHOSTTY2_SMOKE_DIR/initial-size"
printf '\\033[31mGhostty² beta: UTF-8 ✓ and ANSI color\\033[0m\\n'
touch "$GHOSTTY2_SMOKE_DIR/ready"
IFS= read -r input
test "$input" = ghostty2-beta-input
stty size > "$GHOSTTY2_SMOKE_DIR/resized"
touch "$GHOSTTY2_SMOKE_DIR/passed"
""")
        log = root / "application.log"
        with log.open("w") as output:
            process = subprocess.Popen(
                [binary, "--config-default-files=false", f"--config-file={config}",
                 "-e", "/bin/sh", str(child)],
                env=env, stdout=output, stderr=subprocess.STDOUT,
            )
            try:
                wait_for(lambda: (root / "ready").exists(), process, "PTY shell startup")

                def find_window():
                    result = subprocess.run(
                        ["xdotool", "search", "--name", "^Ghostty2 beta smoke$"],
                        env=env, text=True, capture_output=True, check=False,
                    )
                    return result.stdout.splitlines()[0] if result.returncode == 0 else None

                window = wait_for(find_window, process, "terminal window")
                for args in (
                    ["windowsize", "--sync", window, "1000", "700"],
                    ["windowfocus", "--sync", window],
                    ["type", "--clearmodifiers", "--window", window, "ghostty2-beta-input"],
                    ["key", "--window", window, "Return"],
                ):
                    subprocess.run(["xdotool", *args], env=env, check=True, timeout=15)
                wait_for(lambda: (root / "passed").exists(), process, "keyboard input and PTY resize")
                if process.wait(timeout=30) != 0:
                    raise RuntimeError("application did not exit cleanly")
                initial = (root / "initial-size").read_text().split()
                resized = (root / "resized").read_text().split()
                assert len(resized) == 2 and all(int(value) > 0 for value in resized)
                assert resized != initial, (initial, resized)
                print(f"X11 startup, PTY, keyboard, resize {initial} -> {resized}, and exit passed")
            except BaseException:
                print(log.read_text(), file=sys.stderr)
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
