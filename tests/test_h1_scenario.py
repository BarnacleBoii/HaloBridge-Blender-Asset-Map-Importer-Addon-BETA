"""Halo CE gameplay (read from the map) in Halo 2's form, so the same Halo 3 writer places it."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import h1_scenario, h2_scenario

# Blood Gulch as the extractor reads it (a few of its 72 starts and 191 flags).
DATA = dict(
    starts=[dict(position=[98.49, -157.64, 1.70], facing=76.1, team=0), dict(position=[40.2, -79.1, 1.8], facing=-90, team=1)],
    flags=[dict(position=[95.69, -159.45, -0.1], facing=0, type=0, team=0),    # red CTF flag
           dict(position=[95.58, -155.45, 1.81], facing=0, type=6, team=0),    # teleport from, channel 0
           dict(position=[40.06, -82.92, 1.81], facing=0, type=7, team=0),     # teleport to, channel 0
           dict(position=[60, -100, 0], facing=0, type=8, team=2),             # hill 2
           dict(position=[60, -100, 0], facing=0, type=3, team=0)])            # race track: none in Halo 3


class CE(unittest.TestCase):
    def test_converted(self):
        data = h1_scenario.to_h2_format(DATA)
        self.assertEqual(len(data['starts']), 2)
        self.assertEqual(data['starts'][1]['team'], 1)
        self.assertEqual([f['type'] for f in data['flags']], [0, 7, 8, 13])
        objects = h2_scenario.netgame_objects(data)
        tags = [o['tag'].rsplit('\\', 1)[-1] for o in objects]
        self.assertEqual(tags, ['ctf_flag_spawn_point', 'teleporter_sender', 'teleporter_reciever', 'koth_hill_static'])
        self.assertEqual(objects[0]['team'], 0)
        self.assertEqual((objects[1]['channel'], objects[2]['channel']), (0, 0))


class Vehicles(unittest.TestCase):
    def test_families(self):
        import tempfile
        kit = Path(tempfile.mkdtemp())
        for f in ('warthog', 'ghost'):
            (kit / 'objects' / 'vehicles' / f).mkdir(parents=True)
            (kit / 'objects' / 'vehicles' / f / (f + '.vehicle')).write_bytes(b'')
        data = dict(vehicles=[dict(tag='vehicles\\warthog\\mp_warthog', position=[1, 2, 3], rotation=[-49, 0, 0]),
                              dict(tag='vehicles\\rwarthog\\rwarthog', position=[4, 5, 6], rotation=[0, 0, 0]),
                              dict(tag='vehicles\\ghost\\ghost_mp', position=[7, 8, 9], rotation=[90, 0, 0]),
                              dict(tag='vehicles\\scorpion\\scorpion_mp', position=[0, 0, 0], rotation=[0, 0, 0])])
        placed = h1_scenario.vehicles(data, kit, 'bloodgulch.map')
        self.assertEqual([v['tag'].rsplit('\\', 1)[-1] for v in placed], ['warthog', 'warthog', 'ghost'])  # no Scorpion tag in this kit
        self.assertEqual(placed[0]['rotation'], [-49, 0, 0])
        self.assertEqual(len({v['id'] for v in placed}), 3)


if __name__ == '__main__':
    unittest.main()
