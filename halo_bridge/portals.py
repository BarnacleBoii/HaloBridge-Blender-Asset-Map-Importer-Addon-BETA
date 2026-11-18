"""+portal planes: cut the level structure into clusters.

Halo 3's Tool splits the structure where +portal faces cross it; each cluster is compiled as
its own section, so big levels and very dense structure stay under Halo 3's per-section limits
(32,767 vertices) and draw faster. Halo 3 portals may intersect without joining.
"""
import bpy
from mathutils import Vector

MATERIAL = '+portal'
PORTAL_OFFSET = 0.113  # cuts sit this fraction of a piece past the even split (see grid_cuts)
COLLECTION = 'Portals'
OBJECT = 'HaloBridge Portals'


def is_portal(obj):
    """An object made only of +portal faces."""
    mats = [m for m in getattr(obj.data, 'materials', []) if m]
    return obj.type == 'MESH' and bool(mats) and all(m.name.split('.')[0] == MATERIAL for m in mats)


def material():
    mat = bpy.data.materials.get(MATERIAL) or bpy.data.materials.new(MATERIAL)
    mat.diffuse_color = (0.2, 0.55, 1.0, 0.25)  # see-through blue in the viewport
    return mat


def level_bounds(scene):
    """World-space (min, max) of the exported level geometry, without sky and portal objects."""
    from . import geometry_export
    for layer in scene.view_layers:
        layer.update()  # current object transforms
    points = []
    for obj in geometry_export.objects(scene):
        if geometry_export.is_sky(obj) or is_portal(obj):
            continue
        points += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    if not points:
        return None
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo, hi


def grid_cuts(lo, hi, spacing):
    """Cut positions strictly inside (lo, hi), evenly spaced about every `spacing`."""
    import math
    length = hi - lo
    if spacing <= 0 or length <= spacing:
        return []
    pieces = math.ceil(length / spacing)  # pieces about as long as spacing
    # Off the even split by 11.3% of a piece: an even split puts a cut on a symmetric map's centre
    # line, where walls and floors lie in the portal's plane (Burial Mounds, Cyclotron: "couldn't
    # build leaf map during portalization").
    return [lo + length * (i + PORTAL_OFFSET) / pieces for i in range(1, pieces)]


def grid(lo, hi, step, min_margin=1.0):
    """(vertices, quads) of vertical planes every `step` across the box lo..hi (with a margin)."""
    margin = max((hi - lo).length * .02, min_margin)
    lo = lo - Vector((margin, margin, margin)); hi = hi + Vector((margin, margin, margin))
    verts, faces = [], []
    def quad(a, b, c, d):
        base = len(verts); verts.extend((tuple(a), tuple(b), tuple(c), tuple(d))); faces.append((base, base + 1, base + 2, base + 3))
    for x in grid_cuts(lo.x, hi.x, step):
        quad(Vector((x, lo.y, lo.z)), Vector((x, hi.y, lo.z)), Vector((x, hi.y, hi.z)), Vector((x, lo.y, hi.z)))
    for y in grid_cuts(lo.y, hi.y, step):
        quad(Vector((lo.x, y, lo.z)), Vector((hi.x, y, lo.z)), Vector((hi.x, y, hi.z)), Vector((lo.x, y, hi.z)))
    return verts, faces


# Halo 3 compiles each cluster's render geometry as one mesh with 16-bit indices (at most 65,535,
# about 21,800 triangles); a structure without portals is one cluster. Backwash's 23,936 triangles
# overflowed it ("tool overflowed indices_word_block"). Above AUTO_TRIANGLES, preparation adds a
# grid sized for about CELL_TRIANGLES per cluster (levels are uneven, so well under the limit).
# Tool's index count is about 3.2 x the triangles (Backwash: 23,936 -> 75,561), and its vertex count
# can pass the 32,767 vertices per section first (Chiron TL34: 33,610 in one cluster), so portals
# start well below either limit.
AUTO_TRIANGLES = 14000
CELL_TRIANGLES = 9000  # a cluster that still passes the vertex limit compiles again smaller (ui.retry_with_smaller_clusters)


MAX_SLABS = 16


