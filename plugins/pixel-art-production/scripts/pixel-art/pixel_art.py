import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageChops, ImageDraw
import color_style
from style_review import load_style, review_frame, rgb, write_face_preview, write_preview
from transition_review import compare_transition, transition_limits, transition_preview


DIRECTIONS = ("down", "left", "right", "up")
PROFILES = {
    "character": (32, (16, 28)),
    "tile32": (32, (16, 16)),
    "tile": (16, (8, 8)),
}
MAX_SHEET = 2048
MAX_SOURCE_PIXELS = 4096 * 4096
CHARACTER_SIZES = (16, 24, 32, 48, 64)
FRAME_CONFIG = "character-frame.json"


def profile(kind, *paths, legacy_default=True):
    if kind != "character":
        return PROFILES[kind]
    configs = set()
    for path in paths:
        for directory in path.resolve().parents:
            config = directory / FRAME_CONFIG
            if config.exists():
                configs.add(config)
    if len(configs) > 1:
        raise ValueError("paths span multiple character frame configurations")
    if not configs:
        return PROFILES[kind] if legacy_default else None
    config = configs.pop()
    data = json.loads(config.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or type(data.get("size")) is not int or data["size"] not in CHARACTER_SIZES:
        raise ValueError(f"{config}: expected character size in {CHARACTER_SIZES}")
    cell = data["size"]
    return cell, (cell // 2, cell * 7 // 8)


def lock_character_frame(args):
    if not (args.directory / "art-direction.md").is_file():
        raise ValueError("initialize the game workspace before locking its character frame")
    target = args.directory / FRAME_CONFIG
    if target.exists():
        cell, _ = profile("character", target)
        if cell != args.character_size:
            raise ValueError(f"{target}: character frame is already locked to {cell}x{cell}")
    else:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"size": args.character_size}) + "\n")
    print(f"{target}: {args.character_size}x{args.character_size}")


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


def check(image, label, kind=None, colors=None, size=None, *, soft_alpha=False):
    if size and image.size != size:
        raise ValueError(f"{label}: expected {size}, got {image.size}")
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    if not soft_alpha and sum(histogram[1:255]):
        raise ValueError(f"{label}: alpha must be 0 or 255")
    if not any(histogram[1:]):
        raise ValueError(f"{label}: no visible pixels")
    if kind == "character" and not histogram[0]:
        raise ValueError(f"{label}: character needs transparent background")
    if colors is not None:
        if soft_alpha:
            # Palette entries describe RGB, independent of opacity.
            visible = Image.new("RGBA", image.size)
            visible.paste(image.convert("RGB"), mask=alpha.point([0] + [255] * 255))
        else:
            visible = canonical(image)
        visible_colors = visible.getcolors(maxcolors=65536)
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


def manifest(path, *workspace_paths):
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
    cell, pivot = profile(kind, path, *workspace_paths)
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


def color_scan(args):
    selection = color_style.crop(load_png(args.png), args.crop)
    counts, alpha = color_style.histogram(selection)
    rows = color_style.palette_rows(counts)
    with new_directory(args.out) as stage:
        report = {"source": str(args.png), "crop": args.crop, "alpha": alpha, "palette": rows,
                  "metrics": color_style.measure(counts)[0] if counts else None}
        color_style.write_json(stage / "report.json", report)
        color_style.swatch_report(stage, [(args.png.stem, rows)])
        write_frame(selection, stage / "selection.png")
    print(f"{args.out}: {len(rows)} opaque colors")


