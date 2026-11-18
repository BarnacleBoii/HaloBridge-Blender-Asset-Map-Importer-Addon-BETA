"""Halo 2 gameplay data read from the kit's scenario XML: spawns, netgame flags, kill volumes."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import h2_scenario

XML = """<?xml version="1.0"?>
<tag group="scenario">
 <block name="player starting locations">
  <element index="0">
   <field name="position" type="real point 3d">0.025557,8.197940,0.001242</field>
   <field name="facing" type="angle">203.303250</field>
   <field name="team designator" type="enum">1,Bravo</field>
   <field name="type 0" type="enum">12,all games</field>
   <field name="type 1" type="enum">0,none</field>
   <field name="type 2" type="enum">0,none</field>
   <field name="type 3" type="enum">0,none</field>
  </element>
 </block>
 <block name="trigger volumes">
  <element index="0">
   <field name="name" type="string id">kill_clouds</field>
   <field name="forward" type="real vector 3d">1,0,0</field>
   <field name="up" type="real vector 3d">0,0,1</field>
   <field name="position" type="real point 3d">-50,-56,-36</field>
   <field name="extents" type="real point 3d">100,110,20</field>
  </element>
  <element index="1">
   <field name="name" type="string id">not_a_kill</field>
   <field name="forward" type="real vector 3d">1,0,0</field>
   <field name="up" type="real vector 3d">0,0,1</field>
   <field name="position" type="real point 3d">0,0,0</field>
   <field name="extents" type="real point 3d">1,1,1</field>
  </element>
 </block>
 <block name="netgame flags">
  <element index="0" name="Teleporter dest [NEUTRAL]">
   <field name="position" type="real point 3d">3.19835,6.901,-0.585216</field>
   <field name="facing" type="angle">90.000000</field>
   <field name="type" type="enum">8,Teleporter (dest)</field>
   <field name="team designator" type="enum">8,NEUTRAL</field>
   <field name="identifier" type="short integer">2</field>
  </element>
 </block>
 <block name="scenario kill triggers">
  <element index="0"><block_index name="short block index" type="trigger volume" index="0">x</block_index></element>
 </block>
</tag>"""


class Gameplay(unittest.TestCase):
    def setUp(self):
        path = Path(tempfile.mkdtemp()) / 'scenario.xml'; path.write_text(XML, encoding='utf-8')
        self.data = h2_scenario.parse(path)

    def test_starts(self):
        s = self.data['starts'][0]
        self.assertEqual(s['position'], [0.025557, 8.19794, 0.001242])
        self.assertEqual((s['team'], s['team_name'], s['game_types']), (1, 'Bravo', ['all games']))
        self.assertAlmostEqual(h2_scenario.facing_degrees(s), -156.69675)

    def test_flags(self):
        f = self.data['flags'][0]
        self.assertEqual((f['type'], f['type_name'], f['team'], f['identifier']), (8, 'Teleporter (dest)', 8, 2))

    def test_netgame_objects(self):
        data = dict(flags=[
            dict(position=[1, 2, 3], facing=90.0, type=8, type_name='Teleporter (dest)', team=8, identifier=2),
            dict(position=[0, 0, 0], facing=0.0, type=0, type_name='CTF flag spawn', team=1, identifier=0),
            dict(position=[4, 0, 1], facing=0.0, type=12, type_name='King Hill 1', team=8, identifier=0),
            dict(position=[-4, 0, 2], facing=0.0, type=12, type_name='King Hill 1', team=8, identifier=0),
            dict(position=[0, 4, 1], facing=0.0, type=12, type_name='King Hill 1', team=8, identifier=0),
            dict(position=[9, 9, 9], facing=0.0, type=6, type_name='Race checkpoint', team=8, identifier=0)])
        objects = h2_scenario.netgame_objects(data)
        self.assertEqual([o['tag'].rsplit('\\', 1)[-1] for o in objects], ['teleporter_reciever', 'ctf_flag_spawn_point', 'koth_hill_static'])
        self.assertEqual((objects[0]['channel'], objects[1]['team']), (2, 1))
        hill = objects[2]
        self.assertEqual((hill['shape'], hill['channel'], hill['position'][2]), (2, 1, 1))
        self.assertGreaterEqual(hill['radius'], 4.0)

    def test_vehicles(self):
        kit = Path(tempfile.mkdtemp())
        (kit / 'objects' / 'vehicles' / 'banshee').mkdir(parents=True)
        (kit / 'objects' / 'vehicles' / 'banshee' / 'banshee.vehicle').write_bytes(b'')
        data = dict(equipment=[
            dict(position=[1, 2, 3], orientation=[90, 0, 0], classification='weapon', collection='multiplayer\\single_weapons\\smg'),
            dict(position=[4, 5, 6], orientation=[45, 0, 0], classification='vehicle', collection='multiplayer\\single_vehicles\\banshee'),
            dict(position=[0, 0, 0], orientation=[0, 0, 0], classification='vehicle', collection='multiplayer\\single_vehicles\\spectre')])
        placed = h2_scenario.vehicles(data, kit, 'scenarios\\multi\\ascension\\ascension')
        self.assertEqual([(v['tag'], v['position'], v['rotation']) for v in placed], [('objects\\vehicles\\banshee\\banshee', [4, 5, 6], [45, 0, 0])])
        self.assertRegex(placed[0]['id'], r'^hb_[0-9a-f]{24}$')
        self.assertEqual(placed[0]['id'], h2_scenario.vehicles(data, kit, 'scenarios\\multi\\ascension\\ascension')[0]['id'])

    def test_windows_1252_script_text(self):
        # The kit's Tool writes script text as Windows-1252 in a file it declares UTF-8 (Relic).
        path = Path(tempfile.mkdtemp()) / 'scenario.xml'
        path.write_bytes(XML.replace('</tag>', '<field name="script">(print "press the “a” button")</field></tag>').encode('cp1252'))
        data = h2_scenario.parse(path)
        self.assertEqual(len(data['starts']), 1)

    def test_kill_volumes(self):
        volumes = h2_scenario.kill_volumes(self.data)
        self.assertEqual([v['name'] for v in volumes], ['kill_clouds'])
        # The corner plus half the extents along forward, left (+y) and up.
        self.assertEqual(volumes[0]['center'], [0.0, -1.0, -26.0])


if __name__ == '__main__':
    unittest.main()
