"""Sky layer textures are enlarged with bilinear filtering, wrapping, not as squares of one texel."""
import sys
import types
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault('bpy', types.ModuleType('bpy'))
from halo_bridge.classic_sky import _resample


class Resample(unittest.TestCase):
    def test_same_size_is_unchanged(self):
        data = np.random.default_rng(1).random((8, 8, 4)).astype(np.float32)
        self.assertTrue(np.allclose(_resample(data, 8, 8, (1, 1)), data))

    def test_enlarged_mask_is_smooth(self):
        mask = np.zeros((4, 4, 4), dtype=np.float32); mask[:, 2:] = 1  # a hard edge
        big = _resample(mask, 32, 32, (1, 1))[0, :, 0]
        # Nearest-texel enlarging gave 8-wide steps of 0 and 1; bilinear ramps between them.
        self.assertGreater(len(np.unique(np.round(big, 3))), 4)
        self.assertTrue(np.all(np.diff(big[4:20]) >= -1e-6))

    def test_tiling_wraps(self):
        data = np.arange(4, dtype=np.float32).reshape(1, 4, 1).repeat(4, 2)
        tiled = _resample(data, 8, 1, (2, 1))[0, :, 0]
        self.assertTrue(np.allclose(tiled[:4], tiled[4:]))


if __name__ == '__main__':
    unittest.main()
