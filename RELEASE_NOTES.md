# Ghostty² 1.4.0 beta 1

This is a testing prerelease integrating upstream Ghostty v1.4.0. The previous
stable release remains v1.3.2+ghostty2.3. Do not promote this beta until the
end-to-end comparison recorded in test/beta-acceptance.json is complete.

- Retains macOS quick-terminal tabs and the default global hotkey.
- Retains isolated Ghostty² configuration, branding and installer behavior.
- Adapts retained tabs to upstream surface ownership and clipboard handling.
- Updates to Zig 0.17, GTK 4.18+ and libadwaita 1.7+.
- Keeps bundled crash capture and automatic updating removed.

Beta testing must include existing saved sessions, background processes,
clipboard prompts, close confirmation, tab transfers and supported Wayland
compositors. Back up configuration and saved application state before testing
an upgrade or rollback. Beta and stable builds use the same Ghostty² app ID;
the beta is not a separate application namespace.
