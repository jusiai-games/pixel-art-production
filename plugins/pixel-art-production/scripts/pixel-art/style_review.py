import json
import re
from collections import deque
from dataclasses import dataclass

from PIL import Image, ImageDraw


SIDES = ((0, -1), (0, 1), (-1, 0), (1, 0))
LIGHT_SIDES = {
    "upper_left": (0, 2), "upper_right": (0, 3),
    "lower_left": (1, 2), "lower_right": (1, 3),
}


@dataclass
class Style:
    remap: dict
    outline_colors: set
    outline_replace: dict
    outline_minimum: float
    light_sides: tuple
    light_ignore: set
    light_tolerance: float
    background: tuple


def rgb(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"invalid style color: {value!r}")
    return tuple(bytes.fromhex(value[1:]))


def brightness(color):
    r, g, b = color
    return (2126 * r + 7152 * g + 722 * b) / 10000


def object_field(data, field):
    value = data.get(field, {})
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def color_list(value, allowed):
    if not isinstance(value, list):
        raise ValueError("expected a list of style colors")
    colors = [rgb(color) for color in value]
    if not set(colors) <= allowed:
        raise ValueError("style target colors must be in the manifest palette")
    return colors


def load_style(path, palette):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("style must be a JSON object")
    ramps = {name: color_list(values, palette) for name, values in object_field(data, "ramps").items()}
    if any(not ramp or ramp != sorted(ramp, key=brightness) for ramp in ramps.values()):
        raise ValueError("material ramps must list colors from dark to light")
    remap = {}
    for source, material in object_field(data, "source_materials").items():
        if not isinstance(material, str) or material not in ramps:
            raise ValueError(f"{source}: unknown material ramp {material!r}")
        color = rgb(source)
        if color in palette:
            raise ValueError(f"{source}: source_materials only maps off-palette colors")
        remap[color] = min(ramps[material], key=lambda candidate: abs(brightness(candidate) - brightness(color)))

    outline = object_field(data, "outline")
    outline_colors = set(color_list(outline.get("colors", []), palette))
    replace = {rgb(source): rgb(target) for source, target in object_field(outline, "replace").items()}
    if not set(replace.values()) <= outline_colors:
        raise ValueError("outline replacements must target declared outline colors")
    minimum = outline.get("minimum_coverage", 0)
    if type(minimum) not in (int, float) or not 0 <= minimum <= 1 or (minimum and not outline_colors):
        raise ValueError("outline minimum_coverage must be 0–1 and requires outline colors")

    light = object_field(data, "light")
    direction = light.get("direction")
    if direction is not None and (not isinstance(direction, str) or direction not in LIGHT_SIDES):
        raise ValueError("light direction must be upper_left, upper_right, lower_left or lower_right")
    ignored = set(color_list(light.get("ignore_colors", []), palette))
    tolerance = light.get("tolerance", 0)
    if type(tolerance) not in (int, float) or not 0 <= tolerance <= 255:
        raise ValueError("light tolerance must be 0–255")
    return Style(remap, outline_colors, replace, minimum, LIGHT_SIDES.get(direction, ()),
                 ignored, tolerance, rgb(data.get("preview_background", "#393452")))


def external_edges(image):
    width, height = image.size
    alpha = image.getchannel("A")
    outside = {(-1, -1)}
    queue = deque(outside)
    edges = {}
    while queue:
        x, y = queue.popleft()
        for side, (dx, dy) in enumerate(SIDES):
            nx, ny = x + dx, y + dy
            if not (-1 <= nx <= width and -1 <= ny <= height):
                continue
            if 0 <= nx < width and 0 <= ny < height and alpha.getpixel((nx, ny)):
                edges.setdefault((nx, ny), []).append(side ^ 1)
            elif (nx, ny) not in outside:
                outside.add((nx, ny))
                queue.append((nx, ny))
    return edges


