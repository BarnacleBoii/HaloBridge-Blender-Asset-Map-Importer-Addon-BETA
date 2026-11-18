"""Halo 2 lightmap copy: encoding, Halo 2 XML parsing and strip triangles."""
import math
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import h2_lightmaps as h2


def irradiance(coeffs, normal):
    """Light reaching a surface with this normal from 9 x RGB SH coefficients (Halo 3's diffuse)."""
    return (h2.SH_BANDS[:, None] * coeffs * h2.sh(normal)[:, None]).sum(axis=0)


XML = """<?xml version="1.0"?>
<tag group="scenario_structure_lightmap">
 <block name="lightmap groups"><element index="0">
  <block name="clusters"><element index="0">
   <block name="cache data"><element index="0">
    <block name="parts"><element index="0">
     <field name="flags" type="word flags">0</field>
     <field name="strip start index" type="short integer">0</field>
     <field name="strip length" type="short integer">4</field>
    </element></block>
    <block name="raw vertices">
     <element index="0"><field name="position">0,0,0</field><field name="normal">0,0,1</field><field name="primary lightmap texcoord">0,0</field><field name="primary lightmap incident direction">0,0,1</field></element>
     <element index="1"><field name="position">1,0,0</field><field name="normal">0,0,1</field><field name="primary lightmap texcoord">1,0</field><field name="primary lightmap incident direction">0,0,1</field></element>
     <element index="2"><field name="position">0,1,0</field><field name="normal">0,0,1</field><field name="primary lightmap texcoord">0,1</field><field name="primary lightmap incident direction">0,0,1</field></element>
     <element index="3"><field name="position">1,1,0</field><field name="normal">0,0,1</field><field name="primary lightmap texcoord">1,1</field><field name="primary lightmap incident direction">0,0,1</field></element>
    </block>
    <block name="strip indices">
     <element index="0"><field name="index">0</field></element><element index="1"><field name="index">1</field></element>
     <element index="2"><field name="index">2</field></element><element index="3"><field name="index">3</field></element>
    </block>
   </element></block>
  </element></block>
  <block name="cluster render info"><element index="0">
   <field name="bitmap index">7</field><field name="palette index">2</field>
  </element></block>
 </element></block>
</tag>"""


