"""Optional Decimate modifier for very dense objects before Sapien preparation.

Preparation exports every object with its modifiers applied, so the modifier is what
reduces the exported render mesh and collision. It stays on the object: its Ratio can
be changed per object in Modifier Properties, and removing it restores the full mesh.
"""
MODIFIER_NAME = 'HaloBridge Decimate'


def triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def candidates(scene, threshold):
    from . import geometry_export, sky_export
    return [o for o in geometry_export.objects(scene)
            if not geometry_export.is_sky(o) and not o.get(sky_export.PROPERTY)
            and o.modifiers.get(MODIFIER_NAME) is None and triangles(o) > threshold]


def add(scene, threshold, ratio):
    """Add a collapse Decimate modifier to every exported object over threshold triangles.
    Objects that already have one keep it (and its ratio). Returns the objects changed."""
    changed = []
    for obj in candidates(scene, threshold):
        mod = obj.modifiers.new(MODIFIER_NAME, 'DECIMATE')
        mod.decimate_type = 'COLLAPSE'
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        changed.append(obj)
    return changed
