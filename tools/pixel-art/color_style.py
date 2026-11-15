"""Reference PNG selection, color profiles and recolor candidates."""

import json
import math
from collections import Counter
from statistics import median

from PIL import Image, ImageDraw

from color_space import oklch, to_srgb
from style_review import rgb


ROLES = ("character", "environment", "effect")
QUANTILES = (("p10", .10), ("p50", .50), ("p90", .90))
# Initial tolerances in OKLCH units, degrees and color counts.
METRICS = {
    "lightness": (.30, .035),
    "chroma": (.30, .020),
    "contrast": (.20, .06),
    "shadowHueShift": (.10, 12),
    "paletteSize": (.10, 2),
}
MIN_CHROMA = .025


def hex_color(color):
    return "#%02X%02X%02X" % color


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def crop(image, region):
    if region is None:
        return image
    if (not isinstance(region, (list, tuple)) or len(region) != 4
            or any(type(value) is not int for value in region)):
        raise ValueError("crop requires four integers: x y width height")
    x, y, width, height = region
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > image.width or y + height > image.height:
        raise ValueError("crop must fit inside the PNG")
    return image.crop((x, y, x + width, y + height))


def histogram(image):
    opaque = Counter()
    alpha = Counter()
    for red, green, blue, opacity in image.getdata():
        alpha[opacity] += 1
        if opacity == 255:
            opaque[red, green, blue] += 1
    return opaque, {
        "transparent": alpha[0],
        "partial": sum(count for opacity, count in alpha.items() if 0 < opacity < 255),
        "opaque": alpha[255],
    }


def quantiles(weighted):
    weighted = sorted(weighted)
    total = sum(count for _, count in weighted)
    result = {}
    index, cumulative = 0, weighted[0][1]
    for name, fraction in QUANTILES:
        rank = math.ceil(total * fraction)
        while cumulative < rank:
            index += 1
            cumulative += weighted[index][1]
        result[name] = weighted[index][0]
    return result


def wrap(angle):
    return (angle + 180) % 360 - 180


def measure(counts, ramps=None):
    if not counts:
        raise ValueError("selection has no opaque colors")
    colors = {color: oklch(color) for color in counts}
    lightness = quantiles((colors[color][0], count) for color, count in counts.items())
    chroma = quantiles((colors[color][1], count) for color, count in counts.items())
    result = {
        "lightness": lightness,
        "chroma": chroma,
        "contrast": lightness["p90"] - lightness["p10"],
        "paletteSize": len(counts),
    }
    ramp_data = {}
    for name, values in (ramps or {}).items():
        if not isinstance(values, list) or len(values) < 3:
            raise ValueError(f"{name}: ramp needs shadow, base and highlight samples")
        samples = [rgb(value) for value in values]
        if any(color not in colors for color in samples):
            raise ValueError(f"{name}: ramp colors must occur as opaque pixels in the selection")
        levels = [colors[color] for color in samples]
        if any(left[0] >= right[0] for left, right in zip(levels, levels[1:])):
            raise ValueError(f"{name}: ramp colors must increase in OKLCH lightness")
        shadow, base, highlight = levels[0], levels[len(levels) // 2], levels[-1]
        ramp = {
            "colors": [hex_color(color) for color in samples],
            "lightnessSteps": [right[0] - left[0] for left, right in zip(levels, levels[1:])],
            "lightnessSpan": highlight[0] - shadow[0],
        }
        if min(shadow[1], base[1]) >= MIN_CHROMA:
            ramp["shadowHueShift"] = wrap(shadow[2] - base[2])
        ramp_data[name] = ramp
    shifts = [ramp["shadowHueShift"] for ramp in ramp_data.values() if "shadowHueShift" in ramp]
    if shifts:
        result["shadowHueShift"] = circular_center(shifts)
    return result, ramp_data


def circular_center(values):
    # Pick the observed angle with the smallest total circular distance as the unwrap origin.
    origin = min(values, key=lambda angle: sum(abs(wrap(value - angle)) for value in values))
    return wrap(origin + median(wrap(value - origin) for value in values))


def palette_rows(counts):
    total = sum(counts.values())
    rows = []
    for color, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])):
        light, chroma, hue = oklch(color)
        rows.append({
            "hex": hex_color(color), "pixels": count, "share": count / total,
            "L": light, "C": chroma, "H": hue if chroma >= MIN_CHROMA else None,
        })
    return rows


