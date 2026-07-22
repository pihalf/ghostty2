#!/bin/sh

set -eu

: "${HOME:?HOME must be set}"

release_base="${GHOSTTY2_RELEASE_BASE:-https://github.com/pihalf/ghostty2/releases/latest/download}"
install_tmp=$(mktemp -d "${TMPDIR:-/tmp}/ghostty2.XXXXXX")
restore_target=
restore_previous=
install_stage=
config_stage=

cleanup() {
    if [ -n "$restore_previous" ] && [ -e "$restore_previous" ] && [ ! -e "$restore_target" ]; then
        mv "$restore_previous" "$restore_target" || true
    fi
    if [ -n "$install_stage" ] && [ -d "$install_stage" ]; then
        rm -rf -- "$install_stage"
    fi
    if [ -n "$config_stage" ] && [ -d "$config_stage" ]; then
        rm -rf -- "$config_stage"
    fi
    rm -rf -- "$install_tmp"
}

trap cleanup EXIT
trap 'exit 1' HUP INT TERM

fail() {
    printf 'ghostty2: %s\n' "$*" >&2
    exit 1
}

status() {
    printf 'ghostty2: %s\n' "$*" >&2
}

need() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

first_existing_file() {
    for candidate_path in "$@"; do
        if [ -f "$candidate_path" ]; then
            printf '%s\n' "$candidate_path"
            return 0
        fi
    done
    return 1
}

first_nonempty_file() {
    for candidate_path in "$@"; do
        if [ -f "$candidate_path" ] && [ -s "$candidate_path" ]; then
            printf '%s\n' "$candidate_path"
            return 0
        fi
    done
    return 1
}

initialize_config() {
    config_target=$1
    import_source=${2:-}
    import_theme_source=${3:-}
    import_choice=no

    if [ -n "$import_source" ]; then
        status "Found an existing Ghostty configuration at $import_source."
        case ${GHOSTTY2_CONFIG_IMPORT:-ask} in
            always)
                import_choice=yes
                ;;
            never)
                ;;
            ask)
                if [ -t 2 ] && [ -r /dev/tty ]; then
                    printf 'ghostty2: Copy its settings into Ghostty²? [y/N] ' >/dev/tty
                    import_reply=
                    if IFS= read -r import_reply </dev/tty; then
                        case $import_reply in
                            y | Y | yes | YES | Yes)
                                import_choice=yes
                                ;;
                        esac
                    fi
                fi
                ;;
            *)
                fail "GHOSTTY2_CONFIG_IMPORT must be ask, always, or never"
                ;;
        esac
    fi

    config_dir=${config_target%/*}
    config_parent=${config_dir%/*}
    config_name=${config_target##*/}
    config_umask=$(umask)
    umask 077
    mkdir -p "$config_parent"
    config_stage=$(mktemp -d "$config_parent/.ghostty2-config.XXXXXX")

    if [ "$import_choice" = yes ]; then
        import_dir=${import_source%/*}
        import_name=${import_source##*/}
        cp -RL "$import_dir/." "$config_stage/"
        if [ -d "$import_theme_source" ] && [ "$import_theme_source" != "$import_dir/themes" ]; then
            mkdir -p "$config_stage/themes"
            cp -RL "$import_theme_source/." "$config_stage/themes/"
        fi
        if [ "$import_name" != "$config_name" ]; then
            [ ! -e "$config_stage/$config_name" ] || \
                fail "cannot import configuration: $config_name is not a file"
            mv -f "$config_stage/$import_name" "$config_stage/$config_name"
        fi
        chmod 600 "$config_stage/$config_name"
        config_result="Copied the configuration directory to $config_dir."
    else
        printf '# Ghostty² configuration\n' >"$config_stage/$config_name"
        chmod 600 "$config_stage/$config_name"
        config_result="Created a clean configuration at $config_target."
    fi

    [ ! -e "$config_dir" ] || fail "configuration directory appeared during setup: $config_dir"
    mv "$config_stage" "$config_dir"
    config_stage=
    umask "$config_umask"
    status "$config_result"
}

