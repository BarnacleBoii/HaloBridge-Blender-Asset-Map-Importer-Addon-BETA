"""Background Blender: Halo 2 lightmaps -> a Halo 3 level's 9-layer lightmap master (see h2_lightmaps).

blender -b --factory-startup --python h2_lightmap_worker.py -- <job json>
job: {"package": add-on folder parent, "exports": [{"npz", "pages"}], "mesh_csv", "master_in", "master_out",
      "brightness"}
master_in is Tool's master (its size gives the page size; pixels that find no Halo 2 surface keep its light)."""
import json, math, sys
from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

job = json.loads(sys.argv[sys.argv.index('--') + 1])
sys.path.insert(0, job['package'])
from halo_bridge import h2_lightmaps as h2

P3, T3 = h2.read_h3_meshes(job['mesh_csv'])
master = np.fromfile(job['master_in'], dtype=np.float16)
size = int(round(math.sqrt(master.size / (9 * 4))))
if 9 * 4 * size * size != master.size:
    raise SystemExit('Unexpected lightmap master size: ' + str(master.size))
out = master.reshape(9, size, size, 4).astype(np.float32)
print('Halo 3 lightmap meshes:', len(P3), 'vertices,', len(T3), 'triangles; page', size, flush=True)

# All Halo 2 clusters in one triangle tree, remembering cluster and page.
sections, verts, faces, owner = [], [], [], []
for e, export in enumerate(job['exports']):
    d = np.load(export['npz'])
    def add(s):
        base = len(verts); sections.append(s)
        verts.extend(Vector(v) for v in s['pos'])
        for t, tri in enumerate(s['tri']):
            faces.append(tuple(int(i) + base for i in tri)); owner.append((len(sections) - 1, t))
    for key in sorted({k.rsplit('_', 1)[0] for k in d.files if k.endswith('_pos') and k.startswith('c')}):
        if key + '_tri' not in d.files or key + '_bitmap' not in d.files:
            continue
        add(dict(pos=d[key + '_pos'], uv=d[key + '_uv'], dir=d[key + '_dir'], tri=d[key + '_tri'],
                 nrm=d[key + '_nrm'], page=int(d[key + '_bitmap'][0]), pages=export['pages']))
    # Instances (rocks ...): their definition's geometry placed in the world, each with its own page.
    if 'inst_def' in d.files:
        for k, (definition, matrix, per_pixel) in enumerate(zip(d['inst_def'], d['inst_matrix'], d['inst_per_pixel'])):
            key = f'p{definition}'
            if key + '_pos' not in d.files:
                continue
            rot = matrix[:3, :3]; scale = np.linalg.norm(rot[:, 0]) or 1
            pos = (d[key + '_pos'] @ rot.T + matrix[:3, 3]).astype(np.float32)
            nrm = d[key + '_nrm'] @ (rot / scale).T
            if per_pixel and f'i{k}_bitmap' in d.files and d[f'i{k}_bitmap'][0] >= 0:
                dirs = d[key + '_dir'] @ (rot / scale).T
                add(dict(pos=pos, uv=d[key + '_uv'], dir=dirs, tri=d[key + '_tri'], nrm=nrm,
                         page=int(d[f'i{k}_bitmap'][0]), pages=export['pages']))
                continue
            # Lit per vertex in Halo 2: a colour and incident direction for each of the definition's
            # vertices, from the instance's place in a geometry bucket.
            ref = d[f'i{k}_bucket'] if f'i{k}_bucket' in d.files else None
            if ref is None or ref[0] < 0 or f'b{ref[0]}_col' not in d.files:
                continue
            cols, bdirs, n = d[f'b{ref[0]}_col'], d[f'b{ref[0]}_dir'], len(pos)
            if ref[1] < 0 or ref[1] + n > len(cols) or not cols[ref[1]:ref[1] + n].any():
                continue  # no slice, or an empty one (a per-pixel instance whose page is missing)
            add(dict(pos=pos, col=h2.fill_empty_vertices(cols[ref[1]:ref[1] + n], d[key + '_tri']),
                     dir=bdirs[ref[1]:ref[1] + n] @ (rot / scale).T, tri=d[key + '_tri'], nrm=nrm))