def swatch_report(folder, groups):
    rows = sum(1 + min(32, len(colors)) for _, colors in groups)
    image = Image.new("RGB", (270, 20 * rows), "#F4F1EC")
    draw = ImageDraw.Draw(image)
    y = 0
    for name, colors in groups:
        draw.text((8, y + 3), f"{name} ({len(colors)} colors)", fill="#201C26")
        y += 20
        for row in colors[:32]:
            draw.rectangle((8, y + 2, 38, y + 17), fill=row["hex"])
            draw.text((47, y + 3), f'{row["hex"]}   {row["share"]:.1%}', fill="#201C26")
            y += 20
    image.save(folder / "swatches.png")


def series(values, floor, circular=False):
    center = circular_center(values) if circular else median(values)
    deltas = [wrap(value - center) if circular else value - center for value in values]
    return {
        "median": center, "minOffset": min(deltas), "maxOffset": max(deltas),
        "tolerance": max(floor, median(map(abs, deltas)) * 1.4826), "referenceCount": len(values),
    }


def summarize(references):
    groups = {}
    for role in ROLES:
        entries = [entry for entry in references if entry["role"] == role]
        if len(entries) < 2:
            groups[role] = {"status": "insufficient", "referenceCount": len(entries), "metrics": {}}
            continue
        profiles = {}
        for metric, (_, floor) in METRICS.items():
            values = [entry["metrics"][metric] for entry in entries if metric in entry["metrics"]]
            if len(values) < 2:
                continue
            profiles[metric] = (
                {key: series([value[key] for value in values], floor) for key, _ in QUANTILES}
                if metric in ("lightness", "chroma")
                else series(values, floor, circular=metric == "shadowHueShift")
            )
        ramp_lengths = [median(len(ramp["colors"]) for ramp in entry["ramps"].values())
                        for entry in entries if entry["ramps"]]
        ramp_spans = [median(ramp["lightnessSpan"] for ramp in entry["ramps"].values())
                      for entry in entries if entry["ramps"]]
        groups[role] = {
            "status": "limited" if len(entries) < 5 else "available",
            "referenceCount": len(entries), "metrics": profiles,
            "typicalRampColors": median(ramp_lengths) if len(ramp_lengths) >= 2 else None,
            "typicalRampSpan": median(ramp_spans) if len(ramp_spans) >= 2 else None,
        }
    return {"version": 1, "colorSpace": "OKLCH", "referenceCount": len(references),
            "roles": groups, "references": references}


def load_role(path, role):
    data = read_json(path)
    if not isinstance(data, dict) or data.get("version") != 1 or data.get("colorSpace") != "OKLCH":
        raise ValueError(f"{path}: expected a version 1 OKLCH reference profile")
    roles = data.get("roles")
    group = roles.get(role) if isinstance(roles, dict) else None
    if not isinstance(group, dict) or group.get("status") not in {"insufficient", "limited", "available"}:
        raise ValueError(f"{path}: missing or invalid {role} profile")
    if not isinstance(group.get("metrics"), dict) or type(group.get("referenceCount")) is not int:
        raise ValueError(f"{path}: invalid {role} metrics")
    for metric, summary in group["metrics"].items():
        if metric not in METRICS or not isinstance(summary, dict):
            raise ValueError(f"{path}: invalid metric {metric}")
        summaries = [summary.get(key) for key, _ in QUANTILES] if metric in ("lightness", "chroma") else [summary]
        for item in summaries:
            fields = ("median", "minOffset", "maxOffset", "tolerance")
            if (not isinstance(item, dict)
                    or any(type(item.get(key)) not in (int, float) or not math.isfinite(item[key]) for key in fields)
                    or item["tolerance"] <= 0 or item["minOffset"] > item["maxOffset"]):
                raise ValueError(f"{path}: invalid summary for {metric}")
    return group


