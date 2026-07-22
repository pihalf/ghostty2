#!/bin/sh

set -eu

release_base="${GHOSTTY2_RELEASE_BASE:-https://github.com/pihalf/ghostty2/releases/latest/download}"
install_tmp=$(mktemp -d "${TMPDIR:-/tmp}/ghostty2.XXXXXX")
restore_target=
restore_previous=
install_stage=

cleanup() {
    if [ -n "$restore_previous" ] && [ -e "$restore_previous" ] && [ ! -e "$restore_target" ]; then
        mv "$restore_previous" "$restore_target" || true
    fi
    if [ -n "$install_stage" ] && [ -d "$install_stage" ]; then
        rm -rf -- "$install_stage"
    fi
    rm -rf -- "$install_tmp"
}

trap cleanup EXIT
trap 'exit 1' HUP INT TERM

fail() {
    printf 'ghostty2: %s\n' "$*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

download() {
    need curl
    curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
        "$release_base/$1" --output "$install_tmp/$1"
}

verify() {
    asset=$1
    checksum_file="$install_tmp/SHA256SUMS"
    expected=$(awk -v asset="$asset" '$2 == asset { print $1 }' "$checksum_file")
    [ -n "$expected" ] || fail "checksum not found for $asset"

    case $(uname -s) in
        Darwin)
            actual=$(LC_ALL=C shasum -a 256 "$install_tmp/$asset" | awk '{ print $1 }')
            ;;
        *)
            need sha256sum
            actual=$(sha256sum "$install_tmp/$asset" | awk '{ print $1 }')
            ;;
    esac

    [ "$actual" = "$expected" ] || fail "checksum mismatch for $asset"
}

download SHA256SUMS

case $(uname -s) in
    Darwin)
        : "${HOME:?HOME must be set}"
        asset=ghostty2-macos-universal.zip
        download "$asset"
        verify "$asset"

        unpacked="$install_tmp/unpacked"
        mkdir -p "$unpacked"
        /usr/bin/ditto -x -k "$install_tmp/$asset" "$unpacked"
        [ -d "$unpacked/Ghostty2.app" ] || fail "release archive does not contain Ghostty2.app"

        install_dir="${GHOSTTY2_INSTALL_DIR:-$HOME/Applications}"
        target="$install_dir/Ghostty2.app"
        mkdir -p "$install_dir"
        install_stage=$(mktemp -d "$install_dir/.ghostty2.XXXXXX")
        candidate="$install_stage/Ghostty2.app"
        previous="$install_stage/previous-Ghostty2.app"
        if ! mv "$unpacked/Ghostty2.app" "$candidate"; then
            fail "could not stage Ghostty2.app in $install_dir"
        fi
        if [ -e "$target" ]; then
            restore_target=$target
            restore_previous=$previous
            mv "$target" "$previous"
        fi
        if ! mv "$candidate" "$target"; then
            [ ! -e "$previous" ] || mv "$previous" "$target"
            fail "could not install Ghostty2.app"
        fi
        restore_target=
        restore_previous=

        printf 'Installed Ghostty² at %s\n' "$target"
        printf 'Launch it with: open "%s"\n' "$target"
        ;;
    Linux)
        need flatpak
        case $(uname -m) in
            x86_64 | amd64)
                arch=x86_64
                ;;
            aarch64 | arm64)
                arch=aarch64
                ;;
            *)
                fail "no Flatpak release is available for architecture $(uname -m)"
                ;;
        esac

        asset="ghostty2-linux-$arch.flatpak"
        download "$asset"
        verify "$asset"
        flatpak install --user --noninteractive --or-update "$install_tmp/$asset"
        printf 'Installed Ghostty². Launch it with: flatpak run io.github.pihalf.ghostty2\n'
        ;;
    *)
        fail "only macOS and Linux are supported"
        ;;
esac
