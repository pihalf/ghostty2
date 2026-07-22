#!/usr/bin/env python3
"""Generate the Ghostty² app icons from Ghostty's upstream artwork.

The upstream revision is pinned so the generated PNGs do not accumulate
changes when this script is run more than once. The superscript mark is drawn
as a vector path and then composited over the original artwork.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import math
import struct
import subprocess
import sys
from pathlib import Path

import PIL
from PIL import Image, ImageDraw, ImageFilter


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_ART_REVISION = "88b4cd047fa627cdca6781bc7e7dc8b75a2cecb9"
PILLOW_VERSION = "11.1.0"

GNOME_SIZES = (16, 32, 64, 128, 256, 512, 1024, 2048)
GNOME_TARGETS = tuple(
    Path("images/gnome") / f"{prefix}{size}.png"
    for prefix in ("", "nightly-")
    for size in GNOME_SIZES
)
LEGACY_ICON_TARGETS = tuple(
    Path("images/icons") / filename
    for filename in (
        "icon_16.png",
        "icon_16@2x.png",
        "icon_32.png",
        "icon_32@2x.png",
        "icon_128.png",
        "icon_128@2x.png",
        "icon_256.png",
        "icon_256@2x.png",
        "icon_512.png",
        "icon_512@2x.png",
        "icon_1024.png",
        "icon_1024@2x.png",
    )
)
MACOS_IMAGE_TARGETS = tuple(
    Path("macos/Assets.xcassets/AppIconImage.imageset") / filename
    for filename in (
        "macOS-AppIcon-256px-128pt@2x.png",
        "macOS-AppIcon-512px.png",
        "macOS-AppIcon-1024px.png",
    )
)
MACOS_ALTERNATE_ICON_TARGETS = tuple(
    Path("macos/Assets.xcassets/Alternate Icons")
    / f"{name}Image.imageset"
    / "macOS-AppIcon-1024px.png"
    for name in (
        "Blueprint",
        "Chalkboard",
        "Glass",
        "Holographic",
        "Microchip",
        "Paper",
        "Retro",
        "Xray",
    )
)
MACOS_CUSTOM_MARK_TARGET = Path(
    "macos/Assets.xcassets/Custom Icon/"
    "CustomIconGhostty2Mark.imageset/ghostty2-mark.png"
)
RASTER_TARGETS = (
    GNOME_TARGETS
    + LEGACY_ICON_TARGETS
    + MACOS_IMAGE_TARGETS
    + MACOS_ALTERNATE_ICON_TARGETS
)
ICON_COMPOSER_MARK = Path("images/Ghostty.icon/Assets/Ghostty2 Mark.png")
MANIFEST = Path("images/ghostty2-icons.manifest")
CANONICAL_DIGEST_VERSION = b"ghostty2-icon-canonical-rgba-v1\0"
CANONICAL_METADATA_KEYS = (
    "icc_profile",
    "srgb",
    "gamma",
    "chromaticity",
    "dpi",
    "transparency",
)

RGBA = tuple[int, int, int, int]
MarkPalette = tuple[RGBA, RGBA, RGBA, RGBA]
DEFAULT_MARK_PALETTE: MarkPalette = (
    (0, 112, 255, 220),
    (0, 20, 82, 255),
    (21, 139, 255, 255),
    (247, 252, 255, 255),
)
ALTERNATE_MARK_PALETTES: dict[str, MarkPalette] = {
    "BlueprintImage.imageset": DEFAULT_MARK_PALETTE,
    "ChalkboardImage.imageset": (
        (255, 255, 245, 130),
        (31, 31, 29, 255),
        (190, 190, 178, 255),
        (255, 255, 243, 255),
    ),
    "GlassImage.imageset": (
        (20, 20, 20, 130),
        (8, 8, 8, 255),
        (100, 100, 100, 255),
        (245, 245, 245, 255),
    ),
    "HolographicImage.imageset": DEFAULT_MARK_PALETTE,
    "MicrochipImage.imageset": (
        (255, 103, 0, 210),
        (73, 31, 0, 255),
        (255, 92, 0, 255),
        (255, 244, 215, 255),
    ),
    "PaperImage.imageset": (
        (28, 121, 255, 150),
        (0, 46, 143, 255),
        (32, 124, 255, 255),
        (238, 247, 255, 255),
    ),
    "XrayImage.imageset": (
        (255, 255, 255, 130),
        (12, 12, 12, 255),
        (128, 128, 128, 255),
        (248, 248, 248, 255),
    ),
}


def cubic(
    start: tuple[float, float],
    control_a: tuple[float, float],
    control_b: tuple[float, float],
    end: tuple[float, float],
    steps: int = 24,
) -> list[tuple[float, float]]:
    """Sample a cubic Bezier segment."""
    points: list[tuple[float, float]] = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control_a[0]
            + 3 * inverse * t**2 * control_b[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control_a[1]
            + 3 * inverse * t**2 * control_b[1]
            + t**3 * end[1]
        )
        points.append((x, y))
    return points


def superscript_path(
    left: float,
    top: float,
    width: float,
    height: float,
) -> list[tuple[float, float]]:
    """Return a rounded, terminal-style superscript two vector path."""
    normalized = cubic(
        (0.10, 0.28),
        (0.21, 0.05),
        (0.50, 0.00),
        (0.71, 0.08),
    )
    normalized += cubic(
        (0.71, 0.08),
        (0.94, 0.16),
        (0.96, 0.38),
        (0.82, 0.54),
    )[1:]
    normalized += cubic(
        (0.82, 0.54),
        (0.70, 0.67),
        (0.43, 0.78),
        (0.18, 0.93),
    )[1:]
    normalized.append((0.91, 0.93))
    return [
        (left + point[0] * width, top + point[1] * height)
        for point in normalized
    ]


def draw_rounded_path(
    layer: Image.Image,
    points: list[tuple[float, float]],
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    draw = ImageDraw.Draw(layer)
    draw.line(points, fill=color, width=width, joint="curve")
    radius = width / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=color,
        )


def render_mark(
    canvas_size: tuple[int, int],
    bounds: tuple[float, float, float, float],
    palette: MarkPalette = DEFAULT_MARK_PALETTE,
) -> Image.Image:
    """Render a superscript mark with pixel-safe antialiasing."""
    scale = 8
    width, height = canvas_size
    left, top, mark_width, mark_height = bounds
    padding = max(2, mark_width * 0.35)
    crop_left = math.floor(left - padding)
    crop_top = math.floor(top - padding)
    crop_right = math.ceil(left + mark_width + padding)
    crop_bottom = math.ceil(top + mark_height + padding)
    crop_size = (crop_right - crop_left, crop_bottom - crop_top)
    scaled_size = (crop_size[0] * scale, crop_size[1] * scale)
    points = superscript_path(
        (left - crop_left) * scale,
        (top - crop_top) * scale,
        mark_width * scale,
        mark_height * scale,
    )
    glow_color, outline_color, accent_color, core_color = palette

    glow_source = Image.new("RGBA", scaled_size, (0, 0, 0, 0))
    draw_rounded_path(
        glow_source,
        points,
        glow_color,
        max(scale, round(mark_width * scale * 0.25)),
    )
    glow = glow_source.filter(
        ImageFilter.GaussianBlur(max(scale, mark_width * scale * 0.075))
    )

    mark = Image.new("RGBA", scaled_size, (0, 0, 0, 0))
    mark.alpha_composite(glow)
    draw_rounded_path(
        mark,
        points,
        outline_color,
        max(scale, round(mark_width * scale * 0.24)),
    )
    draw_rounded_path(
        mark,
        points,
        accent_color,
        max(scale, round(mark_width * scale * 0.17)),
    )
    draw_rounded_path(
        mark,
        points,
        core_color,
        max(scale, round(mark_width * scale * 0.085)),
    )

    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(
        mark.resize(crop_size, Image.Resampling.LANCZOS),
        (crop_left, crop_top),
    )
    return canvas


def render_pixel_mark(canvas_size: tuple[int, int]) -> Image.Image:
    """Render a hand-tuned 4x6 two for the 16px icon exports."""
    width, height = canvas_size
    pixels = (
        "1111",
        "0001",
        "0010",
        "0100",
        "1000",
        "1111",
    )
    left = round(width * 0.62)
    top = round(height * 0.16)
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for row, pattern in enumerate(pixels):
        for column, value in enumerate(pattern):
            if value == "1":
                draw.point((left + column, top + row), fill=(230, 246, 255, 255))
    return layer


def render_retro_mark(
    canvas_size: tuple[int, int],
    bounds: tuple[float, float, float, float],
) -> Image.Image:
    """Render the Retro alternate icon's superscript as aligned pixel art."""
    left, top, mark_width, mark_height = bounds
    pixels = (
        "1111",
        "0001",
        "0010",
        "0100",
        "1000",
        "1111",
    )
    padding = max(4, mark_width * 0.20)
    crop_left = math.floor(left - padding)
    crop_top = math.floor(top - padding)
    crop_right = math.ceil(left + mark_width + padding)
    crop_bottom = math.ceil(top + mark_height + padding)
    crop_size = (crop_right - crop_left, crop_bottom - crop_top)
    pixel_layer = Image.new("RGBA", crop_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(pixel_layer)
    block_width = mark_width / len(pixels[0])
    block_height = mark_height / len(pixels)
    for row, pattern in enumerate(pixels):
        for column, value in enumerate(pattern):
            if value != "1":
                continue
            x0 = round(left - crop_left + column * block_width)
            y0 = round(top - crop_top + row * block_height)
            x1 = round(left - crop_left + (column + 1) * block_width) - 1
            y1 = round(top - crop_top + (row + 1) * block_height) - 1
            draw.rectangle((x0, y0, x1, y1), fill=(34, 255, 115, 255))

    glow = pixel_layer.filter(
        ImageFilter.GaussianBlur(max(3, mark_width * 0.045))
    )
    result = Image.new("RGBA", crop_size, (0, 0, 0, 0))
    result.alpha_composite(glow)
    result.alpha_composite(pixel_layer)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(result, (crop_left, crop_top))
    return canvas


def mark_bounds(size: tuple[int, int]) -> tuple[float, float, float, float]:
    """Place the mark at the ghost's upper-right, with a small-icon floor."""
    width, height = size
    minimum = min(width, height)
    ratio = min(0.34, 0.16 + 2.8 / minimum)
    mark_width = minimum * ratio
    mark_height = mark_width * 1.08
    return (width * 0.425, height * 0.155, mark_width, mark_height)


def require_upstream_revision(revision: str = UPSTREAM_ART_REVISION) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    )
    if result.returncode == 0:
        return True
    print(
        f"Pinned icon source revision {revision} is missing. "
        "Fetch full history with `git fetch --unshallow` "
        "(or set checkout fetch-depth: 0 in CI), then retry.",
        file=sys.stderr,
    )
    return False


