#!/usr/bin/env python3
"""Exercise quick-terminal tabs on a private, headless Sway compositor.

Requires sway, wtype, grim, dbus-daemon and gdbus. Pass an executable launcher
to test a package. GHOSTTY_TEST_FLATPAK=1 enables only Flatpak's host-spawn
service on the private bus. GHOSTTY_TEST_WAYLAND_RUNNER may prefix compositor
tools (for example, an isolated Nix environment); the app runs independently.
This does not measure GPU performance or validate a user's native desktop.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").unlink(missing_ok=True)
    runner = shlex.split(os.environ.get("GHOSTTY_TEST_WAYLAND_RUNNER", ""))

    with tempfile.TemporaryDirectory(prefix="ghostty2-wayland-") as directory:
        root = Path(directory)
        env = dict(os.environ)
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
                    "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE", "SWAYSOCK", "I3SOCK"):
            env.pop(key, None)
        for key, name in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                          ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data"),
                          ("XDG_STATE_HOME", "state"), ("XDG_RUNTIME_DIR", "run")):
            (root / name).mkdir(mode=0o700)
            env[key] = str(root / name)
        env.update(
            WLR_BACKENDS="headless", WLR_RENDERER="pixman", WLR_HEADLESS_OUTPUTS="1",
            WLR_LIBINPUT_NO_DEVICES="1", XDG_CURRENT_DESKTOP="sway", XDG_SESSION_TYPE="wayland",
            SWAYSOCK=str(root / "sway.sock"), GDK_BACKEND="wayland", GTK_A11Y="none",
            GDK_DEBUG="opengl,no-portals", LIBGL_ALWAYS_SOFTWARE="1",
        )
        if mesa := env.get("GHOSTTY_TEST_MESA"):
            env.update(
                __EGL_VENDOR_LIBRARY_FILENAMES=f"{mesa}/share/glvnd/egl_vendor.d/50_mesa.json",
                LIBGL_DRIVERS_PATH=f"{mesa}/lib/dri", GBM_BACKENDS_PATH=f"{mesa}/lib/gbm",
            )
        services = ""
        if env.get("GHOSTTY_TEST_FLATPAK") == "1":
            (root / "services").mkdir()
            shutil.copy("/usr/share/dbus-1/services/org.freedesktop.Flatpak.service", root / "services")
            services = f"<servicedir>{root}/services</servicedir>"
        (root / "bus.conf").write_text(f"""<busconfig>
  <type>session</type><listen>unix:tmpdir={root}</listen>{services}
  <policy context="default">
    <allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>
  </policy>
</busconfig>
""")
        (root / "sway.conf").write_text(
            "xwayland disable\nseat seat0 fallback true\noutput * resolution 1280x800\n"
        )
        sessions = root / "sessions"
        sessions.mkdir()
        (root / "child.sh").write_text("""set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dir="$root/sessions/$$"
mkdir "$dir"
printf '\\033]0;Session %s\\007' "$$"
printf '\\033[32mGhostty2 Wayland session %s\\033[0m\\n' "$$"
touch "$dir/ready"
while IFS= read -r line; do
  printf '%s\\n' "$line" >> "$dir/input"
  if [ "$line" = exit ]; then touch "$dir/exited"; exit 0; fi
done
""")
        (root / "ghostty.conf").write_text(f"""initial-window = false
