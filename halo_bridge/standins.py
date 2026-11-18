"""Halo 3 shaders and materials for converted Halo 2 surfaces.

Some Halo 2 shader templates draw effects that no texture holds: animated plasma (teleporter
fields, grav lifts: transparent\\plasma_alpha), glass lit by a reflection map
(transparent\\*_alpha_env*) and water (water\\*). Converted to a plain textured shader they come out
solid white, flat grey or opaque. They use a Halo 3 shader with the same role from the Editing
Kit instead (copied into the level like any other Halo 3 shader).

Halo 2 shaders also name a global material (tough_terrain_dirt, hard_metal_thick_for ...) that
gives a surface its footstep sounds and impact effects; Halo 3 has the same materials, so the
converted shader keeps it.
"""
import re
from pathlib import Path

# (id, label, Halo 3 shader). '' keeps HaloBridge's own conversion.
WATER_SHADERS = (
    ('POOL', 'Pool (Reactor)', r'levels\multi\s3d_reactor\shaders\re_water_pool.shader_water'),
    ('POND', 'Pond (The Covenant)', r'levels\solo\100_citadel\shaders\water\cit_water_pond.shader_water'),
    ('RIVER', 'River (Sierra 117)', r'levels\solo\010_jungle\shaders\water\water_river.shader_water'),
    ('OCEAN', 'Ocean (Zanzibar)', r'levels\multi\zanzibar\shaders\zanzibar_water_awesome.shader_water'),
    ('ROUGH', 'Rough (Rat\'s Nest)', r'levels\multi\riverworld\shaders\riverworld_water_rough.shader_water'),
    ('CONVERTED', 'Converted (dark, still)', ''),
)
DEFAULT_WATER = 'POOL'
PLASMA_SHADER = r'levels\dlc\descent\shaders\d_descent_gravlifts_green.shader'  # animated green energy
GLASS_SHADER = r'levels\multi\s3d_lockout\shaders\lct_glass_01.shader'  # clear alpha-blended glass (Construct's glass_floor2 drew solid pink)


def water_shader(choice):
    return next((path for key, _, path in WATER_SHADERS if key == choice), WATER_SHADERS[0][2])


H1_CLASSES = {'spla': 'plasma', 'sgla': 'glass', 'swat': 'water'}  # Halo CE shader classes with a Halo 3 stand-in


def standin(template, config, shader_class=''):
    """The Halo 3 shader (tag path with extension) for a Halo 2 shader template or a Halo CE shader
    class (spla plasma, sgla glass, swat water), or None to convert it."""
    t = str(template or '').lower().replace('/', '\\')
    role = H1_CLASSES.get(str(shader_class or '').lower())
    if role == 'water':
        t = r'shaders\shader_templates\water\h1_water'
    elif role == 'plasma':
        t = r'shaders\shader_templates\transparent\plasma_h1'
    elif role == 'glass':
        t = r'shaders\shader_templates\transparent\h1_alpha_env_glass'
    if not t:
        return None
    path = None
    if '\\water\\' in t:
        path = water_shader(config.get('water_shader', DEFAULT_WATER))
    elif config.get('effect_standins', True) and '\\transparent\\' in t:
        name = t.rsplit('\\', 1)[-1]
        if name.startswith('plasma'):
            path = PLASMA_SHADER
        elif '_alpha_env' in name and 'illum' not in name:
            path = GLASS_SHADER
    if not path:
        return None
    kit = config.get('kit')
    return path if not kit or (Path(kit) / 'tags' / path).is_file() else None


_h2_names = {}


def h2_material_name(h2ek, shader):
    """The global material a Halo 2 Editing Kit shader names ('' when none or unreadable). In the tag
    file the name is the first string stored after the template path, just before the runtime
    properties block's 'tbfd' header."""
    path = Path(h2ek) / 'tags' / (str(shader).replace('/', '\\') + '.shader')
    key = str(path).lower()
    if key not in _h2_names:
        name = ''
        try:
            match = re.search(rb'(?<![\\a-z0-9_])([a-z][a-z0-9_]{2,47})dfbt', path.read_bytes())
            name = match.group(1).decode() if match else ''
        except OSError:
            pass
        _h2_names[key] = name
    return _h2_names[key]


_h3_names = {}


def h3_material_names(kit):
    """Global material names in the Halo 3 Editing Kit's globals tag."""
    key = str(kit).lower()
    if key not in _h3_names:
        try:
            data = (Path(kit) / 'tags' / 'globals' / 'globals.globals').read_bytes()
            _h3_names[key] = {m.decode() for m in re.findall(rb'([a-z][a-z0-9_]{2,47})isgt', data)}
        except OSError:
            _h3_names[key] = set()
    return _h3_names[key]


def h3_material(name, names):
    """Halo 2's material name as a Halo 3 one: the same name, or its nearest parent
    (hard_metal_thick_for -> hard_metal_thick -> hard_metal), or '' when Halo 3 has none."""
    parts = str(name or '').split('_')
    while parts:
        candidate = '_'.join(parts)
        if candidate in names:
            return candidate
        parts.pop()
    return ''