setup_config() {
    setup_platform=$1
    host_xdg_config=${XDG_CONFIG_HOME:-$HOME/.config}
    import_theme_source=

    case $setup_platform in
        Darwin)
            config_target="$HOME/Library/Application Support/io.github.pihalf.ghostty2/config.ghostty"
            config_dir=${config_target%/*}
            [ ! -d "$config_dir" ] || return 0
            existing_config=
            existing_config=$(first_existing_file \
                "$config_target" \
                "$HOME/Library/Application Support/io.github.pihalf.ghostty2/config" \
                "$host_xdg_config/ghostty2/config.ghostty" \
                "$host_xdg_config/ghostty2/config") || true
            [ -z "$existing_config" ] || return 0

            import_source=
            import_source=$(first_nonempty_file \
                "$HOME/Library/Application Support/com.mitchellh.ghostty/config.ghostty" \
                "$HOME/Library/Application Support/com.mitchellh.ghostty/config" \
                "$host_xdg_config/ghostty/config.ghostty" \
                "$host_xdg_config/ghostty/config") || true
            if [ "${import_source%/*}" = "$HOME/Library/Application Support/com.mitchellh.ghostty" ]; then
                import_theme_source="$host_xdg_config/ghostty/themes"
            fi
            ;;
        Linux)
            config_target="$HOME/.var/app/io.github.pihalf.ghostty2/config/ghostty2/config.ghostty"
            config_dir=${config_target%/*}
            [ ! -d "$config_dir" ] || return 0
            existing_config=
            existing_config=$(first_existing_file \
                "$config_target" \
                "$HOME/.var/app/io.github.pihalf.ghostty2/config/ghostty2/config") || true
            [ -z "$existing_config" ] || return 0

            import_source=
            import_source=$(first_nonempty_file \
                "$HOME/.var/app/com.mitchellh.ghostty/config/ghostty/config.ghostty" \
                "$HOME/.var/app/com.mitchellh.ghostty/config/ghostty/config" \
                "$host_xdg_config/ghostty/config.ghostty" \
                "$host_xdg_config/ghostty/config") || true
            ;;
        *)
            return 0
            ;;
    esac

    initialize_config "$config_target" "$import_source" "$import_theme_source"
}

download() {
    asset=$1
    need curl
    progress=--silent
    if [ -t 2 ]; then
        progress=--progress-bar
    fi

    status "Downloading $asset..."
    curl --proto '=https' --tlsv1.2 --fail --location --show-error \
        --connect-timeout 15 --retry 3 --retry-delay 1 "$progress" \
        "$release_base/$asset" --output "$install_tmp/$asset"
}

verify() {
    asset=$1
    status "Verifying $asset..."
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

if [ "${GHOSTTY2_INSTALLER_TESTING:-0}" = 1 ]; then
    return 0 2>/dev/null || exit 0
fi

download SHA256SUMS

case $(uname -s) in
    Darwin)
        if [ -n "${GHOSTTY2_INSTALL_DIR:-}" ]; then
            install_dir=$GHOSTTY2_INSTALL_DIR
        elif [ -d "$HOME/Applications/Ghostty2.app" ] && [ -d /Applications/Ghostty2.app ]; then
            fail "Ghostty2.app exists in both ~/Applications and /Applications; set GHOSTTY2_INSTALL_DIR to choose one"
        elif [ -d "$HOME/Applications/Ghostty2.app" ]; then
            install_dir="$HOME/Applications"
        elif [ -d /Applications/Ghostty2.app ]; then
            install_dir=/Applications
        else
            install_dir="$HOME/Applications"
        fi
        target="$install_dir/Ghostty2.app"

        asset=ghostty2-macos-universal.zip
        download "$asset"
        verify "$asset"

        status "Extracting $asset..."
        unpacked="$install_tmp/unpacked"
        mkdir -p "$unpacked"
        /usr/bin/ditto -x -k "$install_tmp/$asset" "$unpacked"
        [ -d "$unpacked/Ghostty2.app" ] || fail "release archive does not contain Ghostty2.app"

        setup_config Darwin
        status "Installing Ghostty2.app in $install_dir..."
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
        setup_config Linux
        status "Installing the Flatpak bundle..."
        flatpak install --user --noninteractive --or-update "$install_tmp/$asset"
        printf 'Installed Ghostty². Launch it with: flatpak run io.github.pihalf.ghostty2\n'
        ;;
    *)
        fail "only macOS and Linux are supported"
        ;;
esac
