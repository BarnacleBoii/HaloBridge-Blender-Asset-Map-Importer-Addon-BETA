"""Halo 2's original baked lighting, copied into a Halo 3 level's lightmap.

Halo 2 keeps a level's lighting in lightmap pages, one per cluster, with each vertex's lightmap
UV and the main direction light arrives from. The Halo 2 Editing Kit's Tool exports them
(export-tag-to-xml, export-bitmap-tga). Halo 3's Tool, after its test-lighting steps up to
faux_farm_finish, holds the level's lighting as a master bitmap of 9 layers: the spherical-harmonic
(SH) coefficients of the light at each lightmap pixel, in the standard order with the
Condon-Shortley signs (layer 0 the constant term, 1-3 y z x, 4-8 the quadratic terms). Its
faux-build-linear-textures..., faux-compress... and faux-farm-compression-merge steps build the
game's textures from that master, so writing Halo 2's light into it is enough.

Each Halo 3 lightmap pixel is placed on the Halo 2 surface at the same spot (the geometry is the
same, so the nearest Halo 2 triangle), and Halo 2's colour there becomes the light on the surface:
60% from a direction halfway between Halo 2's light direction and the surface normal, 40% even
light, so shade and bump detail never turn black. Only per-pixel Halo 3 meshes have lightmap
pixels; Halo 3 compiles only the level structure that way, so Halo 2's terrain clusters are
compiled as the structure (see geometry_export).
"""
import hashlib
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

# Halo 2 lightmap value (as stored, 0..1) -> light on the surface in Halo 3's units. Halo 2's
# sunlit ground (about 0.66) lands near the sunlight on Bungie's Halo 3 multiplayer maps (about 8).
BRIGHTNESS = 12.0
DIRECTIONAL = 0.6
SEARCH_DISTANCE = 0.5  # world units: a pixel this close to a Halo 2 surface takes that surface's light
OBJECT_SEARCH_DISTANCE = 10.0  # farther pixels (objects in the level) take the nearest Halo 2 light within this
EXPORT_VERSION = 3  # 2: instance definitions, their lightmap pages and the BSP's instance placements; 3: per-vertex light

SH_BANDS = np.array([math.pi] + [2 * math.pi / 3] * 3 + [math.pi / 4] * 5)


def sh(direction):
    """Real SH basis (9 terms) for a unit direction, in Halo 3's order and signs."""
    x, y, z = direction
    return np.array([.282095, -.488603 * y, .488603 * z, -.488603 * x, 1.092548 * x * y, -1.092548 * y * z,
                     .315392 * (3 * z * z - 1), -1.092548 * x * z, .546274 * (x * x - y * y)])


def encode(color, incident, normal, brightness=BRIGHTNESS, directional=DIRECTIONAL):
    """9 x RGB SH coefficients that light a surface with this normal by brightness x color
    (directional: the share of it arriving from Halo 2's light direction, the rest even)."""
    target = brightness * np.clip(np.asarray(color, dtype=np.float64), 0, None)
    n = np.asarray(normal, dtype=np.float64); n = n / (np.linalg.norm(n) or 1)
    d = np.asarray(incident, dtype=np.float64)
    d = d / np.linalg.norm(d) if np.linalg.norm(d) > 1e-6 else n
    half = d + n; half = half / (np.linalg.norm(half) or 1)
    ydir = sh(half); response = max(float((SH_BANDS * ydir * sh(n)).sum()), .3)
    even = np.zeros(9); even[0] = 1 / (math.pi * .282095)  # one unit of light on any normal
    return np.outer(ydir, directional * target / response) + np.outer(even, (1 - directional) * target)


MIN_VERTEX_DIRECTIONAL = 0.1  # Halo 3 takes a vertex's light direction from its linear terms; never zero
GRAZING = 0.5  # the sharp light never meets a vertex's normal at less than this cosine