class Encoding(unittest.TestCase):
    def test_surface_gets_halo2_value(self):
        colour = np.array([.5, .4, .3])
        for normal, incident in (([0, 0, 1], [0, 0, 1]), ([0, 0, 1], [.7, 0, .7]), ([1, 0, 0], [0, .1, 1]), ([0, .6, .8], [-.9, 0, .1])):
            n = np.array(normal, float); n /= np.linalg.norm(n)
            got = irradiance(h2.encode(colour, incident, n), n)
            self.assertTrue(np.allclose(got, h2.BRIGHTNESS * colour, rtol=.02), (normal, incident, got))

    def test_nearby_bumps_never_black(self):
        # A bump-map normal tilted 40 degrees away from a skimming light still gets light.
        coeffs = h2.encode([.3, .3, .3], [1, 0, .05], [0, 0, 1])
        tilt = np.array([-math.sin(math.radians(40)), 0, math.cos(math.radians(40))])
        self.assertGreater(irradiance(coeffs, tilt)[0], .5 * h2.BRIGHTNESS * .3)

    def test_shared_pixel_never_negative(self):
        # A pixel shared by opposite faces gets even light: the same, positive, on every facing.
        coeffs = h2.encode([.4, .5, .6], [1, 0, 0], [1, 0, 0], directional=0)
        for n in ([1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, -.6, -.8]):
            self.assertTrue(np.allclose(irradiance(coeffs, np.array(n, float)), h2.BRIGHTNESS * np.array([.4, .5, .6]), rtol=.02))

    def test_overhead_matches_tool(self):
        # Tool's own bake of an overhead light of strength 1: layer 2 is 0.489, layer 6 is 0.631.
        self.assertAlmostEqual(h2.sh([0, 0, 1])[2], .4886, places=3)
        self.assertAlmostEqual(h2.sh([0, 0, 1])[6], .6308, places=3)
        self.assertLess(h2.sh([1, 0, 0])[3], 0, 'x terms carry the minus sign Tool writes')

    def test_vertex_light_matches_halo2(self):
        # Halo 3's per-vertex shader gives each vertex Halo 2's light on its own normal.
        colour = np.array([.4, .5, .6])
        for normal, incident, share in (([0, 0, 1], [0, 0, 1], .6), ([1, 0, 0], [.6, .3, .74], .8),
                                        ([0, -1, 0], [.2, -.9, .3], 0.0), ([0, 0, 1], [0, 0, 0], .5)):
            values = h2.encode_vertex(colour, incident, normal, 1.0, share)
            self.assertEqual(values.shape, (15,))
            self.assertTrue(np.allclose(h2.vertex_light(values, normal), colour, rtol=.03), (normal, h2.vertex_light(values, normal)))
        # The shader's direction (luminance of -c3, -c1, c2) is Halo 2's light direction.
        values = h2.encode_vertex(colour, [0, .6, .8], [0, 0, 1], 1.0, .7)
        terms = values[3:].reshape(3, 4); d = terms[1, [3, 1, 2]] * [-1, -1, 1]
        self.assertTrue(np.allclose(d / np.linalg.norm(d), [0, .6, .8], atol=1e-5))
        # Faces turned from the light get only the even share, never negative.
        self.assertTrue((h2.vertex_light(values, [0, 0, -1]) >= 0).all())

    def test_vertex_light_skimming_and_behind(self):
        # Light skimming a vertex, or from behind it, still gives the vertex its whole value, and no
        # bump-map normal gets more than 1/GRAZING times it.
        colour = np.array([.4, .5, .6])
        for incident in ([1, 0, .05], [1, 0, -.3], [0, 0, -1], [0, .2, -.98]):
            values = h2.encode_vertex(colour, incident, [0, 0, 1], 1.0, .9)
            self.assertTrue(np.isfinite(values).all())
            self.assertTrue(np.allclose(h2.vertex_light(values, [0, 0, 1]), colour, rtol=.03), (incident, h2.vertex_light(values, [0, 0, 1])))
            for bump in ([.7, 0, .7], [-.7, 0, .7], [0, .7, .7], [1, 0, 0]):
                self.assertTrue((h2.vertex_light(values, bump) <= colour / h2.GRAZING + 1e-6).all(), (incident, bump))

    def test_compressed_positions(self):
        # Definition meshes keep positions as 0..1 inside (x min, x max, y min, y max, z min, z max).
        got = h2.decompress_positions([[0, 0, 0], [1, 1, 1], [.5, .5, .5]], [-2, 6, -4, -1, -3, 1])
        self.assertTrue(np.allclose(got, [[-2, -4, -3], [6, -1, 1], [2, -2.5, -1]]))
        self.assertTrue(np.allclose(h2.decompress_positions([[1, 2, 3]], None), [[1, 2, 3]]))


