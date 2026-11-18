"""Halo 3 sky lights (the lightmap's sun and sky) from a Halo 2 sky's lighting.

A Halo 3 sky render model lights the level through its "sky lights" block: Bungie's skies
have 200, one sun (a tiny solid angle with a very high intensity) and 199 patches of sky,
each 4*pi/199 steradians, spread over the dome. A sky converted from Halo 2 has none, so
its level could only be lit with another level's sky.

Halo 2 keeps the same information in its sky tag: lights with a direction, color, power
and disk size, and an outdoor ambient color. Their direction and color are kept exactly.
Halo 2's light power and ambient have no Halo 3 unit, so their brightness is scaled to
Bungie's Halo 3 multiplayer skies: those give the ground about 3.4 to 5.8 units of light
from the sun and 2.8 to 5.2 from the sky (Chill, Construct, Cyberdyne, Deadlock), with the
sun high (Deadlock 55 degrees). Halo 2 skies often have a low sun (Coagulation 28 degrees),
which lights flat ground at less than half strength, and Halo 2 shows its shade much lighter
than Halo 3 does; so the defaults sit above Bungie's: a stronger sun and a brighter sky fill
for the shade. The sun and sky strengths (1 = these defaults) are adjustable per level.
"""
import math

PATCH_ANGLE = 4 * math.pi / 199  # 0.06314758 sr, as in Bungie's skies
FALLBACK_AMBIENT = 0.12  # sky fill (per channel, like Halo 2's outdoor ambient) for a sky that has none
MIN_SUN_ANGLE = 4.7e-5  # Bungie's smallest sun disk (Deadlock); sharper ones are widened to it
SUN_LIGHT_PER_POWER = 25.0  # Coagulation's power 0.3 -> 7.5 facing the sun, 3.5 on flat ground
SKY_LIGHT = 7.0  # outdoor ambient (0..1) -> light from the whole sky on flat ground (the shade)
MAX_LIGHTS = 200

DIRECT = 4  # Halo 2 radiosity flag: lights the lightmap directly


def dome(count):
    """count directions spread evenly over the upper hemisphere (golden-angle spiral)."""
    result = []
    for i in range(count):
        z = 1 - (i + .5) / count
        r = math.sqrt(max(0.0, 1 - z * z))
        a = i * math.pi * (3 - math.sqrt(5))
        result.append((r * math.cos(a), r * math.sin(a), z))
    return result


def _unit(v):
    length = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / length for x in v]


def h2_sky_lights(lighting, sun=1.0, sky=1.0):
    """[{direction, intensity, solid_angle}] for a Halo 3 sky render model, or [] when the
    Halo 2 sky has no light to give. sun and sky scale the sun and the sky fill (shade)."""
    if not lighting:
        return []
    sun = max(0.0, float(sun)); sky = max(0.0, float(sky))
    suns = []
    for light in lighting.get('lights', []):
        power = float(light.get('power', 0))
        if not int(light.get('flags', 0)) & DIRECT or power <= 0:
            continue
        diameter = float(light.get('diameter', 0))
        angle = max(MIN_SUN_ANGLE, math.pi * (diameter / 2) ** 2)
        strength = sun * SUN_LIGHT_PER_POWER * power / angle
        if strength <= 0:
            continue
        suns.append(dict(direction=_unit(light['direction']), intensity=[c * strength for c in light.get('color', (1, 1, 1))[:3]],
                         solid_angle=angle))
    suns = suns[:MAX_LIGHTS - 1]
    ambient = [sky * max(0.0, float(c)) for c in (lighting.get('outdoor_ambient') or (0, 0, 0))[:3]]
    if suns and not any(ambient) and sky > 0:
        # A sun without outdoor ambient (Beaver Creek): Tool asserts on a sky with only its sun
        # ("-1 is not a valid sky_lights_block index"), so the shade gets a dim fill tinted like the sun.
        tint = max(sum(suns[0]['intensity']), 1e-9)
        ambient = [sky * FALLBACK_AMBIENT * 3 * c / tint for c in suns[0]['intensity']]
    patches = []
    if any(ambient):
        directions = dome(MAX_LIGHTS - len(suns))
        # Radiance so that the patches give flat ground SKY_LIGHT x ambient.
        flat = sum(PATCH_ANGLE * d[2] for d in directions)
        patches = [dict(direction=list(d), intensity=[SKY_LIGHT * c / flat for c in ambient], solid_angle=PATCH_ANGLE) for d in directions]
    if not suns and not patches:
        return []
    # The sun goes last, as in every Bungie sky (index 199): Tool and H3LM take the last sky
    # light as the sun; first, it was baked as one more patch of sky (H3LM: "+0 sun").
    return patches + suns
