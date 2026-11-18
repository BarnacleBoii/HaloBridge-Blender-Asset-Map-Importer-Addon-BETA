"""Halo CE lighting: the extractor's lightmap blocks become the copy worker's arrays."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import h1_lightmaps


class Arrays(unittest.TestCase):
    def test_blocks_become_clusters(self):
        bsp = dict(clusters=[
            dict(page=3, pos=[0, 0, 0, 1, 0, 0, 0, 1, 0], nrm=[0, 0, 1] * 3, uv=[0, 0, 1, 0, 0, 1],
                 dir=[0, 0, 1] * 3, tri=[0, 1, 2]),
            dict(page=0, pos=[0, 0, 5] * 3, nrm=[0, 0, 1] * 3, uv=[0, 0] * 3, dir=[0, 0, 1] * 3, tri=[0, 1, 2])])
        a = h1_lightmaps.to_arrays(bsp)
        self.assertEqual(a['c0_pos'].shape, (3, 3))
        self.assertEqual(a['c0_uv'].shape, (3, 2))
        self.assertEqual(a['c0_tri'].tolist(), [[0, 1, 2]])
        self.assertEqual(a['c0_bitmap'].tolist(), [3, 0])
        self.assertEqual(a['c1_bitmap'].tolist(), [0, 0])
        self.assertEqual(sorted(k for k in a if k.startswith('c1')), ['c1_bitmap', 'c1_dir', 'c1_nrm', 'c1_pos', 'c1_tri', 'c1_uv'])


if __name__ == '__main__':
    unittest.main()