tree = BVHTree.FromPolygons(verts, faces, all_triangles=True)
print('Halo 2 clusters:', len(sections), 'triangles:', len(faces), flush=True)

pages = {}
def page(folder, index):
    key = (folder, index)
    if key not in pages:
        found = sorted(p for p in Path(folder).glob(f'*_{index:02d}_00.*') if p.suffix.lower() in ('.tga', '.png'))  # Halo 2 TGA, Halo CE PNG
        if not found:
            pages[key] = None
        else:
            img = bpy.data.images.load(str(found[0])); img.colorspace_settings.name = 'Non-Color'
            w, h = img.size; px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px)
            rgb = px.reshape(h, w, 4)[:, :, :3].copy()  # Blender rows start at the bottom
            if found[0].suffix.lower() == '.png':
                # Halo CE fills unused lightmap texels with a pure red / yellow checker: no light.
                r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
                rgb[(r > .99) & (b < .01) & ((g < .01) | (g > .99))] = 0
            pages[key] = h2.fill_empty(rgb)
    return pages[key]

def sample(img, uv):
    h, w = img.shape[:2]
    u = uv[0] * w - .5; v = (1 - uv[1]) * h - .5
    x0, y0 = int(math.floor(u)), int(math.floor(v)); tx, ty = u - x0, v - y0
    def px(x, y): return img[min(max(y, 0), h - 1), min(max(x, 0), w - 1)]
    return (px(x0, y0) * (1 - tx) + px(x0 + 1, y0) * tx) * (1 - ty) + (px(x0, y0 + 1) * (1 - tx) + px(x0 + 1, y0 + 1) * tx) * ty

