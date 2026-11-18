"""Halo 2 gameplay data from the Halo 2 Editing Kit scenario, for the Halo 3 port.

The kit's Tool exports a scenario tag as XML (export-tag-to-xml). From it HaloBridge reads what
makes the map playable in Halo 3: player starting locations (spawns, with team and game types),
netgame flags (CTF flag spawns, teleporters, hills, oddball, bomb ...) and the kill trigger
volumes (falling into Ascension's clouds kills).
"""
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

EXPORT_VERSION = 2  # 2: netgame equipment (vehicles)


def _vec(text):
    return [float(x) for x in (text or '0,0,0').split(',')]


def _enum(text):
    """'12,all games' -> (12, 'all games')."""
    head, _, tail = (text or '0,').partition(',')
    try:
        return int(head), tail.strip()
    except ValueError:
        return 0, (text or '').strip()


def read_xml(xml_path):
    """The kit Tool's XML, tolerating its encoding slips (see clean_xml)."""
    return ET.fromstring(clean_xml(xml_path))


def clean_xml(xml_path):
    """The kit Tool's XML as bytes the XML parser accepts: Tool declares UTF-8 but writes some text
    as Windows-1252 (Relic's script "press the “a” button"; names deep in Gemini's and Midship's
    lightmap and BSP tags) and can write control characters; both made the parser stop."""
    import re
    data = Path(xml_path).read_bytes()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('utf-8', errors='surrogateescape')
        text = re.sub(r'[\udc80-\udcff]+', lambda m: bytes(ord(c) - 0xdc00 for c in m.group()).decode('cp1252', errors='replace'), text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]', ' ', text)
    return text.encode('utf-8')


def parse(xml_path):
    """Halo 2 scenario XML -> dict(starts, flags, triggers, kill_triggers)."""
    root = read_xml(xml_path)
    def block(name):
        b = root.find(f"block[@name='{name}']")
        return [] if b is None else b.findall('element')
    def fields(el):
        return {f.get('name'): (f.text or '').strip() for f in el.findall('field')}
    starts = []
    for el in block('player starting locations'):
        f = fields(el)
        types = [_enum(f.get(f'type {i}'))[1] for i in range(4)]
        starts.append(dict(position=_vec(f.get('position')), facing=float(f.get('facing') or 0),
                           team=_enum(f.get('team designator'))[0], team_name=_enum(f.get('team designator'))[1],
                           game_types=[t for t in types if t and t != 'none']))
    flags = []
    for el in block('netgame flags'):
        f = fields(el)
        kind, kind_name = _enum(f.get('type'))
        team, team_name = _enum(f.get('team designator'))
        flags.append(dict(position=_vec(f.get('position')), facing=float(f.get('facing') or 0), type=kind,
                          type_name=kind_name, team=team, team_name=team_name,
                          identifier=int(f.get('identifier') or 0)))
    triggers = []
    for el in block('trigger volumes'):
        f = fields(el)
        triggers.append(dict(name=f.get('name', ''), forward=_vec(f.get('forward')), up=_vec(f.get('up')),
                             position=_vec(f.get('position')), extents=_vec(f.get('extents'))))
    kills = []
    for el in block('scenario kill triggers'):
        index = el.find('block_index')
        if index is not None and int(index.get('index', -1)) >= 0:
            kills.append(int(index.get('index')))
    equipment = []
    for el in block('netgame equipment'):
        f = fields(el)
        ref = el.find("tag_reference")
        equipment.append(dict(position=_vec(f.get('position')), orientation=_vec(f.get('orientation')),
                              classification=_enum(f.get('classification'))[1],
                              collection=(ref.text or '').strip() if ref is not None else ''))
    return dict(starts=starts, flags=flags, triggers=triggers, kill_triggers=kills, equipment=equipment)


def vehicles(data, kit_tags, scenario):
    """Halo 2 multiplayer vehicles (netgame equipment of vehicle collections) as Halo 3 vehicle
    placements: the Halo 3 vehicle of the same name (objects\\vehicles\\<name>\\<name>.vehicle) when
    the Halo 3 Editing Kit has it. Ids are stable per scenario and slot, so preparing again updates
    them instead of adding copies. Weapons and grenades are left for the level designer."""
    result = []
    for index, item in enumerate(data.get('equipment', [])):
        collection = item.get('collection', '').replace('/', '\\').lower()
        if '\\single_vehicles\\' not in collection and item.get('classification') != 'vehicle':
            continue
        name = collection.rsplit('\\', 1)[-1]
        tag = 'objects\\vehicles\\' + name + '\\' + name
        if not (Path(kit_tags) / (tag + '.vehicle')).is_file():
            continue
        identity = 'hb_' + hashlib.sha256((scenario.lower() + '|vehicle|' + str(index)).encode()).hexdigest()[:24]
        result.append(dict(id=identity, tag=tag, position=item['position'], rotation=list(item['orientation'][:3]), scale=1.0))
    return result