def color_build(args):
    config = color_style.read_json(args.config)
    entries = config.get("references") if isinstance(config, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("expected a nonempty references array")
    references, groups = [], []
    ids, selections = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or not slug(entry.get("id")) or entry.get("role") not in color_style.ROLES:
            raise ValueError("each reference needs a lowercase asset id and a valid role")
        name, role, source = entry["id"], entry["role"], entry.get("png")
        if name in ids or not isinstance(source, str) or not source:
            raise ValueError(f"{name}: expected a unique asset id and PNG path")
        ids.add(name)
        path = args.config.parent / source
        region = entry.get("crop")
        selected = color_style.crop(load_png(path), region)
        selection = (path.resolve(), tuple(region or (0, 0, *selected.size)))
        if selection in selections:
            raise ValueError(f"{name}: duplicate PNG selection")
        selections.add(selection)
        counts, alpha = color_style.histogram(selected)
        ignore, ramps = entry.get("ignoreColors", []), entry.get("ramps", {})
        if not isinstance(ignore, list) or not isinstance(ramps, dict):
            raise ValueError(f"{name}: expected an ignoreColors array and ramps object")
        for value in ignore:
            counts.pop(rgb(value), None)
        metrics, ramp_data = color_style.measure(counts, ramps)
        references.append({**entry, "alpha": alpha, "metrics": metrics, "ramps": ramp_data})
        groups.append((name, color_style.palette_rows(counts)))
    built = color_style.summarize(references)
    with new_directory(args.out) as stage:
        color_style.write_json(stage / "profile.json", built)
        color_style.swatch_report(stage, groups)
        for role, group in built["roles"].items():
            if group["referenceCount"]:
                (stage / f"{role}-prompt.md").write_text(color_style.prompt_guide(built, role), encoding="utf-8")
    print(f"{args.out}: {len(references)} reference assets")


def color_candidate(args):
    group = color_style.load_role(args.profile, args.role)
    images, counts, alpha = {}, Counter(), Counter()
    for path in args.png:
        if path.name in images:
            raise ValueError("candidate PNG filenames must be distinct")
        image = load_png(path)
        images[path.name] = image
        colors, opacity = color_style.histogram(image)
        counts.update(colors)
        alpha.update(opacity)
    for value in args.ignore_color:
        counts.pop(rgb(value), None)
    ramps = color_style.read_json(args.ramps) if args.ramps else {}
    if not isinstance(ramps, dict):
        raise ValueError("expected a JSON object of material ramps")
    metrics, ramp_metrics = color_style.measure(counts, ramps)
    before = color_style.palette_rows(counts)
    report = {"role": args.role, "inputs": [str(path) for path in args.png], "alpha": dict(alpha),
              "ignoredColors": args.ignore_color, "palette": before, "ramps": ramp_metrics,
              "comparison": color_style.compare(metrics, group)}
    swatches = [("Candidate", before)]
    with new_directory(args.out) as stage:
        if args.suggest:
            mapping, strength = color_style.suggest_mapping(counts, metrics, group)
            new_counts = {mapping[color]: count for color, count in counts.items()}
            after = color_style.palette_rows(new_counts)
            mapped_ramps = {key: [color_style.hex_color(mapping[rgb(value)]) for value in values]
                            for key, values in ramps.items()}
            suggested_metrics, suggested_ramps = color_style.measure(new_counts, mapped_ramps)
            report.update({
                "suggestion": "improved" if strength else "no_improvement",
                "strength": strength,
                "mapping": {color_style.hex_color(color): color_style.hex_color(mapping[color]) for color in counts},
                "suggestedRamps": suggested_ramps,
                "suggestedComparison": color_style.compare(suggested_metrics, group),
            })
            swatches.append(("Suggested", after))
            for index, (filename, image) in enumerate(images.items()):
                corrected = color_style.recolor(image, mapping)
                write_frame(corrected, stage / "frames" / filename)
                if index == 0:
                    write_frame(color_style.recolor_preview(image, corrected), stage / "preview.png")
        color_style.write_json(stage / "report.json", report)
        color_style.swatch_report(stage, swatches)
    print(f"{args.out}: {args.role} color score {report['comparison']['score']}")


def color_ramp(args):
    profile_data = color_style.read_json(args.profile)
    references = profile_data.get("references") if isinstance(profile_data, dict) else None
    if not isinstance(references, list):
        raise ValueError("profile has no reference list")
    for reference in references:
        if not isinstance(reference, dict) or reference.get("id") != args.reference or reference.get("role") != args.role:
            continue
        ramps = reference.get("ramps")
        ramp = ramps.get(args.material) if isinstance(ramps, dict) else None
        if isinstance(ramp, dict) and isinstance(ramp.get("colors"), list):
            break
    else:
        raise ValueError("reference material ramp was not found for this role")
    samples = [rgb(value) for value in ramp["colors"]]
    colors = color_style.transfer_ramp(samples, rgb(args.base))
    values = [color_style.hex_color(color) for color in colors]
    rows = {row["hex"]: row for row in color_style.palette_rows(dict.fromkeys(colors, 1))}
    with new_directory(args.out) as stage:
        color_style.write_json(stage / "palette.json", values)
        color_style.swatch_report(stage, [(args.material, [rows[value] for value in values])])
    print(f"{args.out}: proposed dark-to-light ramp {' '.join(values)}")



def validate(args):
    colors = palette(args.palette) if args.palette else None
    for path in args.png:
        image = load_png(path)
        size = args.size
        configured = profile("character", path, legacy_default=False) if args.kind == "character" else None
        if configured:
            cell, _ = configured
            if size and size != (cell, cell):
                raise ValueError(f"{path}: character frame requires {cell}x{cell}")
            size = (cell, cell)
        box = check(image, path, args.kind, colors, size)
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
    cell, target_anchor = profile(args.kind, args.png, args.out)
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
    kind, _, cell, _, columns, rows, names, colors = manifest(args.manifest, args.png, args.out)
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
    kind, name, cell, pivot, _, _, names, colors = manifest(args.manifest, args.frames, args.out)
    if args.face_box:
        x, y, width, height = args.face_box
        if kind != "character" or not width or not height or x + width > cell or y + height > cell:
            raise ValueError("face box must have positive dimensions and fit inside a character frame")
    check_frame_files(args.frames, names)
    style = load_style(args.style, colors)
    if args.color_profile and kind != "character":
        raise ValueError("review --color-profile requires a character manifest")
    color_group = color_style.load_role(args.color_profile, "character") if args.color_profile else None
    ignore = {rgb(value) for value in args.color_ignore}
    if ignore and color_group is None:
        raise ValueError("--color-ignore requires --color-profile")
    color_counts = Counter()
    report, preview = [], []
    with new_directory(args.out) as stage:
        for index, frame in enumerate(names):
            path = args.frames / f"{frame}.png"
            before = load_png(path)
            check(before, path, kind, size=(cell, cell))
            after, metrics = review_frame(canonical(before), style)
            check(after, f"{frame} after style review", kind, colors, (cell, cell))
            if color_group is not None:
                color_counts.update(color_style.histogram(after)[0])
            write_frame(after, stage / "frames" / path.name)
            if args.face_box:
                write_face_preview(stage / f"{frame}-face.png", after, args.face_box, style.background)
            report.append({"name": frame, **metrics})
            preview.append((index, before, after, bool(metrics["warnings"])))
            if len(preview) == 16 or index == len(names) - 1:
                write_preview(stage, index // 16 + 1, preview, style.background,
                              pivot if kind == "character" else None)
                preview.clear()
        result = {"sheet": name, "frames": report}
        if color_group is not None:
            for color in ignore:
                color_counts.pop(color, None)
            comparison = color_style.compare(color_style.measure(color_counts)[0], color_group)
            result["colorStyle"] = {"profile": str(args.color_profile), "ignoredColors": args.color_ignore,
                                    **comparison}
        color_style.write_json(stage / "report.json", result)
    warnings = sum(bool(frame["warnings"]) for frame in report)
    print(f"{args.out}: {len(report)} candidate frames, {warnings} with style warnings")


def review_transitions(args):
    data = json.loads(args.map.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("edges"), list) or not data["edges"]:
        raise ValueError("transition map requires a nonempty edges array")
    if not isinstance(data.get("palette"), str) or not data["palette"]:
        raise ValueError("transition map requires a shared body palette path")
    allowed = palette(args.map.parent / data["palette"])
    color_sets = {}
    for key in ("effect_colors", "outline_colors"):
        values = data.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"{key} must be an array of HEX colors")
        color_sets[key] = {rgb(value) for value in values}
    effects, outline = color_sets["effect_colors"], color_sets["outline_colors"]
    if effects & allowed or outline - allowed:
        raise ValueError("effect colors must be separate from the body palette and outline colors must belong to it")
    default_limits = transition_limits(data.get("limits", {}))
    report, seen = [], set()
    with new_directory(args.out) as stage:
        for edge in data["edges"]:
            if not isinstance(edge, dict) or not slug(edge.get("id")) or edge["id"] in seen:
                raise ValueError("transition edges require unique lowercase IDs")
            edge_id = edge["id"]
            seen.add(edge_id)
            mode = edge.get("mode", "pose")
            if mode not in ("exact", "pose"):
                raise ValueError(f"{edge_id}: expected mode exact or pose")
            endpoints = [edge.get(key) for key in ("from", "to")]
            if any(not isinstance(value, str) or Path(value).suffix.lower() != ".png" for value in endpoints):
                raise ValueError(f"{edge_id}: from and to must be frame PNG paths")
            paths = [args.map.parent / value for value in endpoints]
            cell, _ = profile("character", args.map, args.out, *paths)
            images = []
            violations = {}
            for role, path in zip(("from", "to"), paths):
                frame = load_png(path)
                check(frame, path, "character", size=(cell, cell))
                frame = canonical(frame)
                visible = {pixel[:3] for _, pixel in frame.getcolors(cell * cell) if pixel[3]}
                outside = visible - allowed - effects
                if outside:
                    violations[role] = ["#%02X%02X%02X" % color for color in sorted(outside)]
                images.append(frame)
            limits = {**default_limits, **transition_limits(edge.get("limits", {}))}
            result, gaps = compare_transition(*images, mode, effects, outline, limits)
            if violations:
                result["failures"].append("palette_violation")
            preview = f"{edge_id}.png"
            write_frame(transition_preview(*images, gaps), stage / preview)
            report.append({"id": edge_id, "from": endpoints[0], "to": endpoints[1],
                           "mode": mode, "limits": limits, "preview": preview,
                           "off_palette": violations, **result})
        failed = sum(bool(edge["failures"]) for edge in report)
        warned = sum(bool(edge["warnings"]) for edge in report)
        (stage / "report.json").write_text(
            json.dumps({"failed": failed, "warned": warned, "edges": report}, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"{args.out}: {len(report)} transitions, {failed} failed, {warned} with warnings")
    if failed:
        raise SystemExit(1)


def compose(args):
    colors = palette(args.palette) if args.palette else None
    first = load_png(args.png[0])
    width, height = first.size
    columns = args.columns or len(args.png)
    rows = (len(args.png) + columns - 1) // columns
    if args.mode == "repeat":
        if len(args.png) != 1:
            raise ValueError("repeat expects one PNG")
        columns, rows = args.repeat
    elif args.mode == "layers":
        columns = rows = 1
    size = width * columns, height * rows
    if size[0] * size[1] > MAX_SOURCE_PIXELS:
        raise ValueError("composition exceeds the source pixel limit")
    canvas = Image.new("RGBA", size)
    for index, path in enumerate(args.png):
        frame = first if index == 0 else load_png(path)
        check(frame, path, colors=colors, size=first.size, soft_alpha=args.soft_alpha)
        if args.mode == "repeat":
            for y in range(rows):
                for x in range(columns):
                    canvas.paste(frame, (x * width, y * height))
        elif args.mode == "layers":
            canvas.alpha_composite(frame)
        else:
            canvas.paste(frame, (index % columns * width, index // columns * height))
    write_frame(canvas, args.out)


def assemble(args):
    kind, name, cell, pivot, columns, rows, names, colors = manifest(args.manifest, args.frames, args.out)
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


def preview_motion(args):
    if len(args.png) < 2 or len(args.png) != len(args.durations):
        raise ValueError("provide at least two PNGs and one duration per PNG")
    if sum(args.durations) > 65535:
        raise ValueError("total preview duration must be at most 65535 ms")
    cell, _ = profile("character", args.palette, args.out, *args.png)
    colors = palette(args.palette)
    frames = []
    holds = []
    for index, path in enumerate(args.png):
        frame = load_png(path)
        check(frame, path, "character", colors, (cell, cell))
        frame = canonical(frame)
        if frames and ImageChops.difference(frames[-1], frame).getbbox(alpha_only=False) is None:
            holds.append([index, index + 1])
        frames.append(frame)
    if args.loop and ImageChops.difference(frames[-1], frames[0]).getbbox(alpha_only=False) is None:
        holds.append([len(frames), 1])

    with new_directory(args.out) as stage:
        for scale in (1, 4):
            size = (cell * scale, cell * scale)
            display = [frame.resize(size, Image.Resampling.NEAREST) for frame in frames]
            display[0].save(
                stage / f"motion-{scale}x.png", save_all=True, append_images=display[1:],
                duration=args.durations, loop=0 if args.loop else 1,
            )
        report = {
            "loop": args.loop,
            "frames": [
                {"png": str(path), "duration_ms": duration}
                for path, duration in zip(args.png, args.durations)
            ],
            "identical_pairs_1_based": holds,
        }
        (stage / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(frames)} frames, {sum(args.durations)} ms, {len(holds)} identical pairs")


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
    parser = argparse.ArgumentParser(description="Validate, compose, and export pixel-art PNGs.")
    commands = parser.add_subparsers(required=True)
    layouts = commands.add_parser("compose", help="Compose approved PNGs at native resolution.")
    modes = layouts.add_subparsers(dest="mode", required=True)
    for mode in ("sheet", "repeat", "layers"):
        layout = modes.add_parser(mode)
        layout.add_argument("out", type=Path)
        layout.add_argument("png", nargs="+", type=Path)
        layout.add_argument("--palette", type=Path)
        layout.add_argument("--soft-alpha", action="store_true", help="Allow translucent artwork.")
        layout.set_defaults(run=compose, columns=None)
        if mode == "sheet":
            layout.add_argument("--columns", type=positive)
        if mode == "repeat":
            layout.add_argument("--repeat", nargs=2, type=positive, default=(3, 3))

    cmd = commands.add_parser("init", help="Create a local game workspace from templates.")
    cmd.add_argument("directory", type=Path)
    cmd.set_defaults(run=init_project)

    cmd = commands.add_parser("lock-character-frame", help="Set the game-wide character cell once.")
    cmd.add_argument("directory", type=Path)
    cmd.add_argument("character_size", type=int, choices=CHARACTER_SIZES, metavar="size")
    cmd.set_defaults(run=lock_character_frame)

    cmd = commands.add_parser("swatch", help="Render a palette PNG for image-generation input.")
    cmd.add_argument("palette", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.set_defaults(run=swatch)

    cmd = commands.add_parser("color-scan", help="Extract exact opaque colors from a reference PNG or crop.")
    cmd.add_argument("png", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("--crop", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    cmd.set_defaults(run=color_scan)

    cmd = commands.add_parser("color-build", help="Build a role-based OKLCH profile and generation guides.")
    cmd.add_argument("config", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.set_defaults(run=color_build)

    cmd = commands.add_parser("color-ramp", help="Transfer a selected material ramp to a new sRGB base color.")
    cmd.add_argument("profile", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("--role", choices=color_style.ROLES, default="character")
    cmd.add_argument("--reference", required=True)
    cmd.add_argument("--material", required=True)
    cmd.add_argument("--base", required=True, help="The new base color as #RRGGBB.")
    cmd.set_defaults(run=color_ramp)

    for command, suggest in (("color-check", False), ("color-suggest", True)):
        help_text = ("Propose a shared color map for one asset or animation."
                     if suggest else "Compare one asset or animation with a reference profile.")
        cmd = commands.add_parser(command, help=help_text)
        cmd.add_argument("png", type=Path, nargs="+")
        cmd.add_argument("--out", type=Path, required=True)
        cmd.add_argument("--profile", type=Path, required=True)
        cmd.add_argument("--role", choices=color_style.ROLES, required=True)
        cmd.add_argument("--ignore-color", action="append", default=[])
        cmd.add_argument("--ramps", type=Path, help="JSON object of material names to dark-to-light HEX arrays.")
        cmd.set_defaults(run=color_candidate, suggest=suggest)

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
    cmd.add_argument("--color-profile", type=Path, help="Add character color-style diagnostics to the report.")
    cmd.add_argument("--color-ignore", action="append", default=[], help="Exclude an effect HEX from color diagnostics.")
    cmd.set_defaults(run=review)

    cmd = commands.add_parser("review-transitions", help="Check frame boundaries from an animation state map.")
    cmd.add_argument("map", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.set_defaults(run=review_transitions)

    cmd = commands.add_parser("preview-motion", help="Play checked character PNGs at their planned timings.")
    cmd.add_argument("palette", type=Path)
    cmd.add_argument("out", type=Path)
    cmd.add_argument("png", type=Path, nargs="+", help="Static PNGs in playback order.")
    cmd.add_argument("--durations", type=positive, nargs="+", required=True, help="One duration in ms per PNG.")
    cmd.add_argument("--loop", action="store_true", help="Repeat playback and check the last-to-first pair.")
    cmd.set_defaults(run=preview_motion)

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
