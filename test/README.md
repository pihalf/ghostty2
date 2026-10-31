# Test Utilities

This directory contains anything related to testing Ghostty that doesn't
fit within the standard Zig testing framework alongside the source.

The beta integration also exercises a built application with isolated temporary
configuration and state:

```sh
nix develop -c sh test/smoke-cli.sh "$PWD/zig-out/bin/ghostty2"
nix develop -c sh test/smoke-x11.sh "$PWD/zig-out/bin/ghostty2"
```

The X11 check starts its own Xvfb display and D-Bus session, launches a PTY,
sends keyboard input, checks the resized terminal dimensions and waits for a
clean application exit. It does not use the user's desktop or configuration.
It verifies basic application behavior; it does not validate visual fidelity,
Wayland compositor integration or the macOS quick terminal.

To compare the shipped Linux bundles, first download the stable release and
the beta CI artifact, then run:

```sh
python3 test/smoke-flatpak.py \
  --baseline /path/to/stable.flatpak \
  --candidate /path/to/beta.flatpak \
  --runtime-installation "$HOME/.local/share/flatpak" \
  --output /path/to/flatpak-acceptance.json
```

This requires Flatpak, Xvfb, xdotool, D-Bus and an installed GNOME 50 runtime.
The runtime installation is read for runtime lookup; both application branches
are installed into a disposable directory. The check switches stable → beta →
stable, validates a shared sample configuration and theme, checks their hashes,
and runs the CLI and graphical checks. It records bundle hashes and installed
commits in the JSON output. Your installed application and profile are not used.

`beta-acceptance.json` tracks the remaining comparison against the prior stable
release. Keep `promotion_allowed` false until all checks have evidence for the
same candidate commit, including native desktop checks and upgrade/rollback.
