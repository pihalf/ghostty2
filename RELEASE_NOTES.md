# Ghostty²

Ghostty² now uses its own configuration namespace instead of reading Ghostty's
configuration. Existing Ghostty files are never changed. During first setup,
the installer offers to copy detected Ghostty settings; declining starts with
Ghostty²'s built-in defaults. The app icon now uses a high-contrast corner
badge so its 2 remains legible at Dock and launcher sizes.

Ghostty² combines Ghostty's fast, native terminal with the two iTerm2 workflows this fork is built around:

- A global Quake-style terminal, enabled by default with <kbd>Control</kbd>+<kbd>`</kbd>.
- Multiple persistent tabs in the quick terminal: **Command+T** on macOS and **Control+Shift+T** on Linux.
- Independent Ghostty² configuration, with optional import during installation.
- A high-contrast Ghostty² icon badge that remains readable at small sizes.
- The local crash-capture dependencies and bundled macOS updater are omitted; “Check for Updates…” opens this fork's Releases page.
- A universal macOS app plus x86_64 and aarch64 Linux Flatpak bundles, all covered by `SHA256SUMS`.

Install the latest release:

```sh
curl -fsSL https://raw.githubusercontent.com/pihalf/ghostty2/main/install.sh | sh
```

The macOS app is ad-hoc signed. When it is downloaded through a browser, use **Open** from Finder's context menu on first launch if Gatekeeper asks for confirmation.

The Linux quick terminal requires Wayland and a compositor that supports layer shell. Normal windows and tabs work on X11, but the drop-down terminal does not. See the [README](https://github.com/pihalf/ghostty2#readme) for details.
