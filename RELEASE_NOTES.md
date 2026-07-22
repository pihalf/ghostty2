# Ghostty²

Ghostty² combines Ghostty's fast, native terminal with the two iTerm2 workflows this fork is built around:

- A global Quake-style terminal, enabled by default with <kbd>Control</kbd>+<kbd>`</kbd>.
- Multiple persistent tabs in the quick terminal: **Command+T** on macOS and **Control+Shift+T** on Linux.
- No Sentry, Breakpad, analytics, crash uploads, background update checks, or automatic updater.
- A universal macOS app plus x86_64 and aarch64 Linux Flatpak bundles, all covered by `SHA256SUMS`.

Install the latest release:

```sh
curl -fsSL https://raw.githubusercontent.com/pihalf/ghostty2/main/install.sh | sh
```

The macOS app is ad-hoc signed. When it is downloaded through a browser, use **Open** from Finder's context menu on first launch if Gatekeeper asks for confirmation.

The Linux quick terminal requires Wayland and a compositor that supports layer shell. Normal windows and tabs work on X11, but the drop-down terminal does not. See the [README](https://github.com/pihalf/ghostty2#readme) for details.
