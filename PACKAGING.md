# Packaging Ghostty² for Distribution

Ghostty² relies on downstream package maintainers to distribute Ghostty² to
end-users. This document provides guidance to package maintainers on how to
package Ghostty² for distribution.

> [!IMPORTANT]
>
> This document is only accurate for the Ghostty² source alongside it.
> **Do not use this document for older or newer versions of Ghostty²!** If
> you are reading this document in a different version of Ghostty², please
> find the `PACKAGING.md` file alongside that version.

## Source Tarballs

Tagged source archives are available from this fork's GitHub Releases page.
For a tag such as `v1.3.2+ghostty2.1`, use either Git or GitHub's archive:

```
git clone --branch v1.3.2+ghostty2.1 --depth 1 https://github.com/pihalf/ghostty2.git
https://github.com/pihalf/ghostty2/archive/refs/tags/v1.3.2+ghostty2.1.tar.gz
```

> [!WARNING]
>
> GitHub source archives do not contain Ghostty's preprocessed release-tarball
> outputs. They have the same build requirements as a Git checkout. See the
> `README.md` for the complete source-build prerequisites.

## Zig Version

[Zig](https://ziglang.org) is required to build Ghostty². Prior to Zig 1.0,
Zig releases often have breaking changes. Ghostty² requires a specific released
Zig version.

The required version is `minimum_zig_version` in `build.zig.zon`. This source
currently requires Zig 0.17.0.

## Building Ghostty²

The following is a standard example of how to build Ghostty² _for system
packages_. This is not the recommended way to build Ghostty² for your
own system. For that, see the primary README.

1. First, we fetch our dependencies from the internet into a cached directory.
   This is the only step that requires internet access:

```sh
ZIG_GLOBAL_CACHE_DIR=/tmp/offline-cache ./nix/build-support/fetch-zig-cache.sh
```

2. Next, we build Ghostty². This step requires no internet access:

```sh
DESTDIR=/tmp/ghostty2 \
zig build \
  --prefix /usr \
  --system /tmp/offline-cache/p \
  -Doptimize=fast \
  -Dcpu=baseline
```

The build options are covered in the next section, but this will build
and install Ghostty² to `/tmp/ghostty2` with the prefix `/usr` (i.e. the
binary will be at `/tmp/ghostty2/usr/bin/ghostty2`). This style is common
for system packages which separate a build and install step, since the
install step can then be done with a `mv` or `cp` command (from `/tmp/ghostty2`
to wherever the package manager expects it).

### Build Options

Ghostty² uses the Zig build system. You can see all available build options by
running `zig build --help`. The following are options that are particularly
relevant to package maintainers:

- `--prefix`: The installation prefix. Combine with the `DESTDIR` environment
  variable to install to a temporary directory for packaging.

- `--system`: The path to the offline cache directory. This disables
  any package fetching from the internet. This flag also triggers all
  dependencies to be dynamically linked by default. This flag also makes
  the binary a PIE (Position Independent Executable) by default (override
  with `-Dpie`).

- `-Doptimize=fast`: Build with optimizations enabled and safety checks
  disabled. This is the recommended build mode for distribution. I'd prefer
  a safe build but terminal emulators are performance-sensitive and the
  safe build is currently too slow. I plan to improve this in the future.
  Other build modes are available: `debug`, `safe`, and `small`.

- `-Dcpu=baseline`: Build for the "baseline" CPU of the target architecture.
  This avoids building for newer CPU features that may not be available on
  all target machines.

- `-Dtarget=$arch-$os-$abi`: Build for a specific target triple. This is
  often necessary for system packages to specify a specific minimum Linux
  version, glibc, etc. Run `zig targets` to a get a full list of available
  targets.

- `-Dinstalled-exe-path=$prefix/bin/ghostty2`: The absolute path the
  `ghostty2` executable will be installed at, written into the desktop file,
  D-Bus service and systemd user service on Linux. The build can't work this
  out from `--prefix` itself. Without it, those files name the executable
  alone (`ghostty2`), and systemd only looks for that in standard directories
  such as `/usr/bin` and `/usr/local/bin`. Set it for any other prefix, and
  leave `DESTDIR` out of it.

## WebAssembly (libghostty-vt)

libghostty-vt can be built for WebAssembly for use in browsers and other
wasm runtimes:

```sh
zig build -Demit-lib-vt -Dtarget=wasm32-freestanding -Doptimize=small
```

This produces `zig-out/bin/ghostty-vt.wasm`.

Some notes for packaging the wasm module:

- The build enables the `simd128` feature by default. Every browser engine
  has supported it for years (Chrome 91, Firefox 89, Safari 16.4) and it is
  a large performance win for VT parsing. If you target an unusual runtime
  without SIMD support, opt out with `-Dcpu=generic`.

- Optional feature areas can be compiled out with `-Dvt-features` to
  significantly reduce binary size. The flag takes comma-separated
  modifications applied to the default all-enabled feature set,
  `-Dcpu`-style: `+feature` (or bare `feature`) enables, `-feature`
  disables, and the special name `all` refers to every feature. Hyphens
  and underscores are interchangeable in feature names. For example, a
  read-only terminal viewer only needs the render state API:

  ```sh
  zig build -Demit-lib-vt -Dtarget=wasm32-freestanding \
    -Doptimize=small -Dvt-features=-all,+render-state
  ```

  This roughly halves the compressed module size versus the default
  build. An interactive terminal typically wants
  `-Dvt-features=-all,+render-state,+input-encode,+selection,+color`.
  Disabled features drop both their C API exports and any escape
  sequence handling (the sequences are still consumed and safely
  ignored). See the `Features` struct in `src/terminal/build_options.zig`
  for the full list of features and what each one covers.

- `small` is the recommended optimization mode for the web. Running
  the result through [Binaryen's](https://github.com/WebAssembly/binaryen)
  `wasm-opt -O3` shrinks it by roughly a further 10% without hurting
  performance.

- `fast` measures 10-20% faster than `small` on escape-heavy
  terminal workloads, but the artifact is dominated by DWARF debug info.
  If you want the speed, strip it: `wasm-opt -O3 --strip-dwarf` reduces a
  fast build from over 5MB to roughly 1.1MB (versus roughly 0.8MB
  for small). When invoking `wasm-opt`, pass the feature flags for
  what the module uses, e.g. `--enable-simd --enable-bulk-memory
--enable-sign-ext --enable-nontrapping-float-to-int --enable-multivalue
--enable-reference-types`.
