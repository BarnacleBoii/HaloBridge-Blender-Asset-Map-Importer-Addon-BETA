"""Halo 3 stand-in shaders and surface materials for converted Halo 2 shaders."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import standins, h2_scenario


class Standins(unittest.TestCase):
    def test_templates(self):
        cfg = dict(water_shader='OCEAN')
        self.assertEqual(standins.standin(r'shaders\shader_templates\transparent\plasma_alpha', cfg), standins.PLASMA_SHADER)
        self.assertEqual(standins.standin(r'shaders\shader_templates\transparent\two_alpha_env_detail', cfg), standins.GLASS_SHADER)
        self.assertEqual(standins.standin(r'shaders\shader_templates\water\water_pool_cube', cfg), standins.water_shader('OCEAN'))
        # Light bands glow (illum), clouds and opaque surfaces are converted as before.
        for template in (r'shaders\shader_templates\transparent\one_alpha_env_illum', r'shaders\shader_templates\transparent\two_alpha_clouds',
                         r'shaders\shader_templates\opaque\tex_bump', '', None):
            self.assertIsNone(standins.standin(template, cfg), template)
        self.assertIsNone(standins.standin(r'x\water\water_pool_cube', dict(water_shader='CONVERTED')))
        self.assertIsNone(standins.standin(r'x\transparent\plasma_alpha', dict(effect_standins=False)))
        # A kit without the Halo 3 shader converts it instead.
        self.assertIsNone(standins.standin(r'x\transparent\plasma_alpha', dict(kit=tempfile.mkdtemp())))

    def test_halo_ce_classes(self):
        cfg = dict(water_shader='POND')
        self.assertEqual(standins.standin('', cfg, 'spla'), standins.PLASMA_SHADER)
        self.assertEqual(standins.standin('', cfg, 'sgla'), standins.GLASS_SHADER)
        self.assertEqual(standins.standin('', cfg, 'swat'), standins.water_shader('POND'))
        for shader_class in ('schi', 'sotr', 'senv', ''):
            self.assertIsNone(standins.standin('', cfg, shader_class), shader_class)

    def test_materials(self):
        names = {'hard_metal_thick', 'tough_terrain_dirt', 'liquid_thin_water'}
        self.assertEqual(standins.h3_material('hard_metal_thick_for', names), 'hard_metal_thick')
        self.assertEqual(standins.h3_material('tough_terrain_dirt', names), 'tough_terrain_dirt')
        self.assertEqual(standins.h3_material('cloth_banner', names), '')
        self.assertEqual(standins.h3_material('', names), '')

    def test_h2_material_name(self):
        kit = Path(tempfile.mkdtemp()); shader = kit / 'tags' / 'a' / 'b.shader'; shader.parent.mkdir(parents=True)
        shader.write_bytes(b'\0' * 64 + b'stemshaders\\shader_templates\\opaque\\tex_bump\0hard_metal_thick_fordfbt\0\0')
        self.assertEqual(standins.h2_material_name(kit, r'a\b'), 'hard_metal_thick_for')
        empty = kit / 'tags' / 'a' / 'c.shader'; empty.write_bytes(b'stemshaders\\shader_templates\\opaque\\tex_bumpdfbt')
        self.assertEqual(standins.h2_material_name(kit, r'a\c'), '', 'a template path is not a material name')
        self.assertEqual(standins.h2_material_name(kit, r'a\missing'), '')

    def test_teleporters_bare(self):
        data = dict(flags=[dict(type=7, position=[0, 0, 0], facing=0, team=8, identifier=1),
                           dict(type=0, position=[1, 0, 0], facing=0, team=0, identifier=0)])
        got = h2_scenario.netgame_objects(data)
        self.assertEqual([o['bare'] for o in got], [True, False])


if __name__ == '__main__':
    unittest.main()
