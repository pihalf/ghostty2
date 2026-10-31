#!/bin/sh
# Exercise the packaged executable, with no access to the user's configuration.
set -eu
binary=$(realpath "${1:?usage: smoke-cli.sh /absolute/path/to/ghostty2}")
smoke_dir=$(mktemp -d)
trap 'rm -rf "$smoke_dir"' EXIT HUP INT TERM
export HOME="$smoke_dir/home"
export XDG_CONFIG_HOME="$smoke_dir/config"
export XDG_CACHE_HOME="$smoke_dir/cache"
export XDG_STATE_HOME="$smoke_dir/state"
unset GHOSTTY_RESOURCES_DIR GHOSTTY_CONFIG_DIR
mkdir -p "$HOME" "$XDG_CONFIG_HOME/ghostty" "$XDG_CONFIG_HOME/ghostty2"
printf 'font-size = 23\n' > "$XDG_CONFIG_HOME/ghostty/config.ghostty"
printf 'font-size = 17\n' > "$XDG_CONFIG_HOME/ghostty2/config"
upstream_before=$(cksum < "$XDG_CONFIG_HOME/ghostty/config.ghostty")

"$binary" +version | tee "$smoke_dir/version"
grep -F 'Ghostty²' "$smoke_dir/version"
grep -F '1.4.0-beta.' "$smoke_dir/version"

# Legacy fork configuration must load, and upstream configuration must not.
"$binary" +show-config > "$smoke_dir/legacy"
grep -x 'font-size = 17' "$smoke_dir/legacy"

# The current filename takes precedence over the fork's legacy filename.
printf 'font-size = 19\n' > "$XDG_CONFIG_HOME/ghostty2/config.ghostty"
"$binary" +show-config > "$smoke_dir/current"
grep -x 'font-size = 19' "$smoke_dir/current"
"$binary" +validate-config

# Invalid configuration must be reported, not silently accepted.
printf 'font-size = not-a-number\n' > "$XDG_CONFIG_HOME/ghostty2/config.ghostty"
if "$binary" +validate-config > "$smoke_dir/invalid" 2>&1; then
    echo 'invalid configuration was accepted' >&2
    exit 1
fi
test "$upstream_before" = "$(cksum < "$XDG_CONFIG_HOME/ghostty/config.ghostty")"
echo 'Packaged CLI and configuration isolation smoke tests passed'
