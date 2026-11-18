"""Collision policy for current-mesh exports; never infer foliage from names."""
from pathlib import Path

# Citadel's third leaf material uses the generic shader class. Verified with the
# stock plant_tree_pine: excluding these leaf cards removes its remaining overlap
# warnings while the bark remains collidable. This is an exact tag, not a name rule.
VERIFIED_LEAF_TAGS={r'levels\solo\100_citadel\shaders\cit_tree_leafc'}

# Halo 2: Anniversary materials name their engine material shader (recorded on import as
# hb_material_shader). These are its foliage shaders, listed exactly from the shipped maps.
H2A_FOLIAGE_SHADERS={'srf_foliage_clip','srf_pbr_foliage','srf_pbr_foliage_anim','srf_pbr_foliage_new_anim',
                     'srf_pbr_foliage_macrocolor_new_anim_unlit','srf_ca_special_foliage_fakelit'}

def h2a_foliage(material):
    get=getattr(material,'get',None)
    shader=str(get('hb_material_shader','') if get else '').replace('/','\\').lower()
    return shader.rsplit('\\',1)[-1] in H2A_FOLIAGE_SHADERS

SEE_THROUGH_ALPHA={'clip','blend','alpha','multiply','additive','add'}

def leaf(material):
    """A see-through material: leaf cards and other cut-out or blended surfaces, which the
    object collision option "No leaf collision" lets players walk through."""
    get=getattr(material,'get',None)
    if not get:return False
    if h2a_foliage(material) or get('hb_transparent'):return True
    if str(get('hb_source_alpha','opaque')).lower() in SEE_THROUGH_ALPHA:return True
    from . import compat
    try:return bool(compat.is_transparent(material))
    except Exception:return False

def render_only(material,shader_source=None,shader_tag=''):
    # The per-material Collision setting was removed from the sidebar; values saved by
    # older versions (hb_collision_mode) are ignored so nothing hidden changes collision.
    # A generic transparent shader can be glass, so alpha alone is not enough.
    # Halo 2 water (water\* templates) is waded through, never stood on.
    get=getattr(material,'get',None)
    water=('\\water\\' in str(get('hb_h2_template','') if get else '').replace('/','\\').lower()
           or str(get('hb_h1_class','') if get else '').lower()=='swat')  # Halo CE water
    return bool(material.ass_jms.render_only or h2a_foliage(material) or water or
                (shader_source and shader_tag.replace('/','\\').lower() in VERIFIED_LEAF_TAGS) or
                (shader_source and Path(shader_source).suffix.lower()=='.shader_foliage'))