def upstream_asset(relative_path: Path) -> tuple[Image.Image, dict[str, object]]:
    result = subprocess.run(
        ["git", "show", f"{UPSTREAM_ART_REVISION}:{relative_path.as_posix()}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    source = Image.open(io.BytesIO(result.stdout))
    source.load()
    metadata: dict[str, object] = {}
    for key in ("icc_profile", "dpi", "transparency"):
        if key in source.info:
            metadata[key] = source.info[key]
    return source.convert("RGBA"), metadata


def branded_asset(relative_path: Path) -> tuple[Image.Image, dict[str, object]]:
    source, metadata = upstream_asset(relative_path)
    if relative_path.parent.name == "RetroImage.imageset":
        mark = render_retro_mark(source.size, mark_bounds(source.size))
    elif palette := ALTERNATE_MARK_PALETTES.get(relative_path.parent.name):
        mark = render_mark(source.size, mark_bounds(source.size), palette)
    elif min(source.size) <= 20:
        mark = render_pixel_mark(source.size)
    else:
        mark = render_mark(source.size, mark_bounds(source.size))
    source.alpha_composite(mark)
    return source, metadata


def icon_composer_mark() -> Image.Image:
    size = (220, 240)
    return render_mark(size, (24, 18, 172, 204))


def png_bytes(image: Image.Image, metadata: dict[str, object] | None = None) -> bytes:
    output = io.BytesIO()
    image.save(
        output,
        format="PNG",
        compress_level=9,
        **(metadata or {}),
    )
    return output.getvalue()


def hash_value(hasher: object, value: object) -> None:
    """Add a typed, length-delimited metadata value to a SHA-256 digest."""
    if value is None:
        hasher.update(b"N")
    elif isinstance(value, bool):
        hasher.update(b"B1" if value else b"B0")
    elif isinstance(value, int):
        encoded = str(value).encode()
        hasher.update(b"I" + struct.pack(">Q", len(encoded)) + encoded)
    elif isinstance(value, float):
        encoded = value.hex().encode()
        hasher.update(b"F" + struct.pack(">Q", len(encoded)) + encoded)
    elif isinstance(value, str):
        encoded = value.encode("utf-8")
        hasher.update(b"S" + struct.pack(">Q", len(encoded)) + encoded)
    elif isinstance(value, bytes):
        hasher.update(b"Y" + struct.pack(">Q", len(value)) + value)
    elif isinstance(value, (tuple, list)):
        hasher.update(b"L" + struct.pack(">Q", len(value)))
        for item in value:
            hash_value(hasher, item)
    else:
        raise TypeError(f"unsupported canonical metadata type: {type(value).__name__}")


def canonical_png_digest(contents: bytes) -> tuple[str, tuple[int, int]]:
    """Hash decoded pixels and display metadata, independent of PNG encoding."""
    with Image.open(io.BytesIO(contents)) as image:
        if image.format != "PNG":
            raise ValueError(f"expected PNG data, found {image.format or 'unknown'}")
        image.load()
        size = image.size
        metadata = {
            key: image.info[key]
            for key in CANONICAL_METADATA_KEYS
            if key in image.info
        }
        pixels = image.convert("RGBA").tobytes()

    hasher = hashlib.sha256()
    hasher.update(CANONICAL_DIGEST_VERSION)
    hasher.update(struct.pack(">II", *size))
    hasher.update(b"RGBA")
    for key in CANONICAL_METADATA_KEYS:
        encoded_key = key.encode()
        hasher.update(struct.pack(">Q", len(encoded_key)) + encoded_key)
        if key in metadata:
            hasher.update(b"1")
            hash_value(hasher, metadata[key])
        else:
            hasher.update(b"0")
    hasher.update(struct.pack(">Q", len(pixels)))
    hasher.update(pixels)
    return hasher.hexdigest(), size


def generated_assets() -> dict[Path, bytes]:
    assets: dict[Path, bytes] = {}
    for target in RASTER_TARGETS:
        image, metadata = branded_asset(target)
        assets[target] = png_bytes(image, metadata)
    assets[ICON_COMPOSER_MARK] = png_bytes(icon_composer_mark())
    assets[MACOS_CUSTOM_MARK_TARGET] = png_bytes(
        render_mark((1024, 1024), mark_bounds((1024, 1024)))
    )
    manifest_lines = [
        "# Ghostty² canonical icon manifest v1\n",
        "# SHA-256 covers dimensions, decoded RGBA pixels, and display metadata.\n",
    ]
    for relative_path, contents in sorted(
        assets.items(),
        key=lambda item: item[0].as_posix(),
    ):
        digest, (width, height) = canonical_png_digest(contents)
        manifest_lines.append(
            f"{digest}  {width}x{height}  {relative_path.as_posix()}\n"
        )
    assets[MANIFEST] = "".join(manifest_lines).encode()
    return assets


def write_assets(assets: dict[Path, bytes]) -> None:
    for relative_path, contents in assets.items():
        destination = REPOSITORY_ROOT / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        print(relative_path)


def check_assets(assets: dict[Path, bytes]) -> bool:
    valid = True
    for relative_path, expected in assets.items():
        destination = REPOSITORY_ROOT / relative_path
        if not destination.exists():
            valid = False
            print(f"missing: {relative_path}", file=sys.stderr)
            continue
        actual = destination.read_bytes()
        if relative_path == MANIFEST:
            matches = actual == expected
        else:
            try:
                matches = canonical_png_digest(actual) == canonical_png_digest(expected)
            except (OSError, TypeError, ValueError) as error:
                matches = False
                print(f"invalid PNG: {relative_path}: {error}", file=sys.stderr)
        if not matches:
            valid = False
            print(f"out of date: {relative_path}", file=sys.stderr)
    return valid


def contact_sheet(destination: Path) -> None:
    """Create a temporary QA sheet, pixel-zooming small icon exports."""
    paths = (
        GNOME_TARGETS
        + LEGACY_ICON_TARGETS
        + MACOS_IMAGE_TARGETS
        + MACOS_ALTERNATE_ICON_TARGETS
        + (MACOS_CUSTOM_MARK_TARGET,)
    )
    cell_width = 256
    cell_height = 310
    columns = 4
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#20242b")
    draw = ImageDraw.Draw(sheet)
    for index, relative_path in enumerate(paths):
        image = Image.open(REPOSITORY_ROOT / relative_path).convert("RGBA")
        preview_size = 224
        sampling = (
            Image.Resampling.NEAREST
            if image.width < preview_size
            else Image.Resampling.LANCZOS
        )
        preview = image.resize((preview_size, preview_size), sampling)
        column = index % columns
        row = index // columns
        x = column * cell_width + (cell_width - preview_size) // 2
        y = row * cell_height + 8
        sheet.paste(preview, (x, y), preview)
        label = f"{relative_path.name} ({image.width}px)"
        draw.text((column * cell_width + 10, row * cell_height + 242), label, fill="white")
        digest, _ = canonical_png_digest(
            (REPOSITORY_ROOT / relative_path).read_bytes()
        )
        draw.text(
            (column * cell_width + 10, row * cell_height + 266),
            digest[:16],
            fill="#9eabc2",
        )
    sheet.save(destination, format="PNG", compress_level=9)


def main() -> int:
    if PIL.__version__ != PILLOW_VERSION:
        print(
            f"Pillow {PILLOW_VERSION} is required; found {PIL.__version__}. "
            "Install images/requirements.txt.",
            file=sys.stderr,
        )
        return 2

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in icons differ from generated output",
    )
    parser.add_argument(
        "--contact-sheet",
        type=Path,
        help="write a visual QA contact sheet after generating or checking",
    )
    args = parser.parse_args()

    if not require_upstream_revision():
        return 2

    assets = generated_assets()
    valid = check_assets(assets) if args.check else True
    if not args.check:
        write_assets(assets)
    if args.contact_sheet:
        contact_sheet(args.contact_sheet)
        print(args.contact_sheet)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