def export(h2ek, scenario, cache, run):
    """Export (cached) and parse a Halo 2 kit scenario. run(args, cwd) runs the kit's Tool."""
    from .catalog import fingerprint, read_json, write_json
    tag = Path(h2ek) / 'tags' / (scenario + '.scenario')
    if not tag.is_file():
        raise RuntimeError('Halo 2 scenario tag not found: ' + str(tag))
    signature = dict(version=EXPORT_VERSION, scenario=fingerprint(tag))
    folder = Path(cache) / 'h2_scenarios' / hashlib.sha256(json.dumps(signature, default=str).encode()).hexdigest()[:24]
    data = folder / 'gameplay.json'
    if read_json(folder / 'stamp.json') != signature or not data.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        xml = folder / 'scenario.xml'
        run([Path(h2ek) / 'tool.exe', 'export-tag-to-xml', tag, xml], h2ek)
        if not xml.is_file():
            raise RuntimeError('The Halo 2 Editing Kit did not export ' + scenario)
        write_json(data, parse(xml))
        xml.unlink()
        write_json(folder / 'stamp.json', signature)
    return read_json(data)


def kill_volumes(data):
    """The kill trigger volumes as boxes: dict(name, center, forward, up, extents) in world units.
    Halo 2 places a trigger volume by its corner (position) and extends it along forward, left
    (up x forward) and up by the extents."""
    result = []
    for index in data.get('kill_triggers', []):
        if not 0 <= index < len(data.get('triggers', [])):
            continue
        t = data['triggers'][index]
        f, u = t['forward'], t['up']
        left = [u[1] * f[2] - u[2] * f[1], u[2] * f[0] - u[0] * f[2], u[0] * f[1] - u[1] * f[0]]
        e = t['extents']
        center = [t['position'][i] + (f[i] * e[0] + left[i] * e[1] + u[i] * e[2]) / 2 for i in range(3)]
        result.append(dict(name=t['name'], center=center, position=t['position'], forward=f, up=u, extents=e))
    return result


# Halo 2 netgame flag type -> Halo 3 multiplayer object (crates in the Halo 3 Editing Kit), with the
# boundary Halo 3 gives it: (tag, shape, radius). Shapes: 0 none, 1 sphere, 2 cylinder, 3 box.
NETGAME_OBJECTS = {
    0: (r'objects\multi\ctf\ctf_flag_spawn_point', 0, 0.0),        # CTF flag spawn
    1: (r'objects\multi\ctf\ctf_flag_return_area', 2, 1.5),        # CTF flag return
    2: (r'objects\multi\assault\assault_bomb_spawn_point', 0, 0.0),  # Assault bomb spawn
    3: (r'objects\multi\assault\assault_bomb_goal_area', 2, 1.5),  # Assault bomb return
    4: (r'objects\multi\oddball\oddball_ball_spawn_point', 0, 0.0),  # Oddball spawn
    7: (r'objects\multi\teleporter_sender\teleporter_sender', 0, 0.0),      # Teleporter (src)
    8: (r'objects\multi\teleporter_reciever\teleporter_reciever', 0, 0.0),  # Teleporter (dest)
    10: (r'objects\multi\territories\territory_static', 2, 3.0),   # Territories flag
}
TELEPORTER_TYPES = (7, 8)
KING_HILL_TYPES = range(11, 19)  # King Hill 0-7: points around each hill's edge
HILL_TAG = r'objects\multi\koth\koth_hill_static'


def netgame_objects(data):
    """Halo 2 netgame flags as Halo 3 multiplayer objects: dict(tag, position, yaw, team, channel,
    shape, radius, height). King of the Hill hills (points around each hill) become one hill each,
    a cylinder through its points. Unknown flag types (race checkpoints, headhunter bins) are left out."""
    result, hills = [], {}
    for flag in data.get('flags', []):
        if flag['type'] in KING_HILL_TYPES:
            hills.setdefault(flag['type'], []).append(flag['position'])
            continue
        if flag['type'] not in NETGAME_OBJECTS:
            continue
        tag, shape, radius = NETGAME_OBJECTS[flag['type']]
        # Teleporters: the level shows its own (Halo 2 teleporter scenery, Halo CE pads), so the Halo 3
        # crate is a bare copy that only teleports (no model or glow on top of the original).
        result.append(dict(tag=tag, position=flag['position'], yaw=flag['facing'], team=min(max(flag['team'], 0), 8),
                           channel=max(flag['identifier'], 0), shape=shape, radius=radius, height=2.0,
                           bare=flag['type'] in TELEPORTER_TYPES))
    for kind in sorted(hills):
        points = hills[kind]
        center = [sum(p[i] for p in points) / len(points) for i in range(3)]
        radius = max([math.hypot(p[0] - center[0], p[1] - center[1]) for p in points] + [1.0])
        zs = [p[2] for p in points]
        result.append(dict(tag=HILL_TAG, position=[center[0], center[1], min(zs)], yaw=0.0, team=8, channel=kind - 11,
                           shape=2, radius=radius, height=max(zs) - min(zs) + 2.0))
    return result


def facing_degrees(start):
    """Halo 2 stores a start's facing in degrees already; normalized to -180..180."""
    return (start['facing'] + 180.0) % 360.0 - 180.0