gtk-single-instance = true
window-save-state = never
confirm-close-surface = false
shell-integration = none
quick-terminal-animation-duration = 0
command = /bin/sh {root}/child.sh
keybind = ctrl+shift+t=new_tab
keybind = ctrl+1=goto_tab:1
keybind = ctrl+2=goto_tab:2
keybind = ctrl+shift+e=new_split:right
""")
        processes = []

        def command(arguments):
            if arguments[0] == "wtype":
                # Each invocation adds a virtual keyboard. Allow its keymap
                # and focus events to reach GTK before injecting the first key.
                arguments = ["wtype", "-s", "500"] + arguments[1:]
            return runner + arguments if arguments[0] in ("sway", "swaymsg", "wtype", "grim") else arguments

        def start(arguments, name):
            with (output / f"{name}.log").open("w") as log:
                process = subprocess.Popen(command(arguments), env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process

        def run(arguments):
            result = subprocess.run(command(arguments), env=env, text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise RuntimeError(f"{arguments!r}\n{result.stdout}\n{result.stderr}")
            return result.stdout

        def wait(predicate, description):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if predicate():
                    return
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError(f"A test process exited while waiting for {description}")
                time.sleep(0.1)
            raise RuntimeError(f"Timeout: {description}")

        def type_line(value):
            run(["wtype", "-d", "30", value, "-s", "100", "-k", "Return"])

        def received(session, value):
            path = session / "input"
            return path.exists() and value in path.read_text().splitlines()

        try:
            with (output / "bus.log").open("w") as log:
                bus = subprocess.Popen(
                    ["dbus-daemon", "--nofork", f"--config-file={root}/bus.conf", "--print-address=1"],
                    env=env, stdout=subprocess.PIPE, stderr=log, text=True,
                )
            processes.append(bus)
            env["DBUS_SESSION_BUS_ADDRESS"] = bus.stdout.readline().strip()
            start(["sway", "--unsupported-gpu", "-c", str(root / "sway.conf")], "compositor")
            wait(lambda: (root / "sway.sock").exists(), "Wayland compositor")
            env["WAYLAND_DISPLAY"] = next(
                path.name for path in (root / "run").glob("wayland-*") if not path.name.endswith(".lock")
            )
            start([str(binary), "--config-default-files=false", f"--config-file={root}/ghostty.conf"], "app")
            ipc = None

            def ipc_ready():
                nonlocal ipc
                # Debug/safe builds have a separate application ID. Probe only
                # this test's private bus, which contains no user applications.
                for suffix in ("", "-debug"):
                    app_id = "io.github.pihalf.ghostty2" + suffix
                    object_path = "/" + app_id.replace(".", "/").replace("-", "_")
                    candidate = ["gdbus", "call", "--session", "--dest", app_id,
                                 "--object-path", object_path, "--method"]
                    result = subprocess.run(
                        candidate + ["org.gtk.Actions.List"], env=env, capture_output=True, timeout=5
                    )
                    if result.returncode == 0:
                        ipc = candidate
                        return True
                return False

            wait(ipc_ready, "application IPC")
            toggle = ipc + ["org.gtk.Actions.Activate", "toggle-quick-terminal", "[]", "{}"]
            run(toggle)
            wait(lambda: len(list(sessions.glob("*/ready"))) == 1, "first quick-terminal session")
            first = next(sessions.iterdir())
            # The PTY starts before the layer-shell configure/focus roundtrip.
            time.sleep(0.5)
            type_line("first-input")
            wait(lambda: received(first, "first-input"), "input in first tab")
            run(["wtype", "-M", "ctrl", "-M", "shift", "-k", "t", "-m", "shift", "-m", "ctrl"])
            wait(lambda: len(list(sessions.glob("*/ready"))) == 2, "second quick-terminal session")
            second = next(path for path in sessions.iterdir() if path != first)
            type_line("second-input")
            wait(lambda: received(second, "second-input"), "input in second tab")
            run(["wtype", "-M", "ctrl", "-M", "shift", "-k", "e", "-m", "shift", "-m", "ctrl"])
            wait(lambda: len(list(sessions.glob("*/ready"))) == 3, "split in second tab")
            split = next(path for path in sessions.iterdir() if path not in (first, second))
            type_line("split-input")
            wait(lambda: received(split, "split-input"), "input in split")
            run(["grim", str(output / "quick-terminal.png")])
            run(toggle)
            time.sleep(0.3)
            run(toggle)
            time.sleep(0.3)
            if len(list(sessions.glob("*/ready"))) != 3:
                raise RuntimeError("Hide/show created an unexpected session")
            for session in (first, second, split):
                os.kill(int(session.name), 0)
            run(["wtype", "-M", "ctrl", "-k", "1", "-m", "ctrl"])
            time.sleep(0.3)
            type_line("after-hide-show")
            wait(lambda: received(first, "after-hide-show"), "restored first-tab input")
            # Terminate only the child created by this test, while its tab is
            # inactive. Its split should disappear without stealing focus or
            # closing the other split's process.
            os.kill(int(split.name), signal.SIGTERM)
            wait(lambda: not Path(f"/proc/{split.name}").exists(), "background split exit")
            time.sleep(0.5)
            type_line("after-background-exit")
            wait(lambda: received(first, "after-background-exit"), "focus after background split exit")
            os.kill(int(second.name), 0)
            type_line("exit")
            wait(lambda: (first / "exited").exists(), "first tab process exit")
            time.sleep(0.5)
            os.kill(int(second.name), 0)
            type_line("surviving-tab")
            wait(lambda: received(second, "surviving-tab"), "surviving second tab")
            type_line("exit")
            wait(lambda: (second / "exited").exists(), "second tab process exit")
            result = {
                "passed": True,
                "checks": ["Wayland layer-shell quick terminal", "create two tabs and a split", "type into each PTY",
                           "hide/show preserves all three processes", "switch back to first tab",
                           "background split exit preserves focus and the other split",
                           "closing first process preserves second tab"],
                "first_input": (first / "input").read_text(),
                "second_input": (second / "input").read_text(),
                "split_input": (split / "input").read_text(),
            }
            (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(f"Wayland quick-terminal checks passed; evidence: {output}", flush=True)
        finally:
            shutil.copytree(sessions, output / "sessions", dirs_exist_ok=True)
            # A wrapper such as Nix/proot may not forward SIGTERM to Sway.
            # Ask the compositor on this test's private socket to exit too.
            if (root / "sway.sock").exists():
                try:
                    run(["swaymsg", "-s", env["SWAYSOCK"], "exit"])
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