class Parsing(unittest.TestCase):
    def test_xml(self):
        path = Path(tempfile.mkdtemp()) / 'lm.xml'; path.write_text(XML, encoding='utf-8')
        d = h2.parse(path)
        self.assertEqual(d['c0_pos'].shape, (4, 3))
        self.assertEqual(d['c0_bitmap'].tolist(), [7, 2])
        self.assertEqual(d['c0_tri'].tolist(), [[0, 1, 2], [2, 1, 3]])
        self.assertEqual(d['c0_uv'][3].tolist(), [1, 1])

    def test_instances(self):
        path = Path(tempfile.mkdtemp()) / 'bsp.xml'
        path.write_text('''<?xml version="1.0"?><tag group="scenario_structure_bsp">
 <block name="instanced geometry instances"><element index="0">
  <field name="scale">2.0</field><field name="forward">0,1,0</field><field name="left">-1,0,0</field><field name="up">0,0,1</field>
  <field name="position">10,20,3</field>
  <block_index name="short block index" type="instance definition" index="4">x</block_index>
  <field name="lightmapping policy">1,per-vertex</field>
 </element></block></tag>''', encoding='utf-8')
        d = h2.parse_instances(path)
        self.assertEqual(d['inst_def'].tolist(), [4]); self.assertEqual(d['inst_per_pixel'].tolist(), [False])
        m = d['inst_matrix'][0]
        # A point one unit along the definition's x lands two units along world y from the position.
        self.assertTrue(np.allclose(m @ [1, 0, 0, 1], [10, 22, 3, 1]))

    def test_per_vertex_buckets(self):
        # Instances Halo 2 lit per vertex: bucket colours and directions, and each instance's slice.
        path = Path(tempfile.mkdtemp()) / 'lm.xml'
        path.write_text('''<?xml version="1.0"?><tag group="scenario_structure_lightmap">
 <block name="lightmap groups"><element index="0">
  <block name="geometry buckets"><element index="0"><block name="raw vertices">
   <element index="0"><field name="primary lightmap color">0.5,0.4,0.3</field><field name="primary lightmap incident direction">0,0,1</field></element>
   <element index="1"><field name="primary lightmap color">0.1,0.2,0.3</field><field name="primary lightmap incident direction">1,0,0</field></element>
  </block></element></block>
  <block name="instance bucket refs"><element index="0">
   <field name="flags">0</field><field name="bucket index">0</field>
   <block name="section offsets"><element index="0"><field name="section offset">1</field></element></block>
  </element></block>
 </element></block></tag>''', encoding='utf-8')
        d = h2.parse(path)
        self.assertTrue(np.allclose(d['b0_col'], [[.5, .4, .3], [.1, .2, .3]]))
        self.assertEqual(d['b0_dir'][1].tolist(), [1, 0, 0])
        self.assertEqual(d['i0_bucket'].tolist(), [0, 1])
        self.assertFalse(any(k.startswith('c') for k in d), 'bucket vertices are not a cluster')

    def test_unlit_clusters(self):
        # Clusters without a lightmap page (Ascension's water plane) are listed per BSP.
        path = Path(tempfile.mkdtemp()) / 'lightmap.npz'
        np.savez(path, c0_bitmap=np.array([0, 0]), c6_bitmap=np.array([-1, -1]), i3_bitmap=np.array([-1, -1]))
        got = h2.unlit_clusters([dict(npz=str(path), bsp='Scenarios\\Multi\\Ascension\\Ascension')])
        self.assertEqual(got, {'scenarios\\multi\\ascension\\ascension': {6}})

    def test_unbaked_texels_filled(self):
        # Halo 2 leaves unbaked texels black; they take the nearest baked light instead.
        img = np.zeros((6, 6, 3), np.float32); img[:, :2] = [.5, .4, .3]
        out = h2.fill_empty(img)
        self.assertTrue(np.allclose(out, [.5, .4, .3]))
        self.assertTrue(np.allclose(img[:, 2:], 0), 'the input is not changed')
        self.assertTrue(np.allclose(h2.fill_empty(np.zeros((2, 2, 3))), 0), 'an empty page stays empty')

    def test_unlit_vertices_filled(self):
        cols = np.array([[.6, .6, .6], [0, 0, 0], [0, 0, 0], [0, 0, 0]], np.float32)
        tris = np.array([[0, 1, 2], [3, 3, 3]])  # vertex 3 has no lit neighbour: the piece's average
        out = h2.fill_empty_vertices(cols, tris)
        self.assertTrue(np.allclose(out, .6))

    def test_triangle_list_and_degenerate_strips(self):
        self.assertEqual(h2.triangles([(0, 6, True)], [0, 1, 2, 3, 4, 5]), [[0, 1, 2], [3, 4, 5]])
        self.assertEqual(h2.triangles([(0, 5, False)], [0, 1, 1, 2, 3]), [[1, 2, 3]])


if __name__ == '__main__':
    unittest.main()
