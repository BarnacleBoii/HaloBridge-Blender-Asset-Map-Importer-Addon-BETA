"""Halo: CE's original baked lighting, copied into a Halo 3 level's lightmap.

The same copy as Halo 2's (h2_lightmaps, h2_lightmap_worker): each Halo 3 lightmap pixel takes the
light of the Halo CE surface at the same spot. Halo CE keeps its lighting in the map itself, so no
editing kit is needed: the extractor's h1_lightmaps operation reads every BSP's lightmap blocks
(world positions, normals, lightmap texcoords, incident light directions, triangles) and writes the
lightmap pages as PNG. This module turns that into the worker's per-BSP .npz layout.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

EXPORT_VERSION = 1


def to_arrays(bsp):
    """One BSP of the extractor's lightmaps.json -> the worker's arrays (c<i>_pos/_nrm/_uv/_dir/_tri/_bitmap)."""
    arrays = {}
    for i, c in enumerate(bsp.get('clusters', [])):
        key = 'c' + str(i)
        arrays[key + '_pos'] = np.array(c['pos'], np.float32).reshape(-1, 3)
        arrays[key + '_nrm'] = np.array(c['nrm'], np.float32).reshape(-1, 3)
        arrays[key + '_uv'] = np.array(c['uv'], np.float32).reshape(-1, 2)
        arrays[key + '_dir'] = np.array(c['dir'], np.float32).reshape(-1, 3)
        arrays[key + '_tri'] = np.array(c['tri'], np.int32).reshape(-1, 3)
        arrays[key + '_bitmap'] = np.array([int(c['page']), 0], np.int32)
    return arrays


def export(map_path, cache, helper, cancel=None):
    """Export (cached) a Halo CE map's lightmaps: [{npz, pages, bsp}] per BSP.
    helper(kind, job, folder, cancel) runs the extractor (jobs.helper)."""
    from .catalog import fingerprint, read_json, write_json
    signature = dict(version=EXPORT_VERSION, map=fingerprint(Path(map_path)))
    folder = Path(cache) / 'h1_lightmaps' / hashlib.sha256(json.dumps(signature, default=str).encode()).hexdigest()[:24]
    if read_json(folder / 'stamp.json') != signature:
        folder.mkdir(parents=True, exist_ok=True)
        helper('extractor', dict(operation='h1_lightmaps', map=str(map_path), output=str(folder), game='halo1'), folder, cancel)
        data = json.loads((folder / 'lightmaps.json').read_text(encoding='utf-8'))
        for bsp in data.get('bsps', []):
            np.savez_compressed(folder / ('bsp' + str(bsp['bsp']) + '.npz'), **to_arrays(bsp))
        (folder / 'bsps.json').write_text(json.dumps([dict(bsp=b['bsp'], tag=b['tag'], pages=b['page_folder']) for b in data.get('bsps', [])]), encoding='utf-8')
        (folder / 'lightmaps.json').unlink()
        write_json(folder / 'stamp.json', signature)
    bsps = json.loads((folder / 'bsps.json').read_text(encoding='utf-8'))
    return [dict(npz=str(folder / ('bsp' + str(b['bsp']) + '.npz')), pages=str(folder / b['pages']), bsp=b['tag']) for b in bsps]


def source(objects):
    """The Halo CE .map imported Halo CE map objects came from, or None."""
    from .catalog import read_json
    for obj in objects:
        manifest = obj.get('hb_map_manifest')
        if not manifest or not Path(manifest).is_file():
            continue
        # The scene stamp lists every map in the folder; the map is the one named like the
        # scenario (levels\test\bloodgulch\bloodgulch -> bloodgulch.map).
        name = str((read_json(manifest, {}) or {}).get('scenario', '')).replace('/', '\\').rsplit('\\', 1)[-1].lower()
        for res in (read_json(Path(manifest).parent / 'stamp.json', {}) or {}).get('resources', []):
            path = Path(str(res[0])) if res else None
            if path and path.suffix.lower() == '.map' and path.stem.lower() == name and path.is_file():
                return str(path)
    return None