def decompress_positions(positions, bounds):
    """Halo 3 definition meshes store positions as 0..1 inside the compression bounds
    (x min, x max, y min, y max, z min, z max); None leaves them as they are."""
    if bounds is None or len(bounds) != 6:
        return np.asarray(positions, dtype=np.float64)
    b = np.asarray(bounds, dtype=np.float64)
    lo, hi = b[[0, 2, 4]], b[[1, 3, 5]]
    return lo + np.asarray(positions, dtype=np.float64) * (hi - lo)


def encode_vertex(color, incident, normal, brightness=BRIGHTNESS, directional=DIRECTIONAL):
    """Halo 3 per-vertex light (an instance lit per vertex) that lights this vertex's normal by
    brightness x color: 15 values, the dominant light intensity (RGB) and the red, green and blue
    linear SH terms (c0, c1, c2, c3 each). Halo 3's shader (static_per_vertex in
    entry_points_fx, ravi_order_2_with_dominant_light) takes the dominant light's direction from
    the luminance of (-c3, -c1, c2), removes that light's own share from the terms and adds it back
    as a sharp light: diffuse = (0.886227 (c0 - 0.282095 I) - 1.023328 n.(V + 0.488603 D I)) / pi
    + 0.281 I max(D.n, 0), with V = (c3, c1, -c2). Terms V = -0.488603 D I leave exactly an even
    light (c0) plus the directional share from D."""
    target = brightness * np.clip(np.asarray(color, dtype=np.float64), 0, None)
    n = np.asarray(normal, dtype=np.float64); n = n / (np.linalg.norm(n) or 1)
    d = np.asarray(incident, dtype=np.float64)
    d = d / np.linalg.norm(d) if np.linalg.norm(d) > 1e-6 else n
    # Light skimming the surface (or from behind it) is turned toward the normal until it meets it
    # at GRAZING, so the vertex still gets its whole value and the sharp light stays bounded
    # (on a bump map normal, at most 1/GRAZING times the vertex's own light).
    a = float(d @ n)
    if a < GRAZING:
        t = -a + GRAZING * math.sqrt(max(1 - a * a, 0.0)) / math.sqrt(1 - GRAZING * GRAZING)
        d = d + t * n; d = d / (np.linalg.norm(d) or 1)
        if np.linalg.norm(d) < .5:
            d = n
    share = max(float(directional), MIN_VERTEX_DIRECTIONAL)
    intensity = share * target / (0.281 * max(float(d @ n), GRAZING))
    c0 = (1 - share) * target * math.pi / 0.886227 + 0.2820948 * intensity
    k = 0.4886025 * intensity
    terms = [np.array([c0[c], -k[c] * d[1], k[c] * d[2], -k[c] * d[0]]) for c in range(3)]
    return np.concatenate([intensity, *terms]).astype(np.float32)


def vertex_light(values, normal):
    """The diffuse light Halo 3 gives a vertex with this normal from encode_vertex's values (its
    shader's formula; for tests)."""
    v = np.asarray(values, dtype=np.float64); n = np.asarray(normal, dtype=np.float64); n = n / (np.linalg.norm(n) or 1)
    intensity, terms = v[:3], v[3:].reshape(3, 4)
    lum = np.array([0.212656, 0.715158, 0.0721856])
    d = (lum[:, None] * terms[:, [3, 1, 2]]).sum(0) * np.array([-1, -1, 1]); d = d / (np.linalg.norm(d) or 1)
    out = np.zeros(3)
    for c in range(3):
        c0, c1, c2, c3 = terms[c]
        lin = np.array([c3, c1, -c2]) + 0.4886025 * d * intensity[c]
        out[c] = (0.886227 * (c0 - 0.2820948 * intensity[c]) - 2 * 0.511664 * (n @ lin)) / math.pi + max(d @ n, 0) * intensity[c] * 0.281
    return out


def read_mesh_vertices(csv_path):
    """Every mesh's raw vertices from the tag helper's lightmap_mesh CSV: {mesh: N x 10 array}
    (position, normal, texcoord, lightmap texcoord), with or without lightmap UVs."""
    verts = {}
    for line in open(csv_path, encoding='utf-8'):
        if line.startswith('#indices'):
            continue
        f = line.rstrip('\n').split(',')
        if f[0] == 'path':
            continue
        verts.setdefault(int(f[1]), []).append([float(x) for x in f[3:]])
    return {m: np.array(rows) for m, rows in verts.items()}


