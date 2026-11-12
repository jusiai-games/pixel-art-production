from collections import Counter

from PIL import Image, ImageDraw

from style_review import external_edges


LIMITS = {
    "min_overlap": (0, 1),
    "max_color_shift": (0, 1),
    "min_outline_coverage": (0, 1),
    "max_cluster_shift": (0, 1),
    "max_contact_shift": (0, None),
}


def transition_limits(value):
    if not isinstance(value, dict) or value.keys() - LIMITS.keys():
        raise ValueError(f"expected transition limits from {', '.join(LIMITS)}")
    for name, threshold in value.items():
        low, high = LIMITS[name]
        if (type(threshold) not in (int, float) or not low <= threshold < float("inf")
                or high is not None and threshold > high):
            raise ValueError(f"invalid transition limit: {name}")
    return value


def body_pixels(image, effects):
    pixels = {}
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = image.getpixel((x, y))
            if a and (r, g, b) not in effects:
                pixels[x, y] = (r, g, b)
    if not pixels:
        raise ValueError("transition frame has no body pixels after effect colors are excluded")
    return pixels


def color_distribution(pixels):
    counts = Counter(pixels.values())
    return {color: count / len(pixels) for color, count in counts.items()}


def cluster_density(pixels):
    same = total = 0
    for (x, y), color in pixels.items():
        for neighbor in ((x + 1, y), (x, y + 1)):
            if neighbor in pixels:
                total += 1
                same += pixels[neighbor] == color
    return same / total if total else 0


def outline_gaps(size, pixels, outline):
    body = Image.new("RGBA", size)
    for point, color in pixels.items():
        body.putpixel(point, (*color, 255))
    edges = external_edges(body)
    gaps = {point for point in edges if pixels[point] not in outline}
    return 1 - len(gaps) / len(edges), gaps


def compare_transition(before, after, mode, effects, outline, limits):
    left = body_pixels(before, effects)
    right = body_pixels(after, effects)
    left_colors, right_colors = color_distribution(left), color_distribution(right)
    overlap = len(left.keys() & right.keys()) / len(left.keys() | right.keys())
    color_shift = sum(abs(left_colors.get(c, 0) - right_colors.get(c, 0))
                      for c in left_colors.keys() | right_colors.keys()) / 2
    contact_shift = abs(max(y for _, y in left) - max(y for _, y in right))
    cluster_shift = abs(cluster_density(left) - cluster_density(right))
    coverage, gaps = None, None
    if outline:
        a, _ = outline_gaps(before.size, left, outline)
        b, gaps = outline_gaps(after.size, right, outline)
        coverage = [a, b]
    changed = sum(before.getpixel((x, y)) != after.getpixel((x, y))
                  for y in range(before.height) for x in range(before.width))
    failures = ["exact_pose_mismatch"] if mode == "exact" and changed else []
    measured = {
        "min_overlap": overlap,
        "max_color_shift": color_shift,
        "min_outline_coverage": min(coverage) if coverage else None,
        "max_cluster_shift": cluster_shift,
        "max_contact_shift": contact_shift,
    }
    warnings = []
    for name, threshold in limits.items():
        metric = measured[name]
        if metric is None:
            raise ValueError(f"{name} requires outline_colors")
        if (name.startswith("min_") and metric < threshold
                or name.startswith("max_") and metric > threshold):
            warnings.append(name)
    return {
        "changed_pixels": changed, "overlap": overlap, "color_shift": color_shift,
        "outline_coverage": coverage, "cluster_shift": cluster_shift,
        "contact_shift_px": contact_shift, "failures": failures, "warnings": warnings,
    }, gaps


def transition_preview(before, after, gaps):
    scale = 4
    size = before.width * scale
    canvas = Image.new("RGB", (size * 4, size + 22), "#26283A")
    overlay = Image.new("RGBA", before.size)
    for y in range(before.height):
        for x in range(before.width):
            a, b = before.getpixel((x, y)), after.getpixel((x, y))
            if a != b:
                color = "#FFB567" if a[3] and b[3] else "#F16691" if a[3] else "#69C7F6"
                overlay.putpixel((x, y), (*bytes.fromhex(color[1:]), 255))
    outlines = after.copy()
    for point in gaps or ():
        outlines.putpixel(point, (255, 181, 103, 255))
    draw = ImageDraw.Draw(canvas)
    label = "To outline gaps" if gaps is not None else "Outline check off"
    panels = (("From", before), ("To", after), ("Pixel changes", overlay), (label, outlines))
    for index, (label, frame) in enumerate(panels):
        x = index * size
        draw.text((x + 3, 4), label, fill="white")
        scaled = frame.resize((size, size), Image.Resampling.NEAREST)
        canvas.paste(scaled, (x, 22), scaled)
    return canvas
