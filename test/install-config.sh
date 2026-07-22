#!/bin/sh

set -eu

test_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo_dir=$(dirname "$test_dir")

GHOSTTY2_INSTALLER_TESTING=1
export GHOSTTY2_INSTALLER_TESTING
. "$repo_dir/install.sh"

test_tmp=$(mktemp -d "${TMPDIR:-/tmp}/ghostty2-install-test.XXXXXX")
finish() {
    rm -rf -- "$test_tmp"
    cleanup
}
trap finish EXIT

mkdir -p "$test_tmp/old-source"
ln -s old-source "$test_tmp/old"
old_config="$test_tmp/old/config"
printf 'keybind = super+t=unbind\n' >"$old_config"
printf 'font-family = monospace\n' >"$test_tmp/old/included.ghostty"
mkdir -p "$test_tmp/old/themes"
printf 'background = 000000\n' >"$test_tmp/old/themes/custom"
printf 'foreground = ffffff\n' >"$test_tmp/shared-theme"
ln -s "$test_tmp/shared-theme" "$test_tmp/old/themes/linked"

imported_config="$test_tmp/imported/config.ghostty"
GHOSTTY2_CONFIG_IMPORT=always
export GHOSTTY2_CONFIG_IMPORT
initialize_config "$imported_config" "$old_config"
cmp "$old_config" "$imported_config"
cmp "$test_tmp/old/included.ghostty" "$test_tmp/imported/included.ghostty"
cmp "$test_tmp/old/themes/custom" "$test_tmp/imported/themes/custom"
cmp "$test_tmp/shared-theme" "$test_tmp/imported/themes/linked"
test ! -L "$test_tmp/imported/themes/linked"

clean_config="$test_tmp/clean/config.ghostty"
GHOSTTY2_CONFIG_IMPORT=never
export GHOSTTY2_CONFIG_IMPORT
initialize_config "$clean_config" "$old_config"
grep -Fqx '# Ghostty² configuration' "$clean_config"
grep -Fqx 'keybind = super+t=unbind' "$old_config"

fresh_config="$test_tmp/fresh/config.ghostty"
initialize_config "$fresh_config" ""
grep -Fqx '# Ghostty² configuration' "$fresh_config"

noninteractive_config="$test_tmp/noninteractive/config.ghostty"
GHOSTTY2_CONFIG_IMPORT=ask
export GHOSTTY2_CONFIG_IMPORT
initialize_config "$noninteractive_config" "$old_config" 2>"$test_tmp/noninteractive.log"
grep -Fqx '# Ghostty² configuration' "$noninteractive_config"

found_config=$(first_existing_file "$test_tmp/missing" "$old_config")
test "$found_config" = "$old_config"

empty_config="$test_tmp/empty"
: >"$empty_config"
found_config=$(first_nonempty_file "$empty_config" "$old_config")
test "$found_config" = "$old_config"

directory_config="$test_tmp/config-directory"
mkdir -p "$directory_config"
found_config=$(first_nonempty_file "$directory_config" "$old_config")
test "$found_config" = "$old_config"

malformed_source="$test_tmp/malformed-source"
mkdir -p "$malformed_source/config.ghostty"
printf 'font-size = 12\n' >"$malformed_source/config"
if (
    GHOSTTY2_CONFIG_IMPORT=always
    export GHOSTTY2_CONFIG_IMPORT
    initialize_config "$test_tmp/malformed-target/config.ghostty" "$malformed_source/config"
) 2>"$test_tmp/malformed.log"; then
    printf 'malformed import unexpectedly succeeded\n' >&2
    exit 1
fi
test ! -e "$test_tmp/malformed-target"
grep -Fq 'config.ghostty is not a file' "$test_tmp/malformed.log"

HOME="$test_tmp/home"
XDG_CONFIG_HOME="$HOME/.config"
export HOME XDG_CONFIG_HOME
mkdir -p "$XDG_CONFIG_HOME/ghostty"
printf 'font-size = 14\n' >"$XDG_CONFIG_HOME/ghostty/config"
GHOSTTY2_CONFIG_IMPORT=always
export GHOSTTY2_CONFIG_IMPORT
setup_config Darwin
macos_config="$HOME/Library/Application Support/io.github.pihalf.ghostty2/config.ghostty"
grep -Fqx 'font-size = 14' "$macos_config"
grep -Fqx 'font-size = 14' "$XDG_CONFIG_HOME/ghostty/config"
printf 'font-size = 99\n' >"$XDG_CONFIG_HOME/ghostty/config"
setup_config Darwin
grep -Fqx 'font-size = 14' "$macos_config"

HOME="$test_tmp/app-support-home"
XDG_CONFIG_HOME="$HOME/.config"
export HOME XDG_CONFIG_HOME
old_app_support="$HOME/Library/Application Support/com.mitchellh.ghostty"
mkdir -p "$old_app_support" "$XDG_CONFIG_HOME/ghostty/themes"
printf 'font-size = 16\n' >"$old_app_support/config.ghostty"
printf 'background = 111111\n' >"$XDG_CONFIG_HOME/ghostty/themes/imported-theme"
setup_config Darwin
new_app_support="$HOME/Library/Application Support/io.github.pihalf.ghostty2"
grep -Fqx 'font-size = 16' "$new_app_support/config.ghostty"
grep -Fqx 'background = 111111' "$new_app_support/themes/imported-theme"

HOME="$test_tmp/linux-home"
XDG_CONFIG_HOME="$HOME/.config"
export HOME XDG_CONFIG_HOME
old_flatpak="$HOME/.var/app/com.mitchellh.ghostty/config/ghostty"
mkdir -p "$XDG_CONFIG_HOME/ghostty/themes" "$old_flatpak/themes"
printf 'font-family = host\n' >"$XDG_CONFIG_HOME/ghostty/config.ghostty"
printf 'host theme\n' >"$XDG_CONFIG_HOME/ghostty/themes/conflict"
printf 'font-family = flatpak\n' >"$old_flatpak/config.ghostty"
printf 'flatpak theme\n' >"$old_flatpak/themes/conflict"
setup_config Linux
linux_config="$HOME/.var/app/io.github.pihalf.ghostty2/config/ghostty2/config.ghostty"
grep -Fqx 'font-family = flatpak' "$linux_config"
grep -Fqx 'flatpak theme' "${linux_config%/*}/themes/conflict"
grep -Fqx 'font-family = host' "$XDG_CONFIG_HOME/ghostty/config.ghostty"

printf 'installer configuration tests passed\n'
