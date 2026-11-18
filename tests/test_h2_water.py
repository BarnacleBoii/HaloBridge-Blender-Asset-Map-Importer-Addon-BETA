"""Halo 2 water definitions (an infinite water plane in the BSP) as Halo 3 water."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import h2_water

XML = '''<tag group="scenario_structure_bsp">
 <block name="water definitions">
  <element index="0"><tag_reference name="shader">scenarios\\shaders\\multi\\zanzibar\\water_static</tag_reference>
   <field name="height" type="real">-3.000000</field></element>
  <element index="1"><tag_reference name="shader">
			 </tag_reference><field name="height" type="real">0.000000</field></element>
 </block>
 <block name="other"></block>
</tag>'''


class Water(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(h2_water.parse(XML), [(r'scenarios\shaders\multi\zanzibar\water_static', -3.0)])
        self.assertEqual(h2_water.parse('<tag></tag>'), [])

    def test_grid(self):
        verts, faces = h2_water.grid((0, 0), (1600, 800), -300, 100)  # 16 x 8 world units
        self.assertEqual(len(faces), min(2, h2_water.MAX_CELLS) * 1)
        self.assertTrue(all(v[2] == -300 for v in verts))
        verts, faces = h2_water.grid((0, 0), (10 ** 6, 10), 0, 1)
        self.assertEqual(len(faces), h2_water.MAX_CELLS)
        self.assertTrue(set(h2_water.WATER_TEMPLATE.lower().split('\\')) >= {'water'})


if __name__ == '__main__':
    unittest.main()