EMPTY = 1.5 / 255  # a texel or vertex colour summing below this holds no light (Halo 2 left it unbaked)


def fill_empty(img, passes=512):
    """A Halo 2 lightmap page (H x W x 3) with its empty texels filled from the nearest baked ones.
    Halo 2 leaves texels it did not bake black, inside charts too (10-17% of some Ascension rock
    pages); copied as light they made black smudges fading into a tint where they blend with baked
    texels. Grows the baked area one texel per pass, averaging baked neighbours."""
    out = np.array(img, dtype=np.float32, copy=True)
    valid = out.sum(axis=2) >= EMPTY
    if valid.all() or not valid.any():
        return out
    h, w = valid.shape
    for _ in range(passes):
        acc = np.zeros_like(out); count = np.zeros((h, w), np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                ys, yd = (slice(max(dy, 0), h + min(dy, 0)), slice(max(-dy, 0), h + min(-dy, 0)))
                xs, xd = (slice(max(dx, 0), w + min(dx, 0)), slice(max(-dx, 0), w + min(-dx, 0)))
                v = valid[ys, xs]
                acc[yd, xd] += out[ys, xs] * v[..., None]; count[yd, xd] += v
        grow = ~valid & (count > 0)
        if not grow.any():
            break
        out[grow] = acc[grow] / count[grow][:, None]; valid |= grow
    return out


def fill_empty_vertices(colors, tris, passes=64):
    """Per-vertex Halo 2 light with unlit (zero) vertices filled from lit neighbours along the
    triangles (the same unbaked-black problem as fill_empty), else from the piece's average."""
    out = np.array(colors, dtype=np.float32, copy=True)
    valid = out.sum(axis=1) >= EMPTY
    if valid.all() or not valid.any():
        return out
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    edges = np.concatenate([edges, edges[:, ::-1]])
    for _ in range(passes):
        acc = np.zeros_like(out); count = np.zeros(len(out), np.float32)
        src = valid[edges[:, 0]]
        np.add.at(acc, edges[src, 1], out[edges[src, 0]]); np.add.at(count, edges[src, 1], 1)
        grow = ~valid & (count > 0)
        if not grow.any():
            break
        out[grow] = acc[grow] / count[grow][:, None]; valid |= grow
    out[~valid] = out[valid].mean(axis=0)
    return out


# ---- Halo 2 kit export

def lightmap_tags(h2ek, scenario):
    """[(lightmap tag, its bitmap tag)] of a Halo 2 kit scenario (one per BSP), tag paths without extension."""
    folder = Path(h2ek) / 'tags' / Path(scenario.replace('\\', '/')).parent
    result = []
    for path in sorted(folder.glob('*.scenario_structure_lightmap')):
        stem = path.with_suffix('')
        bitmap = stem.with_name(stem.name + '_bitmaps')
        if bitmap.with_suffix('.bitmap').is_file():
            rel = lambda p: str(p.relative_to(Path(h2ek) / 'tags')).replace('/', '\\')
            result.append((rel(stem), rel(bitmap)))
    return result


def export(h2ek, scenario, cache, progress=lambda m: None, cancel=None):
    """Export (cached) and parse a Halo 2 scenario's lightmaps; returns [{npz, pages}] per BSP."""
    from .catalog import fingerprint, read_json, write_json
    h2ek = Path(h2ek)
    tool = h2ek / 'tool.exe'
    if not tool.is_file():
        raise RuntimeError('Halo 2 Editing Kit Tool not found: ' + str(tool))
    tags = lightmap_tags(h2ek, scenario)
    if not tags:
        raise RuntimeError('No Halo 2 lightmap found for ' + scenario + ' in ' + str(h2ek) + '. Light the level in the Halo 2 Editing Kit first.')
    out = []
    for lightmap, bitmap in tags:
        signature = dict(version=EXPORT_VERSION, lightmap=fingerprint(h2ek / 'tags' / (lightmap + '.scenario_structure_lightmap')),
                         bitmap=fingerprint(h2ek / 'tags' / (bitmap + '.bitmap')))
        folder = Path(cache) / 'h2_lightmaps' / hashlib.sha256(json.dumps(signature, default=str).encode()).hexdigest()[:24]
        npz, pages = folder / 'lightmap.npz', folder / 'pages'
        if read_json(folder / 'stamp.json') != signature or not npz.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            progress('Exporting Halo 2 lighting with the Halo 2 Editing Kit: ' + Path(lightmap).name)
            xml = folder / 'lightmap.xml'
            _run([tool, 'export-tag-to-xml', h2ek / 'tags' / (lightmap + '.scenario_structure_lightmap'), xml], h2ek, cancel)
            pages.mkdir(exist_ok=True)
            _run([tool, 'export-bitmap-tga', bitmap, str(pages) + '\\lm'], h2ek, cancel)
            if not xml.is_file() or not any(pages.glob('*.tga')):
                raise RuntimeError('The Halo 2 Editing Kit did not export ' + lightmap)
            progress('Reading Halo 2 lighting: ' + Path(lightmap).name)
            arrays = parse(xml)
            xml.unlink()  # tens of MB; the parsed .npz holds what is used
            # The BSP's instance placements (rocks and other instanced pieces have their own lightmaps).
            bsp = bsp_tag(h2ek, scenario, lightmap)
            if bsp:
                bsp_xml = folder / 'bsp.xml'
                _run([tool, 'export-tag-to-xml', h2ek / 'tags' / (bsp + '.scenario_structure_bsp'), bsp_xml], h2ek, cancel)
                if bsp_xml.is_file():
                    arrays.update(parse_instances(bsp_xml)); bsp_xml.unlink()
            np.savez_compressed(npz, **arrays)
            write_json(folder / 'stamp.json', signature)
        out.append(dict(npz=str(npz), pages=str(pages), bsp=bsp_tag(h2ek, scenario, lightmap)))
    return out


def unlit_clusters(exports):
    """{BSP tag (lower case): {cluster index}} of clusters Halo 2 did not lightmap (no page: water
    planes, abyss floors). They stay out of the per-pixel structure: Halo 3 would give them
    lightmap space by area (Ascension's 700 x 700 water plane took 72% of the page)."""
    result = {}
    for export in exports:
        d = np.load(export['npz'])
        bsp = (export.get('bsp') or '').lower()
        result[bsp] = {int(k[1:-len('_bitmap')]) for k in d.files
                       if k.startswith('c') and k.endswith('_bitmap') and d[k][0] < 0}
    return result


def bsp_tag(h2ek, scenario, lightmap):
    """The BSP a Halo 2 lightmap belongs to (Tool names it <scenario>_<bsp>_lightmap), tag path or None."""
    folder = Path(h2ek) / 'tags' / Path(scenario.replace('\\', '/')).parent
    name, stem = Path(scenario.replace('\\', '/')).name, Path(lightmap.replace('\\', '/')).name
    candidates = sorted(folder.glob('*.scenario_structure_bsp'))
    for path in candidates:
        if stem == name + '_' + path.stem + '_lightmap':
            return str(path.with_suffix('').relative_to(Path(h2ek) / 'tags')).replace('/', '\\')
    if len(candidates) == 1:
        return str(candidates[0].with_suffix('').relative_to(Path(h2ek) / 'tags')).replace('/', '\\')
    return None


def _run(args, cwd, cancel=None):
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    p = subprocess.Popen([str(a) for a in args], cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
    out, _ = p.communicate()
    if p.returncode:
        raise RuntimeError('Halo 2 Tool failed (' + ' '.join(str(a) for a in args[1:2]) + '): ' + out.decode('utf-8', 'replace')[-600:])


def _clean(xml_path):
    """The kit Tool's XML as a stream the parser accepts (h2_scenario.clean_xml)."""
    import io
    from .h2_scenario import clean_xml
    return io.BytesIO(clean_xml(xml_path))


def parse(xml_path):
    """Halo 2 lightmap tag XML -> arrays: c<i>_pos/_uv/_dir/_nrm/_tri per cluster and c<i>_bitmap (page, palette)."""
    sections, render, buckets, refs = {}, {}, {}, {}
    stack = []
    for event, el in ET.iterparse(_clean(xml_path), events=('start', 'end')):
        if event == 'start':
            if el.tag == 'block':
                stack.append([el.get('name'), None])
            elif el.tag == 'element' and stack:
                stack[-1][1] = int(el.get('index'))
            continue
        if el.tag == 'block':
            stack.pop(); el.clear(); continue
        if el.tag != 'element' or not stack:
            continue
        names = [b[0] for b in stack]; block = stack[-1][0]
        fields = {f.get('name'): (f.text or '').strip() for f in el.findall('field')}
        # Per-vertex light (instances Halo 2 lit per vertex): geometry buckets of colour and
        # incident direction, and each instance's bucket and first vertex in it.
        if 'geometry buckets' in names and block == 'raw vertices':
            b = buckets.setdefault(stack[names.index('geometry buckets')][1], dict(col=[], dir=[]))
            b['col'].append([float(x) for x in fields.get('primary lightmap color', '0,0,0').split(',')])
            b['dir'].append([float(x) for x in fields.get('primary lightmap incident direction', '0,0,0').split(',')])
            el.clear(); continue
        if 'instance bucket refs' in names:
            ref = refs.setdefault(stack[names.index('instance bucket refs')][1], [-1, []])
            if block == 'section offsets':
                ref[1].append(int(fields.get('section offset', 0)))
            elif block == 'instance bucket refs':
                ref[0] = int(fields.get('bucket index', -1))
            el.clear(); continue
        # Clusters (c<i>, world space) and instance definitions (p<i>, the instance's own space).
        cluster = None
        for kind, prefix in (('clusters', 'c'), ('poop definitions', 'p')):
            if kind in names:
                cluster = prefix + str(stack[names.index(kind)][1])
        if block in ('cluster render info', 'instance render info'):
            render[('c' if block == 'cluster render info' else 'i') + str(stack[-1][1])] = (
                int(fields.get('bitmap index', -1)), int(fields.get('palette index', -1)))
        elif cluster is not None:
            s = sections.setdefault(cluster, dict(pos=[], uv=[], dir=[], nrm=[], parts=[], strip=[]))
            if block == 'raw vertices':
                for key, name in (('pos', 'position'), ('uv', 'primary lightmap texcoord'), ('dir', 'primary lightmap incident direction'), ('nrm', 'normal')):
                    s[key].append([float(x) for x in fields[name].split(',')])
            elif block == 'strip indices':
                s['strip'].append(int(fields['index']))
            elif block == 'parts':
                flags = el.find("field[@name='flags']")
                s['parts'].append((int(fields['strip start index']), int(fields['strip length']),
                                   flags is not None and 'override triangle list' in (flags.text or '')))
        el.clear()
    arrays = {}
    for key, s in sections.items():
        if not s['pos']:
            continue
        arrays[f'{key}_pos'] = np.array(s['pos'], np.float32); arrays[f'{key}_uv'] = np.array(s['uv'], np.float32)
        arrays[f'{key}_dir'] = np.array(s['dir'], np.float32); arrays[f'{key}_nrm'] = np.array(s['nrm'], np.float32)
        arrays[f'{key}_tri'] = np.array(triangles(s['parts'], s['strip']), np.int32).reshape(-1, 3)
    for key, value in render.items():
        arrays[f'{key}_bitmap'] = np.array(value, np.int32)
    for key, b in buckets.items():
        arrays[f'b{key}_col'] = np.array(b['col'], np.float32).reshape(-1, 3)
        arrays[f'b{key}_dir'] = np.array(b['dir'], np.float32).reshape(-1, 3)
    for key, (bucket, offsets) in refs.items():
        arrays[f'i{key}_bucket'] = np.array([bucket, offsets[0] if offsets else -1], np.int32)
    return arrays


def parse_instances(xml_path):
    """Halo 2 BSP tag XML -> instance placements: inst_def (definition index), inst_matrix (N x 4 x 4,
    columns forward, left, up times scale, then position), inst_per_pixel (lightmapping policy 0)."""
    defs, mats, per_pixel = [], [], []
    stack = []
    for event, el in ET.iterparse(_clean(xml_path), events=('start', 'end')):
        if event == 'start':
            if el.tag == 'block':
                stack.append(el.get('name'))
            continue
        if el.tag == 'block':
            stack.pop(); el.clear(); continue
        if el.tag == 'element' and stack and stack[-1] == 'instanced geometry instances' and len(stack) == 1:
            fields = {f.get('name'): (f.text or '').strip() for f in el.findall('field')}
            index = el.find("block_index[@type='instance definition']")
            vec = lambda name: [float(x) for x in fields[name].split(',')]
            scale = float(fields.get('scale', 1) or 1)
            m = np.eye(4)
            m[:3, 0], m[:3, 1], m[:3, 2] = (np.array(vec(n)) * scale for n in ('forward', 'left', 'up'))
            m[:3, 3] = vec('position')
            defs.append(int(index.get('index')) if index is not None else -1); mats.append(m)
            per_pixel.append(fields.get('lightmapping policy', '0').split(',')[0].strip() == '0')
        if el.tag == 'element':
            el.clear()
    return dict(inst_def=np.array(defs, np.int32), inst_matrix=np.array(mats, np.float64).reshape(-1, 4, 4),
                inst_per_pixel=np.array(per_pixel, bool))


def triangles(parts, strip):
    """Triangles of Halo 2 parts: a triangle list ("override triangle list") or a triangle strip."""
    result = []
    for start, length, tri_list in parts:
        idx = strip[start:start + length]
        if tri_list:
            result += [idx[i:i + 3] for i in range(0, len(idx) - 2, 3)]
        else:
            for i in range(len(idx) - 2):
                a, b, c = idx[i:i + 3]
                if a == b or b == c or a == c:
                    continue
                result.append([a, b, c] if i % 2 == 0 else [b, a, c])
    return result


def read_h3_meshes(csv_path):
    """Halo 3 lightmap meshes (tag helper's lightmap_mesh CSV): every mesh with lightmap UVs, merged."""
    verts, tris = {}, {}
    for line in open(csv_path, encoding='utf-8'):
        if line.startswith('#indices'):
            parts = line.rstrip('\n').split(',')
            tris[parts[2]] = np.array(parts[3].split(), dtype=np.int64).reshape(-1, 3)
            continue
        f = line.rstrip('\n').split(',')
        if f[0] == 'path':
            continue
        verts.setdefault(f[1], []).append([float(x) for x in f[3:]])
    all_v, all_t = [], []
    for m, rows in verts.items():
        rows = np.array(rows)
        if m not in tris or not np.any(rows[:, 8:10]):
            continue
        all_t.append(tris[m] + sum(len(v) for v in all_v)); all_v.append(rows)
    if not all_v:
        return np.zeros((0, 10)), np.zeros((0, 3), np.int64)
    return np.concatenate(all_v), np.concatenate(all_t)


def source(objects):
    """(Halo 2 kit, scenario) for imported Halo 2 map objects: the map was built by a Halo 2 kit's Tool
    (HaloBridge kit_maps record source.json beside the map), or None."""
    from .catalog import read_json
    for obj in objects:
        manifest = obj.get('hb_map_manifest')
        if not manifest or not Path(manifest).is_file():
            continue
        folder = Path(manifest).parent
        for res in (read_json(folder / 'stamp.json', {}) or {}).get('resources', []):
            info = read_json(Path(res[0]).parent / 'source.json', {}) if res else {}
            if info.get('kit') and info.get('scenario'):
                return info['kit'], info['scenario']
    return None
