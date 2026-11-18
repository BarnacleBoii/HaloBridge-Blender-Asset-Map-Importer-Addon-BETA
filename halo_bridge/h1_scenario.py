"""Halo: CE gameplay for the Halo 3 port: player starting locations and netgame flags, read from
the map itself by the extractor's h1_gameplay operation, in the same form as Halo 2's (h2_scenario)
so the same Halo 3 writer places them.
"""
import json
from pathlib import Path

# Halo CE netgame flag type -> Halo 2 netgame flag type (h2_scenario.NETGAME_OBJECTS / KING_HILL_TYPES).
# CE: 0 ctf flag, 1 ctf vehicle, 2 oddball ball spawn, 3 race track, 4 race vehicle, 5 vegas bank,
# 6 teleport from, 7 teleport to, 8 hill flag. CE pairs teleporters, and numbers hills, by the flag's
# team index.
CE_TO_H2 = {0: 0, 2: 4, 6: 7, 7: 8}
CE_HILL = 8


def to_h2_format(data):
    """The extractor's CE gameplay JSON -> h2_scenario's dict(starts, flags, triggers, kill_triggers, equipment)."""
    starts = [dict(position=list(s['position']), facing=float(s['facing']), team=int(s['team']), team_name='', game_types=[])
              for s in data.get('starts', [])]
    flags = []
    for f in data.get('flags', []):
        kind, team = int(f['type']), int(f['team'])
        if kind in CE_TO_H2:
            teleporter = kind in (6, 7)
            flags.append(dict(position=list(f['position']), facing=float(f['facing']), type=CE_TO_H2[kind], type_name='',
                              team=8 if teleporter else team, team_name='', identifier=team if teleporter else 0))
        elif kind == CE_HILL:
            flags.append(dict(position=list(f['position']), facing=float(f['facing']), type=11 + min(max(team, 0), 7),
                              type_name='', team=8, team_name='', identifier=0))
    return dict(starts=starts, flags=flags, triggers=[], kill_triggers=[], equipment=[])


CE_VEHICLES = ('warthog', 'ghost', 'scorpion', 'banshee')  # Halo 3 has each; CE's rocket warthog becomes a warthog


def vehicles(data, kit_tags, map_path):
    """Halo CE vehicle placements (vehicles\\warthog\\mp_warthog ...) as Halo 3 vehicle placements of
    the same family, with ids stable per map and slot."""
    import hashlib
    result = []
    for index, v in enumerate(data.get('vehicles', [])):
        name = str(v.get('tag', '')).replace('/', '\\').lower().rsplit('\\', 1)[-1]
        family = next((f for f in CE_VEHICLES if f in name), None)
        tag = family and 'objects\\vehicles\\' + family + '\\' + family
        if not tag or not (Path(kit_tags) / (tag + '.vehicle')).is_file():
            continue
        identity = 'hb_' + hashlib.sha256((str(map_path).lower() + '|vehicle|' + str(index)).encode()).hexdigest()[:24]
        result.append(dict(id=identity, tag=tag, position=list(v['position']), rotation=list(v['rotation'][:3]), scale=1.0))
    return result


def load(map_path, folder, helper, cancel=None):
    """Read a Halo CE map's gameplay (extractor h1_gameplay) and convert it; None if unreadable."""
    output = Path(folder) / 'h1_gameplay.json'
    helper('extractor', dict(operation='h1_gameplay', map=str(map_path), output=str(output), game='halo1'), folder, cancel)
    if not output.is_file():
        return None
    raw = json.loads(output.read_text(encoding='utf-8'))
    data = to_h2_format(raw)
    data['ce_vehicles'] = raw.get('vehicles', [])
    return data