def compare(metrics, group):
    section = {}
    total = active_weight = 0
    for metric, (weight, _) in METRICS.items():
        if metric not in group["metrics"] or metric not in metrics:
            section[metric] = {"status": "insufficient" if metric not in group["metrics"] else "unmeasured"}
            continue
        value, expected = metrics[metric], group["metrics"][metric]
        parts = ([(key, value[key], expected[key]) for key, _ in QUANTILES]
                 if metric in ("lightness", "chroma") else [("value", value, expected)])
        details = {}
        for key, actual, bounds in parts:
            delta = actual - bounds["median"]
            if metric == "shadowHueShift":
                delta = wrap(delta)
            below = bounds["minOffset"] - delta
            above = delta - bounds["maxOffset"]
            excess = max(below, above, 0)
            details[key] = {
                "actual": actual, "referenceMedian": bounds["median"], "offset": delta,
                "direction": "low" if below > 0 else "high" if above > 0 else "in_range",
                "similarity": 1 / (1 + excess / bounds["tolerance"]),
            }
        similarity = sum(item["similarity"] for item in details.values()) / len(details)
        section[metric] = {"status": "measured", "similarity": similarity, "details": details}
        total += weight * similarity
        active_weight += weight
    return {
        "status": group["status"], "referenceCount": group["referenceCount"],
        "score": round(total / active_weight * 100, 1) if active_weight else None,
        "evaluatedWeight": round(active_weight, 2), "metrics": section,
    }


def prompt_guide(profile, role):
    group = profile["roles"][role]
    lines = [f"# {role} color direction", "",
             f"Reference coverage: {group['referenceCount']} assets ({group['status']}).", "",
             "Keep the requested character's base hue and material identities. Match the reference "
             "lightness contrast and chroma, with discrete pixel-art shade steps.",
             "Use the job's approved palette, matching swatch and pose reference as generation inputs.", ""]
    metrics = group["metrics"]
    for key in ("lightness", "chroma"):
        if key in metrics:
            values = ", ".join(f"{part} {data['median']:.3f}" for part, data in metrics[key].items())
            lines.append(f"- OKLCH {key} targets: {values}.")
    if "contrast" in metrics:
        lines.append(f"- Typical visible-pixel lightness span (P90–P10): {metrics['contrast']['median']:.3f}.")
    if group.get("typicalRampColors") is not None:
        lines.append(f"- About {group['typicalRampColors']:g} shades in a comparable material ramp, "
                     f"with a shadow-to-highlight OKLCH L span near {group['typicalRampSpan']:.3f}.")
    if "shadowHueShift" in metrics:
        lines.append(f"- Observed shadow hue offset from the base: {metrics['shadowHueShift']['median']:+.0f}° in OKLCH. "
                     "Use as a tentative cue on similar materials.")
    for reference in profile["references"]:
        if reference["role"] == role:
            for name, ramp in reference["ramps"].items():
                colors = " → ".join(ramp["colors"])
                lines.append(f"- {reference['id']} / {name} shade example: {colors}. Use the contrast as a guide.")
    return "\n".join(lines) + "\n"


