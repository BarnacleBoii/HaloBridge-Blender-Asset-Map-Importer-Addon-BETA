"""Storage: old Prepare backups are removed, unfinished ones kept."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import build


def backup(folder, stamp, level, state):
    path = folder / str(stamp); (path / 'tags').mkdir(parents=True)
    (path / 'tags' / 'x.bin').write_bytes(b'0' * 100)
    if state: (path / 'transaction.json').write_text(json.dumps(dict(level=level, state=state)))
    return path


class Backups(unittest.TestCase):
    def test_prune(self):
        folder = Path(tempfile.mkdtemp())
        old = backup(folder, 1, 'a', 'committed')
        new = backup(folder, 5, 'a', 'committed')
        other = backup(folder, 2, 'b', 'committed')
        rolled = backup(folder, 6, 'a', 'rolled_back')
        running = backup(folder, 3, 'a', 'running')
        unknown = backup(folder, 4, 'a', None)
        freed = build.prune_backups(folder)
        self.assertFalse(old.exists(), 'an older finished backup of the same level goes')
        self.assertFalse(rolled.exists(), 'a rolled-back backup was already copied back')
        for kept in (new, other, running, unknown):
            self.assertTrue(kept.exists(), kept)
        self.assertGreaterEqual(freed, 200)
        self.assertEqual(build.prune_backups(folder / 'missing'), 0)


class StaleShaders(unittest.TestCase):
    def test_other_types_removed(self):
        folder = Path(tempfile.mkdtemp())
        for name in ('a.shader', 'a.shader_water', 'a.shader_terrain', 'ab.shader', 'b.shader'):
            (folder / name).write_bytes(b'x')
        build.remove_stale_shaders(folder, 'a', '.shader_water')
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['a.shader_water', 'ab.shader', 'b.shader'])
        build.remove_stale_shaders(folder / 'missing', 'a', '.shader')


class WaterSurfaces(unittest.TestCase):
    def test_marked(self):
        path = Path(tempfile.mkdtemp()) / 'level.ASS'
        path.write_bytes(b';MATERIAL 0\r\n"reach_a"\r\n""\r\n;MATERIAL 1\r\n"reach_ab"\r\n')
        self.assertEqual(build.mark_water_surfaces(path, ['reach_a', 'missing']), 1)
        self.assertEqual(path.read_bytes(), b';MATERIAL 0\r\n"\'reach_a"\r\n""\r\n;MATERIAL 1\r\n"reach_ab"\r\n')
        self.assertEqual(build.mark_water_surfaces(path, []), 0)


if __name__ == '__main__':
    unittest.main()