def cut_layout(attempt, lo, hi):
    """Which axes a portal attempt cuts: 'xy' (a grid), 'x' or 'y' (parallel slabs). Retries after
    Tool "couldn't build leaf map during portalization" (Warlock, Derelict, Street Sweeper: every
    shifted grid failed) first keep the grid with only the terrain in the structure (see
    INSTANCED_FROM), then switch to slabs across the level's long side, then its short side;
    slabs never cross each other."""
    long_axis = 'x' if hi[0] - lo[0] >= hi[1] - lo[1] else 'y'
    return {2: long_axis, 3: 'y' if long_axis == 'x' else 'x'}.get(attempt, 'xy')


# From this attempt on, the pieces that are not terrain (Halo 2 BSP instances, machines, scenery)
# and that a portal crosses are compiled as instances, not structure: they overlap the terrain
# ("overlapping surfaces"), and a portal through overlapping structure left Tool unable to build
# its leaf map (Gemini compiled once they were instances). Only the crossed ones move, because
# instances get Tool's light instead of Halo 2's (dark inside: Gemini's pillars).
INSTANCED_FROM = 1


def avoid_spans(cuts, spans, lo, hi, samples=41):
    """Cuts moved (each within half the gap to its neighbours) to where they cross the least of
    spans [(start, end, weight)] along that axis: the BSP pieces and objects a portal would cross
    become instances, lit by Tool instead of Halo 2 (Warlock's central pillars went black)."""
    import numpy as np
    if not cuts or not spans:
        return list(cuts)
    s = np.asarray(spans, dtype=np.float64)
    bounds = [lo] + list(cuts) + [hi]
    moved = []
    for i, cut in enumerate(cuts):
        left = cut - (cut - bounds[i]) / 2
        right = cut + (bounds[i + 2] - cut) / 2
        best = None
        clear = (right - left) * .02  # never exactly on a piece's side, where faces lie in the portal's plane
        for p in np.linspace(left, right, samples):
            cost = s[(s[:, 0] - clear <= p) & (p <= s[:, 1] + clear), 2].sum()
            key = (cost, abs(p - cut))
            if best is None or key < best[0]:
                best = (key, float(p))
        moved.append(best[1])
    return moved


def crosses(obj, xs, ys):
    """True when a vertical portal plane at one of xs (x = const) or ys (y = const) passes through
    the object's world bounding box."""
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    x0, x1 = min(p.x for p in pts), max(p.x for p in pts)
    y0, y1 = min(p.y for p in pts), max(p.y for p in pts)
    return any(x0 < x < x1 for x in xs) or any(y0 < y < y1 for y in ys)


def adaptive_cuts(centers, lo, hi, cell_triangles=CELL_TRIANGLES, attempt=0, threshold=AUTO_TRIANGLES):
    """(x cuts, y cuts) for full-span portal planes, placed where the triangles are: each cut axis
    is cut at quantiles of the triangle centres (N x 2 array), with more cuts until no cell holds
    more than cell_triangles. A uniform grid left one dense cell over Halo 3's 32,767 vertices per
    section (Gemini's cluster 13: 38,228). Cuts move off the exact quantile by a small offset so they
    don't lie in a face's plane. See cut_layout for what each retry attempt cuts."""
    import numpy as np
    pts = np.asarray(centers, dtype=np.float64).reshape(-1, 2)
    if len(pts) <= threshold:
        return [], []
    layout = cut_layout(attempt, lo, hi)
    # Each retry also moves the cuts by about 1.7% of the level.
    nudge = (0.0137 + 1.73 * attempt) * max(hi[0] - lo[0], hi[1] - lo[1]) / 100
    limit = MAX_SLABS if layout == 'xy' else MAX_SLABS * 2
    def cuts(axis, n):
        if axis not in layout or n < 2:
            return []
        qs = np.linspace(0, 1, n + 1)[1:-1]
        return sorted(set(float(v) + nudge for v in np.quantile(pts[:, 0 if axis == 'x' else 1], qs)))
    def fullest(nx, ny):
        xs, ys = cuts('x', nx), cuts('y', ny)
        cells = np.zeros((len(xs) + 1, len(ys) + 1), np.int64)
        np.add.at(cells, (np.searchsorted(xs, pts[:, 0]), np.searchsorted(ys, pts[:, 1])), 1)
        return cells.max()
    # One slab more at a time, on the axis that empties the fullest cell most: as few clusters
    # (and portals) as the limit allows. Cutting both axes every step gave Gemini 20 planes and
    # about 120 clusters, and Sapien "overflowed working portal stack during visibility traversal".
    wide = hi[0] - lo[0] >= hi[1] - lo[1]
    nx = ny = 1
    while fullest(nx, ny) > cell_triangles and max(nx, ny) < limit:
        options = [(fullest(nx + 1, ny), not wide, 'x')] if 'x' in layout else []
        options += [(fullest(nx, ny + 1), wide, 'y')] if 'y' in layout else []
        if min(options)[2] == 'x':
            nx += 1
        else:
            ny += 1
    return cuts('x', nx), cuts('y', ny)


