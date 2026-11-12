import argparse
import hashlib
import json
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw
from style_review import load_style, review_frame, write_face_preview, write_preview


DIRECTIONS = ("down", "left", "right", "up")
PROFILES = {
    "character": (32, (16, 28)),
    "tile32": (32, (16, 16)),
    "tile": (16, (8, 8)),
}
MAX_SHEET = 2048
MAX_SOURCE_PIXELS = 4096 * 4096


def slug(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]*", value)


def palette(path):
    colors = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(colors, list) or not colors or any(
        not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
        for color in colors
    ):
        raise ValueError(f"{path}: expected a JSON array of #RRGGBB colors")
    return {tuple(bytes.fromhex(color[1:])) for color in colors}


def load_png(path):
    with path.open("rb") as source:
        header = source.read(26)
        source.seek(0)
        with Image.open(source) as png:
            if png.format != "PNG" or png.get_format_mimetype() == "image/apng":
                raise ValueError(f"{path}: expected a static PNG")
            if png.width * png.height > MAX_SOURCE_PIXELS:
                raise ValueError(f"{path}: exceeds the source pixel limit")
            if png.mode not in {"RGBA", "RGB", "P"} or header[24] > 8:
                raise ValueError(f"{path}: export an 8-bit RGB/RGBA or indexed PNG")
            png.verify()
        source.seek(0)
        with Image.open(source) as png:
            return png.convert("RGBA")


def check(image, label, kind=None, colors=None, size=None):
    if size and image.size != size:
        raise ValueError(f"{label}: expected {size}, got {image.size}")
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    if sum(histogram[1:255]):
        raise ValueError(f"{label}: alpha must be 0 or 255")
    if not histogram[255]:
        raise ValueError(f"{label}: no visible pixels")
    if kind == "character" and not histogram[0]:
        raise ValueError(f"{label}: character needs transparent background")
    if colors is not None:
        visible_colors = canonical(image).getcolors(maxcolors=65536)
        if visible_colors is None:
            raise ValueError(f"{label}: too many visible colors for the palette")
        invalid = {(r, g, b) for _, (r, g, b, a) in visible_colors if a} - colors
        if invalid:
            examples = ", ".join("#%02X%02X%02X" % color for color in sorted(invalid)[:5])
            raise ValueError(f"{label}: {len(invalid)} colors outside the palette ({examples})")
    return alpha.getbbox()


def canonical(image):
    clean = Image.new("RGBA", image.size)
    clean.paste(image, mask=image.getchannel("A"))
    return clean


