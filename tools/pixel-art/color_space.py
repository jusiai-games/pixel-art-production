import math


def multiply(rows, values):
    return tuple(sum(coefficient * value for coefficient, value in zip(row, values)) for row in rows)


def linear(channel):
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def oklch(rgb):
    # Björn Ottosson's linear sRGB <-> OKLab matrices.
    lms = multiply((
        (.4122214708, .5363325363, .0514459929),
        (.2119034982, .6806995451, .1073969566),
        (.0883024619, .2817188376, .6299787005),
    ), tuple(map(linear, rgb)))
    light, a, b = multiply((
        (.2104542553, .7936177850, -.0040720468),
        (1.9779984951, -2.4285922050, .4505937099),
        (.0259040371, .7827717662, -.8086757660),
    ), tuple(value ** (1 / 3) for value in lms))
    return light, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def linear_rgb(light, chroma, hue):
    angle = math.radians(hue)
    lab = light, chroma * math.cos(angle), chroma * math.sin(angle)
    roots = multiply((
        (1, .3963377774, .2158037573),
        (1, -.1055613458, -.0638541728),
        (1, -.0894841775, -1.2914855480),
    ), lab)
    return multiply((
        (4.0767416621, -3.3077115913, .2309699292),
        (-1.2684380046, 2.6097574011, -.3413193965),
        (-.0041960863, -.7034186147, 1.7076147010),
    ), tuple(value ** 3 for value in roots))


def to_srgb(light, chroma, hue):
    def in_gamut(values):
        return all(-1e-7 <= value <= 1 + 1e-7 for value in values)

    values = linear_rgb(light, chroma, hue)
    if not in_gamut(values):
        low, high = 0, chroma
        for _ in range(20):
            middle = (low + high) / 2
            if in_gamut(linear_rgb(light, middle, hue)):
                low = middle
            else:
                high = middle
        values = linear_rgb(light, low, hue)
    channels = [max(0, min(1, value)) for value in values]
    return tuple(round(255 * (12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055))
                 for value in channels)