def grid_from_cuts(lo, hi, xs, ys, min_margin=1.0):
    """(vertices, quads) of full-span vertical planes at the given x and y positions."""
    margin = max((hi - lo).length * .02, min_margin)
    lo = lo - Vector((margin, margin, margin)); hi = hi + Vector((margin, margin, margin))
    verts, faces = [], []
    def quad(a, b, c, d):
        base = len(verts); verts.extend((tuple(a), tuple(b), tuple(c), tuple(d))); faces.append((base, base + 1, base + 2, base + 3))
    for x in xs:
        quad(Vector((x, lo.y, lo.z)), Vector((x, hi.y, lo.z)), Vector((x, hi.y, hi.z)), Vector((x, lo.y, hi.z)))
    for y in ys:
        quad(Vector((lo.x, y, lo.z)), Vector((hi.x, y, lo.z)), Vector((hi.x, y, hi.z)), Vector((lo.x, y, hi.z)))
    return verts, faces


def auto_spacing(lo, hi, triangles):
    """Grid spacing (world units) giving about CELL_TRIANGLES per cell, or None when not needed."""
    import math
    if triangles <= AUTO_TRIANGLES:
        return None
    area = max((hi.x - lo.x) * (hi.y - lo.y), 1e-6)
    return max(math.sqrt(area * CELL_TRIANGLES / triangles), 4.0)


def fit_to_box(objects, lo, hi, overlap=0.0):
    """Stretch each axis-aligned portal plane to the sealed boundary box lo..hi (world units), so it
    splits the sealed space in two: Tool reports "portal leakage" and makes no clusters when a
    portal stops short of the walls. Its edges lie on the walls; planes that poked past them left
    portal faces outside the world, and Tool "couldn't build leaf map during portalization"
    (Desolation, Warlock, Zanzibar). Other portal faces are left as they are."""
    for obj in objects:
        mesh = obj.data
        to_world, to_local = obj.matrix_world, obj.matrix_world.inverted()
        for poly in mesh.polygons:
            n = (to_world.to_3x3() @ poly.normal).normalized()
            axis = max(range(3), key=lambda i: abs(n[i]))
            if abs(n[axis]) < .99:
                continue
            centre = to_world @ poly.center
            for index in poly.vertices:
                v = to_world @ mesh.vertices[index].co
                for i in range(3):
                    if i != axis:
                        v[i] = lo[i] - overlap if v[i] < centre[i] else hi[i] + overlap
                mesh.vertices[index].co = to_local @ v
        mesh.update()


def add_grid(scene, spacing, units=1.0):
    """Replace HaloBridge's portal grid with vertical +portal planes every `spacing` world units
    (Blender units = world units x units) across the level. Returns the number of planes."""
    bounds = level_bounds(scene)
    if bounds is None:
        raise ValueError('There is no level geometry to cut.')
    verts, faces = grid(*bounds, spacing * units, units)
    old = bpy.data.objects.get(OBJECT)
    if old is not None:
        mesh = old.data; bpy.data.objects.remove(old, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    if not faces:
        return 0
    mesh = bpy.data.meshes.new(OBJECT)
    mesh.from_pydata(verts, [], faces); mesh.uv_layers.new(); mesh.update()
    mesh.materials.append(material())
    obj = bpy.data.objects.new(OBJECT, mesh)
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION); scene.collection.children.link(coll)
    coll.objects.link(obj)
    obj.display_type = 'WIRE'; obj.show_in_front = True
    obj['hb_portal'] = True; obj['hb_working_units'] = units
    return len(faces)