def manifest(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("kind") not in tuple(PROFILES) or not slug(data.get("name")):
        raise ValueError(f"{path}: expected kind (character/tile32/tile) and lowercase name")
    kind, name = data["kind"], data["name"]
    if not isinstance(data.get("palette"), str) or not data["palette"]:
        raise ValueError(f"{path}: palette path is required")
    if kind == "character":
        frame_count = data.get("frames_per_direction")
        if type(frame_count) is not int or not 1 <= frame_count <= 64:
            raise ValueError(f"{path}: frames_per_direction must be 1–64")
        directions = data.get("directions", list(DIRECTIONS))
        if (not isinstance(directions, list) or not directions or
                directions != [direction for direction in DIRECTIONS if direction in directions]):
            raise ValueError(f"{path}: directions must be a nonempty subset in down/left/right/up order")
        columns = data.get("columns", frame_count)
        if type(columns) is not int or not 1 <= columns <= frame_count or frame_count % columns:
            raise ValueError(f"{path}: columns must evenly divide frames_per_direction")
        names = [f"{name}_{direction}_{index:02}" for direction in directions for index in range(frame_count)]
    else:
        columns, tiles = data.get("columns"), data.get("tiles")
        if not isinstance(tiles, list) or not tiles or not all(map(slug, tiles)):
            raise ValueError(f"{path}: tiles must be a nonempty list of lowercase IDs")
        if len(set(tiles)) != len(tiles) or type(columns) is not int or not 1 <= columns <= len(tiles):
            raise ValueError(f"{path}: duplicate tile IDs or invalid column count")
        names = [f"{name}_{tile}" for tile in tiles]
    cell, pivot = PROFILES[kind]
    rows = (len(names) + columns - 1) // columns
    if max(columns, rows) * cell > MAX_SHEET:
        raise ValueError(f"{path}: assembled sheet exceeds {MAX_SHEET}px on an axis")
    return kind, name, cell, pivot, columns, rows, names, palette(path.parent / data["palette"])


@contextmanager
def new_directory(target):
    if target.exists():
        raise ValueError(f"{target}: output directory already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as temporary:
        stage = Path(temporary) / "result"
        stage.mkdir()
        yield stage
        stage.rename(target)


def write_frame(image, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    stream = target.open("xb")
    try:
        with stream:
            image.save(stream, format="PNG")
    except BaseException:
        target.unlink()
        raise


def init_project(args):
    templates = Path(__file__).with_name("templates")
    with new_directory(args.directory) as stage:
        for folder in ("references", "sources", "jobs", "palettes", "manifests",
                       "styles", "work", "approved", "exports"):
            (stage / folder).mkdir()
        for template, destination in (
            ("art-direction.md", "art-direction.md"),
            ("job.md", "jobs/_template.md"),
            ("character.json", "manifests/hero_idle.json"),
            ("style.json", "styles/default.json"),
            ("palette.json", "palettes/project.json"),
        ):
            shutil.copyfile(templates / template, stage / destination)
    print(f"{args.directory}: local game workspace created")


def swatch(args):
    colors = sorted(palette(args.palette), key=lambda color: (sum(color), color))
    size = 24
    columns = min(8, len(colors))
    rows = (len(colors) + columns - 1) // columns
    image = Image.new("RGBA", (columns * size, rows * size))
    for index, color in enumerate(colors):
        x, y = (index % columns) * size, (index // columns) * size
        image.paste((*color, 255), (x, y, x + size, y + size))
    write_frame(image, args.out)
    print(f"{args.out}: {len(colors)} color swatches")



def validate(args):
    colors = palette(args.palette) if args.palette else None
    for path in args.png:
        image = load_png(path)
        box = check(image, path, args.kind, colors, args.size)
        print(f"{path}: {image.width}x{image.height}, content box={box}")


def inspect_grid(args):
    image = load_png(args.png)
    scale = args.scale
    ox, oy = args.origin
    if ox >= scale or oy >= scale or scale < 2:
        raise ValueError("grid scale must be at least 2 and each origin offset must be below scale")
    alpha = image.getchannel("A")
    pixels = image.load()
    overlay = ImageDraw.Draw(image)
    mixed = []
    # Include partial cells along the canvas edge when the grid has an offset.
    for y in range(oy - scale if oy else 0, image.height, scale):
        for x in range(ox - scale if ox else 0, image.width, scale):
            left, top = max(0, x), max(0, y)
            right, bottom = min(x + scale, image.width), min(y + scale, image.height)
            first = pixels[left, top]
            if all(
                pixel == first or (pixel[3] == first[3] == 0)
                for row in range(top, bottom)
                for col in range(left, right)
                for pixel in (pixels[col, row],)
            ):
                continue
            mixed.append([left, top, right, bottom])
    for left, top, right, bottom in mixed:
        overlay.rectangle((left, top, right - 1, bottom - 1), outline="#FF4D68")
    partial_alpha = sum(alpha.histogram()[1:255])
    aligned = not (ox or oy or image.width % scale or image.height % scale)
    report = {
        "source": str(args.png), "size": image.size,
        "scale": scale, "origin": args.origin,
        "canvas_aligned": aligned, "partial_alpha_pixels": partial_alpha,
        "grid_matches": aligned and not mixed and not partial_alpha,
        "nonuniform_cells": mixed,
    }
    with new_directory(args.out) as stage:
        write_frame(image, stage / "grid.png")
        (stage / "report.json").write_text(json.dumps(report) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(mixed)} nonuniform cells, {partial_alpha} partial-alpha pixels, "
          f"canvas aligned: {aligned}")


def normalize(args):
    cell, target_anchor = PROFILES[args.kind]
    colors = palette(args.palette) if args.palette else None
    image = load_png(args.png)
    check(image, args.png, args.kind, colors)
    image = canonical(image)
    if args.scale != 1:
        if any(length % args.scale for length in image.size):
            raise ValueError("source size must be divisible by --scale")
        reduced = image.resize(
            (image.width // args.scale, image.height // args.scale), Image.Resampling.NEAREST
        )
        if reduced.resize(image.size, Image.Resampling.NEAREST).tobytes() != image.tobytes():
            raise ValueError("source pixels are not exact integer blocks. Repair the grid before export.")
        image = reduced
    if args.anchor is not None:
        if args.kind != "character":
            raise ValueError("--anchor applies to characters only")
        x, y = args.anchor
        if not (0 <= x <= image.width and 0 <= y <= image.height):
            raise ValueError("--anchor lies outside the reduced canvas")
        dx, dy = target_anchor[0] - x, target_anchor[1] - y
        left, top, right, bottom = image.getbbox()
        if left + dx < 0 or top + dy < 0 or right + dx > cell or bottom + dy > cell:
            raise ValueError("anchor alignment would clip visible pixels")
        canvas = Image.new("RGBA", (cell, cell))
        canvas.paste(image, (dx, dy))
        image = canvas
    check(image, args.out, args.kind, colors, (cell, cell))
    write_frame(image, args.out)


def split(args):
    kind, _, cell, _, columns, rows, names, colors = manifest(args.manifest)
    if args.defer_palette:
        colors = None
    cell *= args.scale
    width = columns * cell + (columns - 1) * args.gap + 2 * args.margin
    height = rows * cell + (rows - 1) * args.gap + 2 * args.margin
    image = load_png(args.png)
    check(image, args.png, colors=colors, size=(width, height))
    with new_directory(args.out) as stage:
        remaining = image.getchannel("A")
        for index, name in enumerate(names):
            x = args.margin + (index % columns) * (cell + args.gap)
            y = args.margin + (index // columns) * (cell + args.gap)
            rect = (x, y, x + cell, y + cell)
            frame = image.crop(rect)
            check(frame, name, kind, colors)
            remaining.paste(0, rect)
            write_frame(canonical(frame), stage / f"{name}.png")
        if remaining.getbbox():
            raise ValueError("visible pixels in the sheet margin, gaps or unused cells")


def check_frame_files(folder, names):
    expected = {f"{frame}.png" for frame in names}
    actual = {path.name for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".png"}
    if expected != actual:
        raise ValueError(f"frame files differ. Missing: {sorted(expected - actual)}. Extra: {sorted(actual - expected)}")


def review(args):
    kind, name, cell, pivot, _, _, names, colors = manifest(args.manifest)
    if args.face_box:
        x, y, width, height = args.face_box
        if kind != "character" or not width or not height or x + width > cell or y + height > cell:
            raise ValueError("face box must have positive dimensions and fit inside a character frame")
    check_frame_files(args.frames, names)
    style = load_style(args.style, colors)
    report, preview = [], []
    with new_directory(args.out) as stage:
        for index, frame in enumerate(names):
            path = args.frames / f"{frame}.png"
            before = load_png(path)
            check(before, path, kind, size=(cell, cell))
            after, metrics = review_frame(canonical(before), style)
            check(after, f"{frame} after style review", kind, colors, (cell, cell))
            write_frame(after, stage / "frames" / path.name)
            if args.face_box:
                write_face_preview(stage / f"{frame}-face.png", after, args.face_box, style.background)
            report.append({"name": frame, **metrics})
            preview.append((index, before, after, bool(metrics["warnings"])))
            if len(preview) == 16 or index == len(names) - 1:
                write_preview(stage, index // 16 + 1, preview, style.background,
                              pivot if kind == "character" else None)
                preview.clear()
        (stage / "report.json").write_text(
            json.dumps({"sheet": name, "frames": report}, indent=2) + "\n", encoding="utf-8"
        )
    warnings = sum(bool(frame["warnings"]) for frame in report)
    print(f"{args.out}: {len(report)} candidate frames, {warnings} with style warnings")


def assemble(args):
    kind, name, cell, pivot, columns, rows, names, colors = manifest(args.manifest)
    check_frame_files(args.frames, names)
    width, height = columns * cell, rows * cell
    sheet = Image.new("RGBA", (width, height))
    sprites = []
    for index, frame in enumerate(names):
        path = args.frames / f"{frame}.png"
        image = load_png(path)
        check(image, path, kind, colors, (cell, cell))
        x, y = (index % columns) * cell, (index // columns) * cell
        sheet.paste(canonical(image), (x, y))
        sprites.append({"name": frame, "x": x, "y": y})
    with new_directory(args.out) as stage:
        png = stage / f"{name}.png"
        write_frame(sheet, png)
        metadata = {
            "version": 1, "kind": kind, "width": width, "height": height,
            "cell": cell, "ppu": 32, "pivotX": pivot[0] / cell, "pivotY": 1 - pivot[1] / cell,
            "sha256": hashlib.sha256(png.read_bytes()).hexdigest(), "sprites": sprites,
        }
        (stage / f"{name}.sprite.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{args.out / png.name}: {width}x{height}, {len(sprites)} sprites")


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return number


def positive(value):
    number = nonnegative(value)
    if number == 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def main():
    parser = argparse.ArgumentParser(description="Validate and build pixel-art sheets for Unity.")
    commands = parser.add_subparsers(required=True)
    cmd = commands.add_parser("init", help="Create a local game workspace from templates.")
    cmd.add_argument("directory", type=Path)
    cmd.set_defaults(run=init_project)

    cmd = commands.add_parser("swatch", help="Render a palette PNG for image-generation input.")
    cmd.add_argument("palette", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.set_defaults(run=swatch)

    cmd = commands.add_parser("validate", help="Check raw PNGs.")
    cmd.add_argument("png", type=Path, nargs="+")
    cmd.add_argument("--kind", choices=PROFILES)
    cmd.add_argument("--palette", type=Path)
    cmd.add_argument("--size", type=positive, nargs=2)
    cmd.set_defaults(run=validate)

    cmd = commands.add_parser("inspect-grid", help="Mark nonuniform cells in an enlarged source PNG.")
    cmd.add_argument("png", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("--scale", type=positive, required=True)
    cmd.add_argument("--origin", type=nonnegative, nargs=2, default=(0, 0), metavar=("X", "Y"))
    cmd.set_defaults(run=inspect_grid)

    cmd = commands.add_parser("normalize", help="Normalize one PNG to the profile canvas.")
    cmd.add_argument("png", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("--kind", choices=PROFILES, required=True)
    cmd.add_argument("--palette", type=Path)
    cmd.add_argument("--scale", type=positive, default=1)
    cmd.add_argument("--anchor", type=nonnegative, nargs=2, metavar=("X", "Y"))
    cmd.set_defaults(run=normalize)

    cmd = commands.add_parser("split", help="Extract a known grid in manifest order.")
    cmd.add_argument("manifest", type=Path)
    cmd.add_argument("png", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("--scale", type=positive, default=1)
    cmd.add_argument("--margin", type=nonnegative, default=0)
    cmd.add_argument("--gap", type=nonnegative, default=0)
    cmd.add_argument("--defer-palette", action="store_true", help="Defer palette checks to style review.")
    cmd.set_defaults(run=split)

    cmd = commands.add_parser("review", help="Apply explicit style corrections and write review candidates.")
    cmd.add_argument("manifest", type=Path)
    cmd.add_argument("style", type=Path)
    cmd.add_argument("frames", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("--face-box", type=nonnegative, nargs=4, metavar=("X", "Y", "W", "H"))
    cmd.set_defaults(run=review)

    cmd = commands.add_parser("assemble", help="Build a sheet and Unity metadata.")
    cmd.add_argument("manifest", type=Path)
    cmd.add_argument("frames", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.set_defaults(run=assemble)

    args = parser.parse_args()
    try:
        if getattr(args, "size", None):
            args.size = tuple(args.size)
        args.run(args)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
