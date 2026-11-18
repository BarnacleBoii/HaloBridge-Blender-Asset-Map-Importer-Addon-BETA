import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from halo_bridge import jobs

class H2ACampaignPaksTests(unittest.TestCase):
    def make_install(self,root):
        paks=root/'Halo The Master Chief Collection'/'halo2'/'preload'/'paks'
        maps=root/'Halo The Master Chief Collection'/'groundhog'/'maps'
        paks.mkdir(parents=True);maps.mkdir(parents=True)
        for name in ('shared.pck','cache.pck','01a_tutorial.pck','07b_forerunnership.pck','01a_tutorial.csv'):
            (paks/name).write_bytes(b'')
        return paks,maps

    def test_found_from_groundhog_maps(self):
        with tempfile.TemporaryDirectory() as folder:
            paks,maps=self.make_install(Path(folder))
            self.assertEqual(jobs.h2a_campaign_paks(str(maps)),paks)
            # shared.pck and cache.pck hold common data; only level paks are listed.
            self.assertEqual(jobs.h2a_campaign_levels(str(maps)),['01a_tutorial.pck','07b_forerunnership.pck'])

    def test_found_from_paks_folder_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            paks,_=self.make_install(Path(folder))
            self.assertEqual(jobs.h2a_campaign_paks(str(paks)),paks)

    def test_missing_install(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(jobs.h2a_campaign_paks(folder))
            self.assertEqual(jobs.h2a_campaign_levels(folder),[])
            self.assertIsNone(jobs.h2a_campaign_paks(''))
            with self.assertRaises(RuntimeError):
                jobs.extract_h2a_campaign_scene(dict(maps=folder,cache=folder),'01a_tutorial.pck')

class H2ACampaignStorageTests(unittest.TestCase):
    def test_discard_removes_only_campaign_geometry(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);scene=folder/'scene'
            scene.mkdir()
            (scene/'mesh_0.json').write_text('{"meshes":[]}');(scene/'mesh_1.json').write_text('{}')
            manifest=scene/'scene.json'
            manifest.write_text(json.dumps(dict(source='h2a_campaign',meshes={'a|0':'mesh_0.json','a|1':'mesh_1.json'})))
            self.assertTrue(jobs._scene_complete(manifest))
            self.assertGreater(jobs.discard_h2a_campaign_meshes(manifest),0)
            self.assertFalse((scene/'mesh_0.json').exists())
            self.assertTrue(manifest.is_file())  # Prepare still reads scene.json
            self.assertFalse(jobs._scene_complete(manifest))  # a later import re-extracts
            # Other games' map scenes are never touched.
            (scene/'mesh_0.json').write_text('{}')
            manifest.write_text(json.dumps(dict(game='halo2',meshes={'a|0':'mesh_0.json'})))
            self.assertEqual(jobs.discard_h2a_campaign_meshes(manifest),0)
            self.assertTrue((scene/'mesh_0.json').exists())

    def test_textures_shared_per_size(self):
        config=dict(cache='C:/cache')
        self.assertEqual(jobs.h2a_campaign_textures(config,2048),jobs.h2a_campaign_textures(config,2048))
        self.assertNotEqual(jobs.h2a_campaign_textures(config,2048),jobs.h2a_campaign_textures(config,1024))

if __name__=='__main__':unittest.main()
