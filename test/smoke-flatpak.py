#!/usr/bin/env python3
"""Check stable -> beta -> stable in a disposable Flatpak installation.

Reuse an installed runtime without modifying its installation. Each graphical
check uses its own Xvfb display, session bus and temporary application profile.
This checks package switching and configuration compatibility, not native
desktop behavior, visual parity or macOS state migration.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--runtime-installation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    test_dir = Path(__file__).resolve().parent
    bundles = {"stable": args.baseline.resolve(strict=True), "beta": args.candidate.resolve(strict=True)}
    evidence = {"bundles": {name: {"sha256": digest(path)} for name, path in bundles.items()}, "stages": []}

    with tempfile.TemporaryDirectory(prefix="ghostty2-flatpak-") as directory:
        root = Path(directory)
        env = dict(os.environ)
        for key in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY"):
            env.pop(key, None)
        env.update(
            FLATPAK_USER_DIR=str(root / "installation"),
            FLATPAK_SYSTEM_DIR=str(args.runtime_installation.resolve(strict=True)),
            GHOSTTY_TEST_FLATPAK="1",
        )
        for key, name in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                          ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
                          ("XDG_STATE_HOME", "state"), ("XDG_RUNTIME_DIR", "run")):
            (root / name).mkdir(mode=0o700)
            env[key] = str(root / name)

        def run(*command):
            result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=180)
            if result.returncode:
                raise RuntimeError(f"{command!r} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
            return result.stdout

        launcher = root / "ghostty2"
        launcher.write_text("""#!/bin/sh
set -eu
profile_root=$(dirname "$HOME")
exec env -u LD_LIBRARY_PATH -u __EGL_VENDOR_LIBRARY_FILENAMES -u LIBGL_DRIVERS_PATH -u GBM_BACKENDS_PATH \\
  FLATPAK_USER_DIR=""" + shlex.quote(env["FLATPAK_USER_DIR"]) + """ \\
  FLATPAK_SYSTEM_DIR=""" + shlex.quote(env["FLATPAK_SYSTEM_DIR"]) + """ \\
  flatpak run --user --socket=x11 --nosocket=wayland --filesystem="$profile_root" \\
  --env=HOME="$HOME" --env=GDK_BACKEND=x11 --env=LIBGL_ALWAYS_SOFTWARE=1 \\
  --env=GTK_A11Y=none --env=GDK_DEBUG=opengl,no-portals \\
  --command=env io.github.pihalf.ghostty2 \\
  HOME="$HOME" XDG_CONFIG_HOME="$XDG_CONFIG_HOME" XDG_CACHE_HOME="$XDG_CACHE_HOME" \\
  XDG_STATE_HOME="$XDG_STATE_HOME" /app/bin/ghostty2 "$@"
""")
        # Flatpak sets XDG paths after processing --env. Set the test harness's
        # paths inside the sandbox so its deliberately isolated files are used.
        launcher.chmod(0o755)

        services = root / "services"
        services.mkdir()
        shutil.copy("/usr/share/dbus-1/services/org.freedesktop.Flatpak.service", services)
        bus_config = root / "bus.conf"
        bus_config.write_text(f"""<busconfig>
  <type>session</type>
  <listen>unix:tmpdir={root}</listen>
  <servicedir>{services}</servicedir>
  <policy context="default">
    <allow send_destination="*"/>
    <allow receive_sender="*"/>
    <allow own="*"/>
  </policy>
</busconfig>
""")
        private_session = ["dbus-run-session", f"--config-file={bus_config}", "--", "xvfb-run", "-a"]

        def cli(*arguments):
            # Loading defaults queries the host account through Flatpak's bus.
            # Give CLI calls their own bus and display as well as private files.
            return run(*private_session, str(launcher), *arguments)

        for branch, bundle in bundles.items():
            run("flatpak", "install", "--user", "--no-deps", "--no-related", "--noninteractive", "--bundle", str(bundle))
            evidence["bundles"][branch]["commit"] = run(
                "flatpak", "info", "--user", "--show-commit", "io.github.pihalf.ghostty2", branch
            ).strip()

        config_dir = root / "home/.var/app/io.github.pihalf.ghostty2/config"
        env["XDG_CONFIG_HOME"] = str(config_dir)
        themes = config_dir / "ghostty2/themes"
        themes.mkdir(parents=True, exist_ok=True)
        (themes / "UpgradeRollback").write_text("background = #102030\nforeground = #405060\n")
        (themes.parent / "config.ghostty").write_text(
            "font-size = 17\ntheme = UpgradeRollback\nconfirm-close-surface = true\n"
            "keybind = ctrl+shift+t=new_tab\n"
        )

        def profile_hashes():
            return {str(p.relative_to(config_dir)): digest(p) for p in config_dir.rglob("*") if p.is_file()}

        before = profile_hashes()
        for branch in ("stable", "beta", "stable"):
            run("flatpak", "make-current", "--user", "io.github.pihalf.ghostty2", branch)
            version = cli("+version").splitlines()[0]
            expected = "1.4.0-beta." if branch == "beta" else "1.3.2+ghostty2.3"
            if expected not in version:
                raise RuntimeError(f"Wrong package selected: {version}")
            cli("+validate-config")
            config = cli("+show-config")
            if "font-size = 17\n" not in config or "background = #102030\n" not in config:
                raise RuntimeError(f"Configuration did not survive package switch: {config}")
            graphical = run("sh", str(test_dir / "smoke-x11.sh"), str(launcher))
            if profile_hashes() != before:
                raise RuntimeError("The shared sample configuration or theme was modified")
            stage = {"branch": branch, "version": version, "profile_unchanged": True, "graphical": graphical.strip()}
            if branch == "beta":
                stage["cli"] = run(*private_session, "sh", str(test_dir / "smoke-cli.sh"), str(launcher)).strip()
            evidence["stages"].append(stage)
            print(f"{version}: configuration and packaged GUI checks passed", flush=True)

    evidence["passed"] = True
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Isolated package switch and rollback passed; evidence: {args.output}")


if __name__ == "__main__":
    main()
