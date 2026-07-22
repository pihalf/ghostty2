#!/usr/bin/env python3
"""Generate the Ghostty² app icons from Ghostty's upstream artwork.

The upstream revision is pinned so the generated PNGs do not accumulate
changes when this script is run more than once. The Ghostty² badge is drawn as
vector geometry and then composited over the original artwork.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
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
ICON_COMPOSER_CONFIG = Path("images/Ghostty.icon/icon.json")
ICON_COMPOSER_BASE_TARGETS = tuple(
    Path("images/Ghostty.icon/Assets") / filename
    for filename in (
        "Ghostty.png",
        "Inner Bevel 6px.png",
        "Screen Effects.png",
        "Screen.png",
        "gloss.png",
    )
)
ICON_COMPOSER_MARK_POSITION = (147, -237)
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
BadgePalette = tuple[RGBA, RGBA, RGBA, RGBA]
DEFAULT_BADGE_PALETTE: BadgePalette = (
    (0, 112, 255, 220),
    (0, 20, 82, 255),
    (21, 139, 255, 255),
    (247, 252, 255, 255),
)
ALTERNATE_BADGE_PALETTES: dict[str, BadgePalette] = {
    "BlueprintImage.imageset": DEFAULT_BADGE_PALETTE,
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
    "HolographicImage.imageset": DEFAULT_BADGE_PALETTE,
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
    for x, y in points:
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=color,
        )


def render_badge(
    canvas_size: tuple[int, int],
    bounds: tuple[float, float, float, float],
    palette: BadgePalette = DEFAULT_BADGE_PALETTE,
) -> Image.Image:
    """Render a rounded Ghostty² badge with pixel-safe antialiasing."""
    scale = 8
    left, top, badge_width, badge_height = bounds
    badge_size = min(badge_width, badge_height)
    padding = max(2, badge_size * 0.18)
    crop_left = math.floor(left - padding)
    crop_top = math.floor(top - padding)
    crop_right = math.ceil(left + badge_width + padding)
    crop_bottom = math.ceil(top + badge_height + padding)
    crop_size = (crop_right - crop_left, crop_bottom - crop_top)
    scaled_size = (crop_size[0] * scale, crop_size[1] * scale)

    badge_box = (
        (left - crop_left) * scale,
        (top - crop_top) * scale,
        (left - crop_left + badge_width) * scale,
        (top - crop_top + badge_height) * scale,
    )
    radius = round(badge_size * scale * 0.20)
    glow_color, outline_color, accent_color, core_color = palette

    glow_source = Image.new("RGBA", scaled_size, (0, 0, 0, 0))
    ImageDraw.Draw(glow_source).rounded_rectangle(
        badge_box,
        radius=radius,
        fill=glow_color,
    )
    glow = glow_source.filter(
        ImageFilter.GaussianBlur(max(scale, badge_size * scale * 0.055))
    )

    badge = Image.new("RGBA", scaled_size, (0, 0, 0, 0))
    badge.alpha_composite(glow)
    draw = ImageDraw.Draw(badge)
    draw.rounded_rectangle(badge_box, radius=radius, fill=outline_color)

    rim_inset = badge_size * scale * 0.035
    rim_box = tuple(
        coordinate + rim_inset if index < 2 else coordinate - rim_inset
        for index, coordinate in enumerate(badge_box)
    )
    draw.rounded_rectangle(
        rim_box,
        radius=max(scale, round(radius - rim_inset)),
        fill=core_color,
    )

    tile_inset = badge_size * scale * 0.075
    tile_box = tuple(
        coordinate + tile_inset if index < 2 else coordinate - tile_inset
        for index, coordinate in enumerate(badge_box)
    )
    draw.rounded_rectangle(
        tile_box,
        radius=max(scale, round(radius - tile_inset)),
        fill=accent_color,
    )

    points = superscript_path(
        (left - crop_left + badge_width * 0.20) * scale,
        (top - crop_top + badge_height * 0.14) * scale,
        badge_width * 0.60 * scale,
        badge_height * 0.68 * scale,
    )
    draw_rounded_path(
        badge,
        points,
        outline_color,
        max(scale, round(badge_size * scale * 0.20)),
    )
    draw_rounded_path(
        badge,
        points,
        core_color,
        max(scale, round(badge_size * scale * 0.135)),
    )

    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(
        badge.resize(crop_size, Image.Resampling.LANCZOS),
        (crop_left, crop_top),
    )
    return canvas


def render_pixel_badge(canvas_size: tuple[int, int]) -> Image.Image:
    """Render a hand-tuned badge for the 16px icon exports."""
    width, height = canvas_size
    pixels = (
        "1111",
        "0001",
        "0011",
        "0110",
        "1100",
        "1111",
    )
    left = width - 8
    top = max(1, round(height * 0.06))
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rectangle((left, top, left + 7, top + 7), fill=(0, 20, 82, 255))
    draw.rectangle((left + 1, top + 1, left + 6, top + 6), fill=(21, 139, 255, 255))
    for row, pattern in enumerate(pixels):
        for column, value in enumerate(pattern):
            if value == "1":
                draw.point(
                    (left + 2 + column, top + 1 + row),
                    fill=(247, 252, 255, 255),
                )
    return layer


def render_retro_badge(
    canvas_size: tuple[int, int],
    bounds: tuple[float, float, float, float],
) -> Image.Image:
    """Render the Retro alternate icon's badge as aligned pixel art."""
    left, top, badge_width, badge_height = bounds
    pixels = (
        "1111",
        "0001",
        "0011",
        "0110",
        "1100",
        "1111",
    )
    padding = max(4, badge_width * 0.20)
    crop_left = math.floor(left - padding)
    crop_top = math.floor(top - padding)
    crop_right = math.ceil(left + badge_width + padding)
    crop_bottom = math.ceil(top + badge_height + padding)
    crop_size = (crop_right - crop_left, crop_bottom - crop_top)
    pixel_layer = Image.new("RGBA", crop_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(pixel_layer)
    outer = (
        round(left - crop_left),
        round(top - crop_top),
        round(left - crop_left + badge_width),
        round(top - crop_top + badge_height),
    )
    border = max(1, round(badge_width * 0.06))
    draw.rectangle(outer, fill=(0, 25, 8, 255))
    draw.rectangle(
        (
            outer[0] + border,
            outer[1] + border,
            outer[2] - border,
            outer[3] - border,
        ),
        outline=(34, 255, 115, 255),
        width=border,
        fill=(0, 55, 20, 255),
    )
    digit_left = left - crop_left + badge_width * 0.23
    digit_top = top - crop_top + badge_height * 0.17
    digit_width = badge_width * 0.54
    digit_height = badge_height * 0.66
    block_width = digit_width / len(pixels[0])
    block_height = digit_height / len(pixels)
    for row, pattern in enumerate(pixels):
        for column, value in enumerate(pattern):
            if value != "1":
                continue
            x0 = round(digit_left + column * block_width)
            y0 = round(digit_top + row * block_height)
            x1 = round(digit_left + (column + 1) * block_width) - 1
            y1 = round(digit_top + (row + 1) * block_height) - 1
            draw.rectangle((x0, y0, x1, y1), fill=(34, 255, 115, 255))

    glow = pixel_layer.filter(
        ImageFilter.GaussianBlur(max(3, badge_width * 0.045))
    )
    result = Image.new("RGBA", crop_size, (0, 0, 0, 0))
    result.alpha_composite(glow)
    result.alpha_composite(pixel_layer)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(result, (crop_left, crop_top))
    return canvas


def badge_bounds(size: tuple[int, int]) -> tuple[float, float, float, float]:
    """Place the badge in the screen's upper-right, with a small-icon floor."""
    width, height = size
    minimum = min(width, height)
    ratio = min(0.44, 0.245 + 3 / minimum)
    badge_size = minimum * ratio
    return (width * 0.52, height * 0.145, badge_size, badge_size)


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


def upstream_bytes(relative_path: Path) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{UPSTREAM_ART_REVISION}:{relative_path.as_posix()}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def upstream_asset(relative_path: Path) -> tuple[Image.Image, dict[str, object]]:
    source = Image.open(io.BytesIO(upstream_bytes(relative_path)))
    source.load()
    metadata: dict[str, object] = {}
    for key in ("icc_profile", "dpi", "transparency"):
        if key in source.info:
            metadata[key] = source.info[key]
    return source.convert("RGBA"), metadata


def branded_asset(relative_path: Path) -> tuple[Image.Image, dict[str, object]]:
    source, metadata = upstream_asset(relative_path)
    if relative_path.parent.name == "RetroImage.imageset":
        badge = render_retro_badge(source.size, badge_bounds(source.size))
    elif palette := ALTERNATE_BADGE_PALETTES.get(relative_path.parent.name):
        badge = render_badge(source.size, badge_bounds(source.size), palette)
    elif min(source.size) <= 20:
        badge = render_pixel_badge(source.size)
    else:
        badge = render_badge(source.size, badge_bounds(source.size))
    source.alpha_composite(badge)
    return source, metadata


def icon_composer_mark() -> Image.Image:
    size = (300, 300)
    return render_badge(size, (23, 23, 254, 254))


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
    for target in ICON_COMPOSER_BASE_TARGETS:
        assets[target] = upstream_bytes(target)
    assets[ICON_COMPOSER_MARK] = png_bytes(icon_composer_mark())
    assets[MACOS_CUSTOM_MARK_TARGET] = png_bytes(
        render_badge((1024, 1024), badge_bounds((1024, 1024)))
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


def check_icon_composer_config() -> bool:
    """Verify the generated badge is the configured branded icon layer."""
    config_path = REPOSITORY_ROOT / ICON_COMPOSER_CONFIG
    try:
        config = json.loads(config_path.read_text())
        layers = [
            layer
            for group in config["groups"]
            for layer in group.get("layers", ())
            if layer.get("name") == "Ghostty²"
        ]
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"invalid Icon Composer config: {error}", file=sys.stderr)
        return False

    expected_position = {
        "scale": 1,
        "translation-in-points": list(ICON_COMPOSER_MARK_POSITION),
    }
    if len(layers) != 1:
        print("Icon Composer config must contain one Ghostty² layer", file=sys.stderr)
        return False
    layer = layers[0]
    if (
        layer.get("image-name") != ICON_COMPOSER_MARK.name
        or layer.get("position") != expected_position
    ):
        print("Icon Composer Ghostty² layer is out of date", file=sys.stderr)
        return False
    return True


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
    valid = check_icon_composer_config()
    if args.check:
        valid = check_assets(assets) and valid
    if not args.check:
        write_assets(assets)
    if args.contact_sheet:
        contact_sheet(args.contact_sheet)
        print(args.contact_sheet)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
