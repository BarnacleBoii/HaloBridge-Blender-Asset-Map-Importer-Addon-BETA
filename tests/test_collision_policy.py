import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from halo_bridge import collision_policy
from halo_bridge.diagnostics import geometry_warnings

class CollisionPolicyTests(unittest.TestCase):
    def test_foliage_and_explicit_choices(self):
        mat=SimpleNamespace(hb_collision_mode='AUTO',ass_jms=SimpleNamespace(render_only=False))
        self.assertTrue(collision_policy.render_only(mat,'leaves.shader_foliage'))
        self.assertFalse(collision_policy.render_only(mat,'glass.shader'))
        self.assertFalse(collision_policy.render_only(mat,'tree_leafc.shader'))
        self.assertTrue(collision_policy.render_only(mat,'cit_tree_leafc.shader',r'levels\solo\100_citadel\shaders\cit_tree_leafc'))
        # Per-material collision settings from older versions no longer change anything.
        mat.hb_collision_mode='SOLID';self.assertTrue(collision_policy.render_only(mat,'leaves.shader_foliage'))
        mat.hb_collision_mode='RENDER_ONLY';self.assertFalse(collision_policy.render_only(mat,'tree_leafc.shader'))
        mat.hb_collision_mode='AUTO';mat.ass_jms.render_only=True
        self.assertTrue(collision_policy.render_only(mat,'anything.shader'))

    def test_leaf_materials(self):
        # "No leaf collision": cut-out and blended surfaces are leaves; solid ones are not.
        class Mat(dict):ass_jms=SimpleNamespace(render_only=False)
        for alpha in ('clip','blend','additive'):
            self.assertTrue(collision_policy.leaf(Mat(hb_source_alpha=alpha)),alpha)
        self.assertTrue(collision_policy.leaf(Mat(hb_transparent='alpha')))
        self.assertFalse(collision_policy.leaf(Mat(hb_source_alpha='opaque')))
        self.assertFalse(collision_policy.leaf(None))
        # Halo 2 water is waded through whatever the object setting.
        self.assertTrue(collision_policy.render_only(Mat(hb_h2_template=r'shaders\shader_templates\water\water_pool_cube')))

    def test_h2a_foliage_shaders(self):
        class Mat(dict):ass_jms=SimpleNamespace(render_only=False)
        leaves=Mat(hb_material_shader=r'shaders\material_shaders\materials\special\srf_ca_special_foliage_fakelit')
        self.assertTrue(collision_policy.render_only(leaves,'leaves.shader'))
        self.assertTrue(collision_policy.render_only(Mat(hb_material_shader=r'shaders\material_shaders\materials\srf_pbr_foliage'),None))
        self.assertFalse(collision_policy.render_only(Mat(hb_material_shader=r'shaders\material_shaders\materials\srf_pbr_grime_clip'),None))
        self.assertFalse(collision_policy.render_only(Mat(),'rock.shader'))

    def test_warning_names_and_deduplication(self):
        text='WARNING (poop hb_0.001) overlapping surfaces\rWARNING (poop hb_0.001) overlapping surfaces\nWARNING rasterizer: leaking textures\nWARNING (poop hb_1) duplicate triangle'
        self.assertEqual(geometry_warnings(text,{'hb_0':'pine','hb_1':'rock'}),['WARNING (object pine) overlapping surfaces','WARNING (object rock) duplicate triangle'])

if __name__=='__main__':unittest.main()
