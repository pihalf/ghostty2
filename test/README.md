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

`beta-acceptance.json` tracks the remaining comparison against the prior stable
release. Keep `promotion_allowed` false until all checks have evidence for the
same candidate commit, including native desktop checks and upgrade/rollback.
