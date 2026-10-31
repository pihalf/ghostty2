#!/bin/sh
# Keep the X server, session bus, activated services and app away from user state.
set -eu
binary=$(realpath "${1:?usage: smoke-x11.sh /absolute/path/to/ghostty2}")
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
smoke_session=$(mktemp -d)
trap 'rm -rf "$smoke_session"' EXIT HUP INT TERM
export HOME="$smoke_session/home"
export XDG_CONFIG_HOME="$smoke_session/config"
export XDG_CACHE_HOME="$smoke_session/cache"
export XDG_STATE_HOME="$smoke_session/state"
export XDG_RUNTIME_DIR="$smoke_session/run"
mkdir -m 700 "$HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_STATE_HOME" "$XDG_RUNTIME_DIR"
unset DBUS_SESSION_BUS_ADDRESS DBUS_STARTER_ADDRESS DBUS_STARTER_BUS_TYPE
export GTK_A11Y=none
export GDK_DEBUG=opengl,no-portals
if [ -n "${GHOSTTY_TEST_MESA:-}" ]; then
    export __EGL_VENDOR_LIBRARY_FILENAMES="$GHOSTTY_TEST_MESA/share/glvnd/egl_vendor.d/50_mesa.json"
    export LIBGL_DRIVERS_PATH="$GHOSTTY_TEST_MESA/lib/dri"
    export GBM_BACKENDS_PATH="$GHOSTTY_TEST_MESA/lib/gbm"
fi
cat > "$smoke_session/bus.conf" <<EOF
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=$smoke_session</listen>
  <policy context="default">
    <allow send_destination="*"/>
    <allow receive_sender="*"/>
    <allow own="*"/>
  </policy>
</busconfig>
EOF
xvfb-run -a -e /dev/stderr -s '-screen 0 1280x800x24' \
    dbus-run-session --config-file="$smoke_session/bus.conf" -- \
    python3 "$script_dir/smoke-x11.py" "$binary"