def review_frame(image, style):
    edges = external_edges(image)
    after = image.copy()
    material_changes = outline_changes = 0
    for y in range(image.height):
        for x in range(image.width):
            point = (x, y)
            *color, alpha = image.getpixel(point)
            if not alpha:
                continue
            color = tuple(color)
            if point in edges and color in style.outline_replace:
                replacement = style.outline_replace[color]
                outline_changes += replacement != color
            else:
                replacement = style.remap.get(color, color)
                material_changes += replacement != color
            after.putpixel(point, (*replacement, alpha))

    edge_colors = {point: after.getpixel(point)[:3] for point in edges}
    coverage = None
    if style.outline_colors:
        coverage = sum(color in style.outline_colors for color in edge_colors.values()) / len(edges)
    warnings = []
    if coverage is not None and coverage < style.outline_minimum:
        warnings.append("outline_coverage")

    delta = samples = None
    if style.light_sides:
        facing, away = [], []
        for point, sides in edges.items():
            color = edge_colors[point]
            if color in style.outline_colors or color in style.light_ignore:
                continue
            groups = {side in style.light_sides for side in sides}
            if len(groups) == 1:
                (facing if True in groups else away).append(brightness(color))
        samples = {"facing": len(facing), "opposite": len(away)}
        if min(samples.values()) < 4:
            warnings.append("light_insufficient_samples")
        else:
            delta = sum(facing) / len(facing) - sum(away) / len(away)
            if delta < -style.light_tolerance:
                warnings.append("light_direction")
    return after, {
        "material_pixels_changed": material_changes, "outline_pixels_changed": outline_changes,
        "outline_coverage": round(coverage, 4) if coverage is not None else None,
        "light_delta": round(delta, 2) if delta is not None else None,
        "light_samples": samples, "warnings": warnings,
    }


def write_face_preview(path, frame, box, background):
    x, y, width, height = box
    zoom = 8
    top = 20
    left = frame.width + 22
    preview = Image.new("RGB", (max(145, left + width * zoom + 6),
                                top + max(frame.height, height * zoom) + 6), "#242633")
    draw = ImageDraw.Draw(preview)
    draw.text((6, 4), "1x", fill="#ECEAF2")
    draw.text((left, 4), "Face 8x", fill="#ECEAF2")
    tile = Image.new("RGB", frame.size, background)
    tile.paste(frame, (0, 0), frame)
    preview.paste(tile, (6, top))
    face = tile.crop((x, y, x + width, y + height))
    face = face.resize((width * zoom, height * zoom), Image.Resampling.NEAREST)
    preview.paste(face, (left, top))
    for col in range(1, width):
        px = left + col * zoom
        draw.line((px, top, px, top + face.height - 1), fill="#383B4B")
    for row in range(1, height):
        py = top + row * zoom
        draw.line((left, py, left + face.width - 1, py), fill="#383B4B")
    preview.save(path)


def write_preview(folder, page, pairs, background, pivot):
    cell = pairs[0][1].width
    size = cell * 3
    width = 2 * size + 18
    height = size + 29
    columns = min(4, len(pairs))
    rows = (len(pairs) + columns - 1) // columns
    preview = Image.new("RGB", (width * columns, height * rows), "#242633")
    draw = ImageDraw.Draw(preview)
    for index, (number, before, after, warned) in enumerate(pairs):
        x, y = index % columns * width + 6, index // columns * height + 7
        draw.text((x, y), f"{number:03}  Input / Candidate", fill="#F0D383" if warned else "#ECEAF2")
        for offset, frame in enumerate((before, after)):
            left = x + offset * (size + 6)
            top = y + 16
            tile = Image.new("RGB", (size, size), background)
            image = frame.resize(tile.size, Image.Resampling.NEAREST)
            tile.paste(image, (0, 0), image)
            preview.paste(tile, (left, top))
            if pivot is not None:
                px, py = left + pivot[0] * 3, top + pivot[1] * 3
                draw.line((px - 3, py, px + 3, py), fill="#F0D383")
                draw.line((px, py - 3, px, py + 3), fill="#F0D383")
    preview.save(folder / f"preview-{page:02}.png")