def bary(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-20: return np.array([1., 0, 0])
    v = (d11 * d20 - d01 * d21) / den; w = (d00 * d21 - d01 * d20) / den
    return np.array([1 - v - w, v, w])

def best_match(p, n):
    """The Halo 2 surface a Halo 3 lightmap pixel lies on: (section, triangle, barycentric weights)
    or None. Of the Halo 2 triangles within SEARCH_DISTANCE, the nearest one facing the same way
    (normals within ~60 degrees): where a rock meets the ground, or a piece's hidden back face
    touches a visible one, the closest point can be on the other surface, whose light is dark.
    The nearest of any facing is the fallback."""
    nn = n / (np.linalg.norm(n) or 1)
    best = fallback = None
    for loc, _, index, dist in tree.find_nearest_range(Vector(p), h2.SEARCH_DISTANCE):
        si, ti = owner[index]; s = sections[si]; t2 = s['tri'][ti]
        wb = np.clip(bary(np.array(loc), *s['pos'][t2]), 0, 1); wb /= wb.sum() or 1
        if fallback is None or dist < fallback[0]:
            fallback = (dist, s, t2, wb)
        n2 = wb @ s['nrm'][t2] if 'nrm' in s else None
        if n2 is not None and float(n2 @ nn) > .5 * (np.linalg.norm(n2) or 1) and (best is None or dist < best[0]):
            best = (dist, s, t2, wb)
    chosen = best or fallback
    return None if chosen is None else chosen[1:]

written = np.zeros((size, size), bool); misses = 0
P, N, L = P3[:, 0:3], P3[:, 3:6], P3[:, 8:10] * size
# Pass 1: every lightmap pixel a triangle covers or reaches through filtering (centre within
# REACH pixels). Small pieces get tiny charts (Ascension's rocks: 0.03-0.4 pixels per
# triangle), so most of their pixels have no triangle over the centre yet are read when drawn.
# Each pixel keeps the triangle that covers it best and the sum of the normals reaching it.
REACH = 1.0
cand_d = np.full((size, size), np.inf, np.float32); cand_t = np.full((size, size), -1, np.int64)
cand_w = np.zeros((size, size, 3), np.float32)
nsum = np.zeros((size, size, 3), np.float32); ncount = np.zeros((size, size), np.int32)
for count, tri in enumerate(T3):
    if count % 2000 == 0:
        print(f'Copying Halo 2 lighting: triangle {count}/{len(T3)}', flush=True)
    uv = L[tri]
    area2 = abs((uv[1, 0] - uv[0, 0]) * (uv[2, 1] - uv[0, 1]) - (uv[2, 0] - uv[0, 0]) * (uv[1, 1] - uv[0, 1]))
    # Height over each vertex's opposite edge: a barycentric weight w_i outside the triangle is
    # -distance / height_i, so the distance to the triangle is about max(-w_i * height_i).
    edges = np.array([np.linalg.norm(uv[(i + 2) % 3] - uv[(i + 1) % 3]) for i in range(3)])
    heights = area2 / np.maximum(edges, 1e-9)
    (x0, y0), (x1, y1) = np.floor(uv.min(0) - REACH).astype(int), np.ceil(uv.max(0) + REACH).astype(int)
    for y in range(max(y0, 0), min(y1, size)):
        for x in range(max(x0, 0), min(x1, size)):
            c = np.array([x + .5, y + .5])
            if area2 < 1e-9:  # a sliver: its nearest vertex
                dist = float(np.min(np.linalg.norm(uv - c, axis=1))); w = np.eye(3)[np.argmin(np.linalg.norm(uv - c, axis=1))]
            else:
                w = bary(np.append(c, 0), *(np.append(v, 0) for v in uv))
                dist = float(np.max(-w * heights))
                w = np.clip(w, 0, None); w /= w.sum() or 1
            if dist > REACH:
                continue
            n = w @ N[tri]
            nsum[y, x] += n / (np.linalg.norm(n) or 1); ncount[y, x] += 1
            if dist < cand_d[y, x]:
                cand_d[y, x], cand_t[y, x], cand_w[y, x] = dist, count, w

# Pass 2: each used pixel takes Halo 2's light at its best triangle's point. Where faces
# pointing different ways share a pixel (both sides of a small rock), directional light encoded
# for one would read negative - black, tinted - on the other, so the light is made even in
# proportion to how much their normals disagree.
brightness = job.get('brightness', h2.BRIGHTNESS); objects_lit = 0
ys, xs = np.nonzero(cand_t >= 0)
print(f'Copying Halo 2 lighting: {len(ys)} lightmap pixels in use', flush=True)
for k, (y, x) in enumerate(zip(ys, xs)):
    if k % 100000 == 0 and k:
        print(f'Copying Halo 2 lighting: pixel {k}/{len(ys)}', flush=True)
    tri = T3[cand_t[y, x]]; w = cand_w[y, x]
    p = w @ P[tri]; n = w @ N[tri]
    match = best_match(p, n); nearby = False
    if match is None:
        # Not a Halo 2 surface: an object compiled into the level (Halo 2 lit objects from the
        # level's light around them) or new geometry. It takes the nearest Halo 2 surface's light.
        loc, _, index, dist = tree.find_nearest(Vector(p), h2.OBJECT_SEARCH_DISTANCE)
        if index is None:
            misses += 1; continue
        si, ti = owner[index]; s = sections[si]; t2 = s['tri'][ti]
        wb = np.clip(bary(np.array(loc), *s['pos'][t2]), 0, 1); wb /= wb.sum() or 1
        nearby = True; objects_lit += 1
    else:
        s, t2, wb = match
    if 'col' in s:
        colour = wb @ s['col'][t2]
    else:
        img = page(s['pages'], s['page'])
        if img is None:
            misses += 1; continue
        colour = sample(img, wb @ s['uv'][t2])
    mean = nsum[y, x] / ncount[y, x]; agree = float(np.linalg.norm(mean))
    directional = h2.DIRECTIONAL * min(max((agree - .6) / .35, 0.0), 1.0)
    if nearby:
        directional *= .5  # borrowed light: its direction belongs to another surface
    normal = mean if agree > .2 else n
    out[:, y, x, :3] = h2.encode(colour, wb @ s['dir'][t2], normal, brightness, directional)
    out[:, y, x, 3] = 0
    written[y, x] = True
written |= cand_t >= 0  # used pixels without Halo 2 light keep Tool's; padding never overwrites them

# Pixels next to copied ones (chart padding, read by filtering) take their neighbours' light.
for _ in range(4):
    acc = np.zeros_like(out); cnt = np.zeros((size, size), np.float32)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        m = np.roll(written, (dy, dx), axis=(0, 1))
        acc += np.roll(out, (dy, dx), axis=(1, 2)) * m[None, :, :, None]; cnt += m
    grow = (~written) & (cnt > 0)
    out[:, grow] = acc[:, grow] / cnt[grow][None, :, None]; written |= grow
out.astype(np.float16).tofile(job['master_out'])

def light_at(p, n):
    """(colour, incident direction, directional share) of Halo 2's light at a point, or None."""
    match = best_match(p, n); borrowed = False
    if match is None:
        loc, _, index, dist = tree.find_nearest(Vector(p), h2.OBJECT_SEARCH_DISTANCE)
        if index is None:
            return None
        si, ti = owner[index]; s = sections[si]; t2 = s['tri'][ti]
        wb = np.clip(bary(np.array(loc), *s['pos'][t2]), 0, 1); wb /= wb.sum() or 1
        borrowed = True
    else:
        s, t2, wb = match
    if 'col' in s:
        colour = wb @ s['col'][t2]
    else:
        img = page(s['pages'], s['page'])
        if img is None:
            return None
        colour = sample(img, wb @ s['uv'][t2])
    return colour, wb @ s['dir'][t2], h2.DIRECTIONAL * (.5 if borrowed else 1)

# Instances Halo 3 lights per vertex (BSP pieces and objects compiled as instances) get Halo 2's
# light at each vertex too; without it they keep Tool's draft light, black indoors.
vertices_lit = vertices_missed = 0
if job.get('pervertex_in'):
    instances = json.load(open(job['pervertex_in'], encoding='utf-8')).get('instances', [])
    meshes = h2.read_mesh_vertices(job['mesh_csv'])
    order, chunks = [], []
    for item in instances:
        rows = meshes.get(item['mesh'])
        if rows is None or len(rows) != item['count']:
            continue
        axes = np.array([item['forward'], item['left'], item['up']], dtype=np.float64)
        local = h2.decompress_positions(rows[:, 0:3], item.get('bounds'))
        pos = local @ axes * item['scale'] + np.array(item['position'])
        nrm = rows[:, 3:6] @ axes
        values = np.full((len(rows), 15), np.nan, np.float32)
        for v in range(len(rows)):
            found = light_at(pos[v], nrm[v])
            if found is None:
                vertices_missed += 1; continue
            colour, incident, share = found
            values[v] = h2.encode_vertex(colour, incident, nrm[v], brightness, share); vertices_lit += 1
        order.append([item['block'], item['count']]); chunks.append(values)
    print(f'Copying Halo 2 lighting: {vertices_lit} instance vertices', flush=True)
    with open(job['pervertex_order'], 'w', encoding='utf-8') as f:
        json.dump(order, f)
    (np.concatenate(chunks) if chunks else np.zeros((0, 15), np.float32)).astype('<f4').tofile(job['pervertex_out'])
print(json.dumps(dict(pixels=int(written.sum()), misses=misses, objects=objects_lit, vertices=vertices_lit, vertex_misses=vertices_missed)), flush=True)