def transfer_ramp(samples, base_color):
    source = [oklch(color) for color in samples]
    if len(source) < 3 or any(left[0] >= right[0] for left, right in zip(source, source[1:])):
        raise ValueError("material ramp needs at least three increasing lightness steps")
    index = len(source) // 2
    ref_light, ref_chroma, ref_hue = source[index]
    light, chroma, hue = oklch(base_color)
    if not 0 < light < .999999:
        raise ValueError("choose a base color between black and white")
    scale = min(1, light / (ref_light - source[0][0]),
                (1 - light) / (source[-1][0] - ref_light))
    result = []
    for position, (level_light, level_chroma, level_hue) in enumerate(source):
        delta_hue = wrap(level_hue - ref_hue) if min(level_chroma, ref_chroma, chroma) >= MIN_CHROMA else 0
        delta_chroma = level_chroma - ref_chroma if chroma >= MIN_CHROMA else 0
        result.append(base_color if position == index else to_srgb(
            light + scale * (level_light - ref_light), max(0, chroma + delta_chroma), hue + delta_hue,
        ))
    levels = [oklch(color)[0] for color in result]
    if any(left >= right for left, right in zip(levels, levels[1:])):
        raise ValueError("the requested base cannot keep distinct lightness steps in 8-bit sRGB")
    return result


def adjust(value, observed, expected, strength, maximum):
    low, mid, high = (observed[key] for key, _ in QUANTILES)
    anchors = (low, mid, high)
    targets = [source * (1 - strength) + expected[key]["median"] * strength
               for source, (key, _) in zip(anchors, QUANTILES)]
    # A flat section has no rank information. Its colors share one correction.
    points = [(anchor, median(target for source, target in zip(anchors, targets) if source == anchor))
              for anchor in sorted(set(anchors))]
    result = value + (points[-1][1] - points[-1][0])
    if value <= points[0][0]:
        result = value + (points[0][1] - points[0][0])
    else:
        for (start, left), (end, right) in zip(points, points[1:]):
            if value <= end:
                result = left + (right - left) * (value - start) / (end - start)
                break
    return max(0, min(maximum, result))


def suggest_mapping(counts, metrics, group):
    expected = group["metrics"]
    if not {"lightness", "chroma"} <= expected.keys():
        raise ValueError("recolor needs at least two reference assets for this role")
    original = {color: oklch(color) for color in counts}
    ordered = sorted(original, key=lambda color: original[color][0])
    for strength in (.65, .40, .20, .10, .05):
        mapping = {
            color: to_srgb(
                adjust(light, metrics["lightness"], expected["lightness"], strength, 1),
                adjust(chroma, metrics["chroma"], expected["chroma"], strength, .5) if chroma >= MIN_CHROMA else chroma,
                hue,
            )
            for color, (light, chroma, hue) in original.items()
        }
        if len(set(mapping.values())) != len(mapping):
            continue
        new = {target: oklch(target) for target in mapping.values()}
        if any(
            original[left][0] < original[right][0] and new[mapping[left]][0] >= new[mapping[right]][0]
            for left, right in zip(ordered, ordered[1:])
        ):
            continue
        if any(original[source][1] >= MIN_CHROMA and (
            new[target][1] < MIN_CHROMA or abs(wrap(new[target][2] - original[source][2])) > 5
        ) for source, target in mapping.items()):
            continue
        recolored = measure({mapping[color]: count for color, count in counts.items()})[0]
        measurable_before = {key: value for key, value in metrics.items() if key != "shadowHueShift"}
        if compare(recolored, group)["score"] > compare(measurable_before, group)["score"]:
            return mapping, strength
    return {color: color for color in counts}, 0


def recolor(image, mapping):
    output = Image.new("RGBA", image.size)
    output.putdata([(*mapping.get((r, g, b), (r, g, b)), a) if a else (r, g, b, a)
                    for r, g, b, a in image.getdata()])
    return output


def recolor_preview(before, after):
    scale = min(4, max(1, 512 // max(before.size)))
    width, height = before.width * scale, before.height * scale
    tile = max(100, width)
    preview = Image.new("RGB", (2 * tile + 24, height + 32), "#E7E1DA")
    draw = ImageDraw.Draw(preview)
    for offset, label, image in ((8, "Original", before), (tile + 16, "Suggested", after)):
        draw.text((offset, 5), label, fill="#201C26")
        draw.rectangle((offset, 24, offset + width - 1, height + 23), fill="#514B59")
        enlarged = image.resize((width, height), Image.Resampling.NEAREST)
        preview.paste(enlarged, (offset, 24), enlarged)
    return preview
